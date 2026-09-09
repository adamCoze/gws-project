"""考核模块路由"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import (
    Assessment, AssessmentScore, AssessmentOperationLog,
    WorkItem, User, Department, District,
    RoleLevel, AssessmentStatus,
)
from auth import get_current_user, require_role

router = APIRouter(prefix="/assessments", tags=["考核管理"])


def get_user_identities(user):
    identities = [{
        "role_level": user.role_level,
        "department_id": user.department_id,
        "district_id": user.district_id,
        "is_primary": True,
        "index": 0,
    }]
    if user.secondary_roles:
        for i, sr in enumerate(user.secondary_roles):
            identities.append({
                "role_level": sr.get("role_level"),
                "department_id": sr.get("department_id"),
                "district_id": sr.get("district_id"),
                "is_primary": False,
                "index": i + 1,
            })
    return identities


def user_to_brief(u):
    if not u:
        return None
    return {
        "id": u.id,
        "real_name": u.real_name,
        "username": u.username,
        "email_prefix": u.email_prefix,
        "role_level": u.role_level,
        "secondary_roles": u.secondary_roles or [],
    }


async def add_op_log(db, aid, uid, action, detail=""):
    db.add(AssessmentOperationLog(
        assessment_id=aid, operator_id=uid, action=action, detail=detail
    ))


async def get_direct_manager(db, user_id):
    r = await db.execute(select(User).where(User.id == user_id))
    u = r.scalar_one_or_none()
    if not u or not u.department_id:
        return None
    r2 = await db.execute(
        select(User).where(
            User.department_id == u.department_id,
            User.role_level == RoleLevel.MANAGER,
            User.is_active == True,
        )
    )
    mgrs = r2.scalars().all()
    return mgrs[0] if mgrs else None


# ===== Schemas =====

class AssessmentCreate(BaseModel):
    title: str
    year: int
    month: int
    description: Optional[str] = None
    scope_type: str = "department"
    scope_id: Optional[int] = None
    initiator_identity_index: int = 0


class AssessmentUpdate(BaseModel):
    title: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = None
    description: Optional[str] = None
    scope_type: Optional[str] = None
    scope_id: Optional[int] = None


class ScoreSubmit(BaseModel):
    score: int
    comment: Optional[str] = None


# ===== 我的待评分 =====

@router.get("/pending-scores", response_model=List[dict])
async def pending_scores(db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    idents = get_user_identities(current_user)
    conds = []
    for ident in idents:
        conds.append(and_(
            AssessmentScore.scorer_id == current_user.id,
            AssessmentScore.scorer_role_level == ident["role_level"],
            AssessmentScore.score.is_(None),
        ))
    if not conds:
        return []

    r = await db.execute(
        select(AssessmentScore).options(
            selectinload(AssessmentScore.assessment),
            selectinload(AssessmentScore.work_item).selectinload(WorkItem.assignee).selectinload(User.department),
            selectinload(AssessmentScore.work_item).selectinload(WorkItem.assignee).selectinload(User.district),
        ).where(or_(*conds)).order_by(AssessmentScore.created_at.desc())
    )
    scores = r.scalars().all()
    out = []
    for s in scores:
        wi = s.work_item
        assignee = wi.assignee if wi else None
        out.append({
            "id": s.id, "assessment_id": s.assessment_id, "work_item_id": s.work_item_id,
            "level": s.level, "scorer_role_level": s.scorer_role_level,
            "scorer_department_id": s.scorer_department_id,
            "scorer_district_id": s.scorer_district_id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "assessment_title": s.assessment.title if s.assessment else "",
            "assessment_status": s.assessment.status if s.assessment else "",
            "work_item_title": wi.title if wi else "",
            "assignee_name": (assignee.real_name or assignee.username) if assignee else "",
            "assignee_email_prefix": assignee.email_prefix if assignee else "",
        })
    return out



# ===== 列表 =====

@router.get("", response_model=List[dict])
async def list_assessments(
    status: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Assessment).options(
        selectinload(Assessment.creator).selectinload(User.department),
        selectinload(Assessment.creator).selectinload(User.district),
    )

    if current_user.role_level < RoleLevel.REGULATOR:
        if current_user.role_level == RoleLevel.DEPT_DIRECTOR and current_user.department_id:
            query = query.where(or_(
                Assessment.initiator_department_id == current_user.department_id,
                Assessment.created_by == current_user.id,
            ))
        elif current_user.role_level == RoleLevel.DISTRICT_MANAGER and current_user.district_id:
            query = query.where(or_(
                Assessment.initiator_district_id == current_user.district_id,
                Assessment.created_by == current_user.id,
            ))
        else:
            query = query.where(Assessment.created_by == current_user.id)

    if status:
        query = query.where(Assessment.status == status)
    if year:
        query = query.where(Assessment.year == year)
    if month:
        query = query.where(Assessment.month == month)

    query = query.order_by(Assessment.created_at.desc()).offset((page-1)*page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    out = []
    for item in items:
        scr = await db.execute(select(AssessmentScore.id).where(AssessmentScore.assessment_id == item.id))
        cnt = len(scr.all())
        out.append({
            "id": item.id, "title": item.title, "year": item.year, "month": item.month,
            "status": item.status, "description": item.description,
            "initiator_role_level": item.initiator_role_level,
            "initiator_department_id": item.initiator_department_id,
            "initiator_district_id": item.initiator_district_id,
            "created_by": item.created_by,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "creator": user_to_brief(item.creator),
            "scores_count": cnt,
        })
    return out


# ===== 详情 =====

@router.get("/{aid}", response_model=dict)
async def get_assessment(aid: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    r = await db.execute(
        select(Assessment).options(
            selectinload(Assessment.creator).selectinload(User.department),
            selectinload(Assessment.creator).selectinload(User.district),
        ).where(Assessment.id == aid)
    )
    a = r.scalar_one_or_none()
    if not a:
        raise HTTPException(404, "考核不存在")
    return {
        "id": a.id, "title": a.title, "year": a.year, "month": a.month,
        "status": a.status, "description": a.description,
        "initiator_role_level": a.initiator_role_level,
        "initiator_department_id": a.initiator_department_id,
        "initiator_district_id": a.initiator_district_id,
        "created_by": a.created_by,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "creator": user_to_brief(a.creator),
    }


# ===== 创建 =====

@router.post("", response_model=dict, status_code=201)
async def create_assessment(data: AssessmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(RoleLevel.MANAGER))):
    idents = get_user_identities(current_user)
    if data.initiator_identity_index >= len(idents):
        raise HTTPException(400, "无效的发起身份")
    ident = idents[data.initiator_identity_index]

    a = Assessment(
        title=data.title, year=data.year, month=data.month,
        description=data.description, status=AssessmentStatus.draft.value,
        initiator_role_level=ident["role_level"],
        initiator_department_id=ident["department_id"],
        initiator_district_id=ident["district_id"],
        created_by=current_user.id,
    )
    db.add(a)
    await db.flush()
    await add_op_log(db, a.id, current_user.id, "创建", f"创建考核：{data.title}")
    await db.commit()
    await db.refresh(a)
    return {"id": a.id, "title": a.title, "status": a.status}


# ===== 更新 =====

@router.put("/{aid}", response_model=dict)
async def update_assessment(aid: int, data: AssessmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    r = await db.execute(select(Assessment).where(Assessment.id == aid))
    a = r.scalar_one_or_none()
    if not a: raise HTTPException(404, "考核不存在")
    if a.status != AssessmentStatus.draft.value:
        raise HTTPException(400, "仅草稿状态可编辑")
    if a.created_by != current_user.id and current_user.role_level < RoleLevel.DEPT_DIRECTOR:
        raise HTTPException(403, "无权限")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    await add_op_log(db, a.id, current_user.id, "编辑")
    await db.commit()
    return {"id": a.id, "status": a.status}


# ===== 删除 =====

@router.delete("/{aid}")
async def delete_assessment(aid: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    r = await db.execute(select(Assessment).where(Assessment.id == aid))
    a = r.scalar_one_or_none()
    if not a: raise HTTPException(404, "考核不存在")
    if a.status != AssessmentStatus.draft.value:
        raise HTTPException(400, "仅草稿状态可删除")
    if a.created_by != current_user.id and current_user.role_level < RoleLevel.DEPT_DIRECTOR:
        raise HTTPException(403, "无权限")
    await db.delete(a)
    await db.commit()
    return {"message": "删除成功"}


# ===== 启动评分 =====

@router.post("/{aid}/start", response_model=dict)
async def start_assessment(aid: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    r = await db.execute(select(Assessment).where(Assessment.id == aid))
    a = r.scalar_one_or_none()
    if not a: raise HTTPException(404, "考核不存在")
    if a.status != AssessmentStatus.draft.value:
        raise HTTPException(400, "仅草稿状态可启动")
    if a.created_by != current_user.id and current_user.role_level < RoleLevel.DEPT_DIRECTOR:
        raise HTTPException(403, "无权限")

    # 筛选范围内工作项
    wiq = select(WorkItem).options(selectinload(WorkItem.assignee))
    if a.initiator_department_id:
        wiq = wiq.where(WorkItem.department_id == a.initiator_department_id)
    # 只选已完成的工作项作为考核对象
    wiq = wiq.where(WorkItem.status.in_(["completed", "in_progress", "pending"]))

    wir = await db.execute(wiq)
    wis = wir.scalars().all()

    count = 0
    for wi in wis:
        if not wi.assignee_id:
            continue
        scorer = await get_direct_manager(db, wi.assignee_id)
        s = AssessmentScore(
            assessment_id=a.id, work_item_id=wi.id, level=1,
            scorer_id=scorer.id if scorer else None,
            scorer_role_level=scorer.role_level if scorer else None,
            scorer_department_id=scorer.department_id if scorer else None,
            scorer_district_id=scorer.district_id if scorer else None,
        )
        db.add(s)
        count += 1

    a.status = AssessmentStatus.scoring.value
    await add_op_log(db, a.id, current_user.id, "启动评分", f"创建{count}条一级评分")
    await db.commit()
    return {"id": a.id, "status": a.status, "created_scores": count}


# ===== 完成 =====

@router.post("/{aid}/complete", response_model=dict)
async def complete_assessment(aid: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    r = await db.execute(select(Assessment).where(Assessment.id == aid))
    a = r.scalar_one_or_none()
    if not a: raise HTTPException(404, "考核不存在")
    if a.status not in (AssessmentStatus.scoring.value, AssessmentStatus.reviewing.value):
        raise HTTPException(400, "当前状态不可完成")
    if current_user.role_level < RoleLevel.DEPT_DIRECTOR and a.created_by != current_user.id:
        raise HTTPException(403, "无权限")
    a.status = AssessmentStatus.completed.value
    await add_op_log(db, a.id, current_user.id, "完成")
    await db.commit()
    return {"id": a.id, "status": a.status}


# ===== 取消 =====

@router.post("/{aid}/cancel", response_model=dict)
async def cancel_assessment(aid: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    r = await db.execute(select(Assessment).where(Assessment.id == aid))
    a = r.scalar_one_or_none()
    if not a: raise HTTPException(404, "考核不存在")
    if a.status == AssessmentStatus.completed.value:
        raise HTTPException(400, "已完成不可取消")
    if current_user.role_level < RoleLevel.DEPT_DIRECTOR and a.created_by != current_user.id:
        raise HTTPException(403, "无权限")
    a.status = AssessmentStatus.cancelled.value
    await add_op_log(db, a.id, current_user.id, "取消")
    await db.commit()
    return {"id": a.id, "status": a.status}


# ===== 评分列表 =====

@router.get("/{aid}/scores", response_model=List[dict])
async def list_scores(aid: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    r = await db.execute(select(Assessment).where(Assessment.id == aid))
    if not r.scalar_one_or_none():
        raise HTTPException(404, "考核不存在")

    sr = await db.execute(
        select(AssessmentScore).options(
            selectinload(AssessmentScore.scorer).selectinload(User.department),
            selectinload(AssessmentScore.scorer).selectinload(User.district),
            selectinload(AssessmentScore.work_item).selectinload(WorkItem.assignee).selectinload(User.department),
            selectinload(AssessmentScore.work_item).selectinload(WorkItem.assignee).selectinload(User.district),
        ).where(AssessmentScore.assessment_id == aid).order_by(AssessmentScore.level, AssessmentScore.id)
    )
    scores = sr.scalars().all()
    out = []
    for s in scores:
        wi = s.work_item
        out.append({
            "id": s.id, "assessment_id": s.assessment_id, "work_item_id": s.work_item_id,
            "scorer_id": s.scorer_id, "scorer_role_level": s.scorer_role_level,
            "scorer_department_id": s.scorer_department_id,
            "scorer_district_id": s.scorer_district_id,
            "level": s.level, "score": s.score, "comment": s.comment,
            "scored_at": s.scored_at.isoformat() if s.scored_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "work_item": {"id": wi.id, "title": wi.title, "status": wi.status, "assignee_id": wi.assignee_id} if wi else None,
            "scorer": user_to_brief(s.scorer),
        })
    return out


# ===== 操作日志 =====

@router.get("/{aid}/logs", response_model=List[dict])
async def list_logs(aid: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    r = await db.execute(
        select(AssessmentOperationLog).options(
            selectinload(AssessmentOperationLog.operator).selectinload(User.department),
            selectinload(AssessmentOperationLog.operator).selectinload(User.district),
        ).where(AssessmentOperationLog.assessment_id == aid)
         .order_by(AssessmentOperationLog.created_at.desc())
    )
    logs = r.scalars().all()
    return [{"id": l.id, "action": l.action, "detail": l.detail,
             "created_at": l.created_at.isoformat() if l.created_at else None,
             "operator": user_to_brief(l.operator)} for l in logs]



# ===== 提交评分 =====

@router.put("/scores/{sid}", response_model=dict)
async def submit_score(sid: int, data: ScoreSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    if data.score not in (1, 5, 10, 20, 30):
        raise HTTPException(400, "分数必须是 1/5/10/20/30")

    r = await db.execute(
        select(AssessmentScore).options(
            selectinload(AssessmentScore.assessment),
        ).where(AssessmentScore.id == sid)
    )
    s = r.scalar_one_or_none()
    if not s: raise HTTPException(404, "评分记录不存在")

    idents = get_user_identities(current_user)
    is_scorer = any(s.scorer_id == current_user.id and s.scorer_role_level == i["role_level"] for i in idents)
    if not is_scorer and current_user.role_level < RoleLevel.REGULATOR:
        raise HTTPException(403, "无权限评分")
    if s.score is not None:
        raise HTTPException(400, "已提交不可重复评分")
    if s.assessment and s.assessment.status != AssessmentStatus.scoring.value:
        raise HTTPException(400, "当前状态不允许评分")

    s.score = data.score
    s.comment = data.comment
    s.scored_at = datetime.utcnow()
    await add_op_log(db, s.assessment_id, current_user.id, "提交评分",
                     f"工作项#{s.work_item_id} 评分：{data.score}分")
    await db.commit()
    await db.refresh(s)
    return {"id": s.id, "score": s.score, "comment": s.comment,
            "scored_at": s.scored_at.isoformat() if s.scored_at else None}


# ===== 单条评分详情 =====

@router.get("/scores/{sid}", response_model=dict)
async def get_score(sid: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    r = await db.execute(
        select(AssessmentScore).options(
            selectinload(AssessmentScore.assessment),
            selectinload(AssessmentScore.work_item).selectinload(WorkItem.assignee).selectinload(User.department),
            selectinload(AssessmentScore.work_item).selectinload(WorkItem.assignee).selectinload(User.district),
            selectinload(AssessmentScore.scorer).selectinload(User.department),
            selectinload(AssessmentScore.scorer).selectinload(User.district),
        ).where(AssessmentScore.id == sid)
    )
    s = r.scalar_one_or_none()
    if not s: raise HTTPException(404, "评分记录不存在")

    wi = s.work_item
    assignee = wi.assignee if wi else None
    return {
        "id": s.id, "assessment_id": s.assessment_id, "work_item_id": s.work_item_id,
        "scorer_id": s.scorer_id, "scorer_role_level": s.scorer_role_level,
        "scorer_department_id": s.scorer_department_id,
        "scorer_district_id": s.scorer_district_id,
        "level": s.level, "score": s.score, "comment": s.comment,
        "scored_at": s.scored_at.isoformat() if s.scored_at else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "assessment_title": s.assessment.title if s.assessment else "",
        "work_item": {"id": wi.id, "title": wi.title, "content": wi.content, "status": wi.status} if wi else None,
        "assignee_name": (assignee.real_name or assignee.username) if assignee else "",
        "scorer": user_to_brief(s.scorer),
    }
