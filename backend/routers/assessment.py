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
    AppealSubmitRequest,
    AppealCommentRequest,
    RulingSubmitRequest,
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
    submit_appeal,
    submit_appeal_comment,
    get_pending_ruling_list,
    submit_ruling,
    get_all_assessments,
    export_assessments_excel,
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


# ======================================================================
# 异议
# ======================================================================


@router.post("/{id}/appeal", response_model=dict)
async def submit_appeal_api(
    id: int,
    data: AppealSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """主办人发起异议"""
    try:
        appeal = await submit_appeal(db, id, current_user, data.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "success": True,
        "message": "异议已提交",
        "appeal_id": appeal.id,
    }


@router.post("/{id}/appeal-comment", response_model=dict)
async def submit_appeal_comment_api(
    id: int,
    data: AppealCommentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """监察主任/集团总监对异议提交补充意见（作为裁定参考材料）"""
    try:
        appeal = await submit_appeal_comment(db, id, current_user, data.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "success": True,
        "message": "补充意见已提交",
        "appeal_id": appeal.id,
    }


# ======================================================================
# 最终裁定
# ======================================================================


@router.get("/to-ruling", response_model=dict)
async def list_to_ruling(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(RoleLevel.GROUP_DIRECTOR)),
):
    """待裁定列表（集团总监及以上）"""
    total, items = await get_pending_ruling_list(db, current_user, page, page_size)
    rows = []
    for item in items:
        out = AssessmentListItemOut.model_validate(item).model_dump()
        out["has_appeal"] = item.appeal is not None  # 区分：有异议待裁定 / 异议期满自动流转
        rows.append(out)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": rows,
    }


@router.post("/{id}/ruling", response_model=SuccessResponse)
async def submit_ruling_api(
    id: int,
    data: RulingSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """最终裁定（集团总监及以上，代录总裁线下裁定结果）

    - maintain：维持原评分
    - adjust：调整分数（档位内）+ 裁定意见必填
    """
    try:
        await submit_ruling(
            db, id, current_user,
            ruling_action=data.ruling_action,
            adjusted_score=data.adjusted_score,
            comment=data.comment or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SuccessResponse(success=True, message="裁定完成，考核已完结")


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

    # 脱敏：AI审查意见、各层补充意见仅监察主任及以上可见；员工仅见自己的异议理由与裁定结果
    from models import RoleLevel as _RL
    from services.assessment_service import _get_effective_role_level
    if _get_effective_role_level(current_user) < _RL.REGULATOR and assessment.appeal:
        db.expunge(assessment)  # 脱离session，改动不会写库
        appeal = assessment.appeal
        appeal.ai_opinions = []
        appeal.ai_status = "hidden"
        appeal.regulator_comment = None
        appeal.group_director_comment = None

    return assessment


# ======================================================================
# 附件上传（评分凭证/补充凭证/异议凭证 图片上传）
# ======================================================================

import os
import uuid
from fastapi import UploadFile, File

ATTACHMENT_ROOT = os.environ.get("ATTACHMENT_ROOT", "/app/data/assessment-attachments")
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/upload-attachment", response_model=dict)
async def upload_attachment(
    assessment_id: int,
    type: str = "scoring",
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传凭证图片，返回 file_path 供评分/补充提交时引用"""
    if type not in ("scoring", "supplement", "appeal"):
        raise HTTPException(status_code=400, detail="无效的凭证类型")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(status_code=400, detail="仅支持图片格式: jpg/png/gif/webp/bmp")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件不能超过10MB")

    dir_path = os.path.join(ATTACHMENT_ROOT, str(assessment_id), type)
    os.makedirs(dir_path, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
    file_path = os.path.join(dir_path, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    rel_path = f"/api/assessment-attachments/{assessment_id}/{type}/{safe_name}"
    logger.info(f"用户{current_user.id}上传凭证: {rel_path} ({len(content)}字节)")
    return {
        "success": True,
        "file_type": "image",
        "file_name": file.filename,
        "file_path": rel_path,
    }


# ======================================================================
# 管理员：全集团考核管理
# ======================================================================

@router.get("/admin/all")
async def admin_all_assessments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    month: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    district_id: Optional[int] = Query(None),
    department_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(RoleLevel.REGULATOR)),
):
    """全集团考核列表（需监察主任及以上权限）"""
    total, items = await get_all_assessments(
        db=db, page=page, page_size=page_size,
        month=month, status=status,
        district_id=district_id, department_id=department_id,
        keyword=keyword,
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": a.id,
                "work_item_id": a.work_item_id,
                "work_item_no": a.work_item.item_no if a.work_item else "",
                "title": a.work_item.title if a.work_item else "",
                "sponsor_id": a.sponsor_id,
                "sponsor_name": a.sponsor.name if a.sponsor else "",
                "department_id": a.department_id,
                "department_name": a.department.name if a.department else "",
                "district_id": a.district_id,
                "district_name": a.district.name if a.district else "",
                "status": a.status,
                "initiated_at": a.initiated_at.isoformat() if a.initiated_at else None,
                "scores": [
                    {
                        "level": s.level,
                        "total_score": s.total_score,
                    } for s in (a.scores or [])
                ],
            }
            for a in items
        ],
    }


@router.get("/admin/export")
async def admin_export_assessments(
    month: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    district_id: Optional[int] = Query(None),
    department_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(RoleLevel.REGULATOR)),
):
    """导出全集团考核 Excel（需监察主任及以上权限）"""
    from fastapi.responses import StreamingResponse
    from io import BytesIO
    from datetime import datetime as dt

    excel_data = await export_assessments_excel(
        db=db,
        month=month, status=status,
        district_id=district_id, department_id=department_id,
        keyword=keyword,
    )
    filename = f"考核项目_{month or '全部'}_{dt.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        BytesIO(excel_data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ======================================================================
# 附件上传（评分凭证/补充凭证/异议凭证 图片上传）
# ======================================================================

import os
import uuid
from fastapi import UploadFile, File

ATTACHMENT_ROOT = os.environ.get("ATTACHMENT_ROOT", "/app/data/assessment-attachments")
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/upload-attachment", response_model=dict)
async def upload_attachment(
    assessment_id: int,
    type: str = "scoring",
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传凭证图片，返回 file_path 供评分/补充提交时引用"""
    if type not in ("scoring", "supplement", "appeal"):
        raise HTTPException(status_code=400, detail="无效的凭证类型")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(status_code=400, detail="仅支持图片格式: jpg/png/gif/webp/bmp")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件不能超过10MB")

    dir_path = os.path.join(ATTACHMENT_ROOT, str(assessment_id), type)
    os.makedirs(dir_path, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
    file_path = os.path.join(dir_path, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    rel_path = f"/api/assessment-attachments/{assessment_id}/{type}/{safe_name}"
    logger.info(f"用户{current_user.id}上传凭证: {rel_path} ({len(content)}字节)")
    return {
        "success": True,
        "file_type": "image",
        "file_name": file.filename,
        "file_path": rel_path,
    }
