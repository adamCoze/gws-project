"""考核模块路由"""
import logging
from typing import Optional, List, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from auth import get_current_user, require_role
from models import (
    User,
    RoleLevel,
    WorkItem,
    Assessment,
    AssessmentStatus,
    ScoreLevel,
    Department,
)
from schemas import (
    PendingAssessmentItemOut,
    AssessmentListItemOut,
    AssessmentDetailOut,
    ScoreSubmitRequest,
    SupplementRequestCreate,
    SupplementSubmitRequest,
    SupplementRequestOut,
    NonAssessmentMarkRequest,
    NonAssessmentItemOut,
    SkipRuleInfoOut,
    InitiateAssessmentResponse,
    SuccessResponse,
)
from services.assessment_service import (
    get_pending_items,
    initiate_assessment,
    calculate_skip_rules,
    get_initial_status,
    get_dept_confirm_list,
    dept_confirm,
    dept_reject,
    get_to_score_list,
    submit_score,
    request_supplement,
    submit_supplement,
    get_assessment_detail,
    get_my_assessments,
    mark_non_assessment,
    revoke_non_assessment,
    get_non_assessment_list,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assessment", tags=["assessment"])


def _to_pending_item_out(item: WorkItem) -> dict:
    """将 WorkItem 转为待考核项输出格式"""
    return {
        "work_item_id": item.id,
        "title": item.title,
        "department_id": item.department_id,
        "department_name": item.department.name if item.department else None,
        "district_id": item.department.district_id if item.department else None,
        "district_name": item.department.district.name if item.department and item.department.district else None,
        "sponsor_id": item.sponsor_id,
        "sponsor_name": (item.sponsor.real_name or item.sponsor.username) if item.sponsor else None,
        "completed_at": item.completed_at,
        "has_email": bool(item.message_id),
        "email_url": None,
    }


# ======================================================================
# 待考核项
# ======================================================================


@router.get("/pending-items", response_model=dict)
async def list_pending_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None,
    department_id: Optional[int] = None,
    district_id: Optional[int] = None,
    month: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """待考核项清单（已完成、未发起考核、未标记非考核项）"""
    total, items = await get_pending_items(
        db, current_user, page, page_size, keyword, department_id, district_id, month
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_to_pending_item_out(item) for item in items],
    }


@router.get("/check-skip-rule/{work_item_id}", response_model=SkipRuleInfoOut)
async def check_skip_rule(
    work_item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询某个工作项的跳过情况（前端展示用）"""
    from sqlalchemy import select
    result = await db.execute(
        select(WorkItem).options(selectinload(WorkItem.sponsor)).where(WorkItem.id == work_item_id)
    )
    work_item = result.scalar_one_or_none()
    if not work_item:
        raise HTTPException(status_code=404, detail="工作项不存在")

    skip_dept, skip_district, skip_regulator, reason = await calculate_skip_rules(
        db, work_item, work_item.sponsor
    )
    initial_status = get_initial_status(skip_dept, skip_district, skip_regulator)

    return SkipRuleInfoOut(
        skip_dept_confirm=skip_dept,
        skip_district_score=skip_district,
        skip_regulator_score=skip_regulator,
        initial_status=initial_status,
        reason=reason,
    )


# ======================================================================
# 发起考核
# ======================================================================


@router.post("/initiate/{work_item_id}", response_model=InitiateAssessmentResponse)
async def initiate_assessment_api(
    work_item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发起考核"""
    try:
        assessment = await initiate_assessment(db, work_item_id, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    status_text = {
        AssessmentStatus.pending_dept_confirm.value: "待部门总监确认",
        AssessmentStatus.pending_district_score.value: "待区总评分",
        AssessmentStatus.pending_regulator_score.value: "待监察主任评分",
        AssessmentStatus.pending_group_score.value: "待集团总监评分",
    }.get(assessment.status, assessment.status)

    return InitiateAssessmentResponse(
        assessment_id=assessment.id,
        status=assessment.status,
        status_text=status_text,
        message="考核已发起",
    )


# ======================================================================
# 非考核项
# ======================================================================


@router.post("/non-assessment/{work_item_id}", response_model=SuccessResponse)
async def mark_non_assessment_api(
    work_item_id: int,
    data: Optional[NonAssessmentMarkRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标记为非考核项"""
    try:
        await mark_non_assessment(
            db, work_item_id, current_user,
            remark=data.remark if data else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SuccessResponse(success=True, message="已标记为非考核项")


@router.delete("/non-assessment/{work_item_id}", response_model=SuccessResponse)
async def revoke_non_assessment_api(
    work_item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(RoleLevel.DEPT_DIRECTOR)),
):
    """撤销非考核项标记（部门总监及以上）"""
    try:
        await revoke_non_assessment(db, work_item_id, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SuccessResponse(success=True, message="已撤销非考核项标记")


@router.get("/non-assessment", response_model=dict)
async def list_non_assessment(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = None,
    department_id: Optional[int] = None,
    district_id: Optional[int] = None,
    month: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """非考核项列表"""
    total, items = await get_non_assessment_list(
        db, current_user, page, page_size, keyword, department_id, district_id, month
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [NonAssessmentItemOut.model_validate(item).model_dump() for item in items],
    }


# ======================================================================
# 部门总监确认
# ======================================================================


@router.get("/to-confirm", response_model=dict)
async def list_to_confirm(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(RoleLevel.DEPT_DIRECTOR)),
):
    """待我确认的列表（部门总监）"""
    total, items = await get_dept_confirm_list(db, current_user, page, page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [AssessmentListItemOut.model_validate(item).model_dump() for item in items],
    }


@router.post("/{id}/dept-confirm", response_model=SuccessResponse)
async def dept_confirm_api(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(RoleLevel.DEPT_DIRECTOR)),
):
    """部门总监确认完成，流转到区总评分"""
    try:
        await dept_confirm(db, id, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SuccessResponse(success=True, message="确认完成")


@router.post("/{id}/dept-reject", response_model=SuccessResponse)
async def dept_reject_api(
    id: int,
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(RoleLevel.DEPT_DIRECTOR)),
):
    """部门总监退回（不确认），考核取消，工作项改回进行中"""
    try:
        await dept_reject(db, id, current_user, reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SuccessResponse(success=True, message="已退回")


# ======================================================================
# 评分流程
# ======================================================================


@router.get("/to-score", response_model=dict)
async def list_to_score(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(RoleLevel.DISTRICT_MANAGER)),
):
    """待我评分的列表（区总/监察/集团总监，按层级过滤）"""
    total, items = await get_to_score_list(db, current_user, page, page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [AssessmentListItemOut.model_validate(item).model_dump() for item in items],
    }


@router.post("/{id}/score", response_model=SuccessResponse)
async def submit_score_api(
    id: int,
    data: ScoreSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(RoleLevel.DISTRICT_MANAGER)),
):
    """提交评分（根据当前用户角色自动判断评分层级）"""
    # 根据当前用户角色确定评分层级
    user_level = current_user.role_level or 2
    score_level = None

    # 需要先获取考核记录，确认当前处于哪一层
    from sqlalchemy import select as sa_select
    result = await db.execute(sa_select(Assessment).where(Assessment.id == id))
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=404, detail="考核记录不存在")

    current_level = assessment.current_level

    # 校验当前用户是否有权限评当前层
    if current_level == ScoreLevel.district.value:
        if user_level < RoleLevel.DISTRICT_MANAGER:
            raise HTTPException(status_code=403, detail="无权限：需要区总及以上角色")
        score_level = ScoreLevel.district.value
    elif current_level == ScoreLevel.regulator.value:
        if user_level < RoleLevel.REGULATOR:
            raise HTTPException(status_code=403, detail="无权限：需要监察主任及以上角色")
        score_level = ScoreLevel.regulator.value
    elif current_level == ScoreLevel.group.value:
        if user_level < RoleLevel.GROUP_DIRECTOR:
            raise HTTPException(status_code=403, detail="无权限：需要集团总监及以上角色")
        score_level = ScoreLevel.group.value
    else:
        raise HTTPException(status_code=400, detail=f"当前状态（{assessment.status}）不允许评分")

    try:
        await submit_score(
            db,
            assessment_id=id,
            user=current_user,
            score_level=score_level,
            total_score=data.total_score,
            opinion=data.opinion,
            participants=data.participants,
            attachments=data.attachments,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return SuccessResponse(success=True, message="评分提交成功")


# ======================================================================
# 补充凭证
# ======================================================================


@router.post("/{id}/supplement-request", response_model=dict)
async def request_supplement_api(
    id: int,
    data: SupplementRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(RoleLevel.DISTRICT_MANAGER)),
):
    """要求补充凭证"""
    try:
        req = await request_supplement(db, id, current_user, data.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "success": True,
        "supplement_request_id": req.id,
        "message": "已要求补充凭证",
    }


@router.post("/{id}/supplement-submit", response_model=SuccessResponse)
async def submit_supplement_api(
    id: int,
    data: SupplementSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交补充凭证"""
    try:
        await submit_supplement(
            db,
            assessment_id=id,
            user=current_user,
            supplement_request_id=data.supplement_request_id,
            response=data.response,
            attachments=data.attachments,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SuccessResponse(success=True, message="补充凭证已提交")


# ======================================================================
# 考核详情
# ======================================================================


@router.get("/{id}", response_model=AssessmentDetailOut)
async def get_assessment_api(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """考核详情（含各层评分、附件、操作日志）"""
    assessment = await get_assessment_detail(db, id, current_user)
    if not assessment:
        raise HTTPException(status_code=404, detail="考核记录不存在或无权限查看")
    return assessment


@router.get("/my-assessments", response_model=dict)
async def my_assessments_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: Optional[str] = None,
    month: Optional[str] = None,
    keyword: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """我参与的考核列表（主办人视角）"""
    total, items = await get_my_assessments(
        db, current_user, page, page_size, status, month, keyword
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [AssessmentListItemOut.model_validate(item).model_dump() for item in items],
    }
