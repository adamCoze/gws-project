"""考核业务逻辑服务"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import (
    Assessment,
    AssessmentStatus,
    AssessmentScore,
    ScoreLevel,
    ScoreTier,
    AssessmentScoreParticipant,
    AssessmentAttachment,
    AttachmentType,
    AssessmentSupplementRequest,
    SupplementRequestStatus,
    AssessmentAppeal,
    NonAssessmentItem,
    AssessmentOperationLog,
    WorkItem,
    WorkItemStatus,
    User,
    RoleLevel,
    Department,
    District,
)

logger = logging.getLogger(__name__)


# ======================================================================
# 权限范围过滤
# ======================================================================


def get_data_scope_filter(user: User, table, prefix: str = ""):
    """根据用户角色返回数据范围过滤条件

    - admin/regulator+ (>=6): 全部
    - dept_director (5): 本部门
    - district_manager (4): 本区域
    - staff/manager (<=3): 仅自己主办的
    """
    dept_col = getattr(table, f"{prefix}department_id", None) or getattr(table, "department_id", None)
    district_col = getattr(table, f"{prefix}district_id", None) or getattr(table, "district_id", None)
    sponsor_col = getattr(table, f"{prefix}sponsor_id", None) or getattr(table, "sponsor_id", None)

    level = user.role_level or 2
    if level >= RoleLevel.REGULATOR:
        return None  # 全部
    elif level == RoleLevel.DEPT_DIRECTOR:
        return dept_col == user.department_id
    elif level == RoleLevel.DISTRICT_MANAGER:
        return district_col == user.district_id
    else:
        return sponsor_col == user.id


# ======================================================================
# 跳过规则
# ======================================================================


async def calculate_skip_rules(
    db: AsyncSession,
    work_item: WorkItem,
    sponsor: Optional[User] = None,
) -> Tuple[bool, bool, bool, str]:
    """计算某个工作项的跳过规则

    返回: (skip_dept_confirm, skip_district_score, skip_regulator_score, reason)
    """
    if sponsor is None:
        result = await db.execute(select(User).where(User.id == work_item.sponsor_id))
        sponsor = result.scalar_one_or_none()

    if not sponsor:
        return False, False, False, "无法获取主办人信息"

    sponsor_level = sponsor.role_level or 2
    sponsor_dept = sponsor.department_id
    work_item_dept = work_item.department_id

    skip_dept = False
    skip_district = False
    skip_regulator = False
    reasons = []

    # 集团总监作为主办人：跳过部门确认 + 区总评分 + 监察评分
    if sponsor_level >= RoleLevel.GROUP_DIRECTOR:
        skip_dept = True
        skip_district = True
        skip_regulator = True
        reasons.append("主办人为集团总监")
        return skip_dept, skip_district, skip_regulator, "；".join(reasons)

    # 主办人是部门总监/监察主任，且主办人部门 == 工作项部门
    # → 跳过部门总监确认和区总评分，直接由监察主任开始评分
    if sponsor_level >= RoleLevel.DEPT_DIRECTOR:
        if sponsor_dept and work_item_dept and sponsor_dept == work_item_dept:
            skip_dept = True
            skip_district = True
            if sponsor_level >= RoleLevel.REGULATOR:
                reasons.append("主办人为监察主任及以上且同部门")
            else:
                reasons.append("主办人为部门总监且同部门")
            return skip_dept, skip_district, skip_regulator, "；".join(reasons)

    # 工作项由部门总监及以上确认完成 → 跳过部门总监确认环节
    if work_item.completed_by:
        completer_result = await db.execute(
            select(User).where(User.id == work_item.completed_by)
        )
        completer = completer_result.scalar_one_or_none()
        if completer and completer.role_level >= RoleLevel.DEPT_DIRECTOR:
            skip_dept = True
            reasons.append("由部门总监及以上确认完成")

    return skip_dept, skip_district, skip_regulator, "；".join(reasons)


def get_initial_status(skip_dept: bool, skip_district: bool, skip_regulator: bool) -> str:
    """根据跳过规则返回初始状态"""
    if skip_regulator:
        return AssessmentStatus.pending_group_score.value
    if skip_district:
        return AssessmentStatus.pending_regulator_score.value
    if skip_dept:
        return AssessmentStatus.pending_district_score.value
    return AssessmentStatus.pending_dept_confirm.value


def get_current_level_from_status(status: str) -> Optional[str]:
    """从状态获取当前评分层级"""
    if status == AssessmentStatus.pending_district_score.value:
        return ScoreLevel.district.value
    if status == AssessmentStatus.pending_regulator_score.value:
        return ScoreLevel.regulator.value
    if status == AssessmentStatus.pending_group_score.value:
        return ScoreLevel.group.value
    return None


# ======================================================================
# 操作日志
# ======================================================================


async def add_operation_log(
    db: AsyncSession,
    assessment_id: Optional[int],
    work_item_id: int,
    operator_id: int,
    action: str,
    detail: Optional[str] = None,
):
    """添加操作日志"""
    log = AssessmentOperationLog(
        assessment_id=assessment_id,
        work_item_id=work_item_id,
        operator_id=operator_id,
        action=action,
        detail=detail,
    )
    db.add(log)


# ======================================================================
# 待考核项
# ======================================================================


async def get_pending_items(
    db: AsyncSession,
    user: User,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    department_id: Optional[int] = None,
    district_id: Optional[int] = None,
    month: Optional[str] = None,
) -> Tuple[int, List[WorkItem]]:
    """获取待考核项清单（已完成、未发起考核、未标记非考核项）"""

    # 基础条件：状态为completed
    query = select(WorkItem).where(WorkItem.status == WorkItemStatus.completed.value)

    # 排除已有考核记录的
    subq_assessed = select(Assessment.work_item_id).where(Assessment.status != AssessmentStatus.cancelled.value)
    query = query.where(WorkItem.id.not_in(subq_assessed))

    # 排除已标记为非考核项的
    subq_non = select(NonAssessmentItem.work_item_id).where(NonAssessmentItem.is_active == True)  # noqa
    query = query.where(WorkItem.id.not_in(subq_non))

    # 权限过滤
    level = user.role_level or 2
    if level >= RoleLevel.REGULATOR:
        pass  # 全部
    elif level == RoleLevel.DEPT_DIRECTOR:
        query = query.where(WorkItem.department_id == user.department_id)
    elif level == RoleLevel.DISTRICT_MANAGER:
        query = query.where(WorkItem.department_id.in_(
            select(Department.id).where(Department.district_id == user.district_id)
        ))
    else:
        query = query.where(WorkItem.sponsor_id == user.id)

    # 筛选
    if keyword:
        query = query.where(WorkItem.title.contains(keyword))
    if department_id:
        query = query.where(WorkItem.department_id == department_id)
    if district_id:
        query = query.where(WorkItem.department_id.in_(
            select(Department.id).where(Department.district_id == district_id)
        ))
    if month:
        # 按完成月份筛选
        # month格式: YYYY-MM
        from sqlalchemy import text as sa_text
        query = query.where(sa_text(
            "strftime('%Y-%m', completed_at) = :month"
        ).params(month=month))

    # 加载关联
    query = query.options(
        selectinload(WorkItem.department),
        selectinload(WorkItem.sponsor),
    )

    # 总数
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    # 分页
    query = query.order_by(WorkItem.completed_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return total, items


# ======================================================================
# 发起考核
# ======================================================================


async def initiate_assessment(
    db: AsyncSession,
    work_item_id: int,
    initiator: User,
) -> Assessment:
    """发起考核"""
    # 检查工作项
    result = await db.execute(
        select(WorkItem)
        .options(selectinload(WorkItem.department), selectinload(WorkItem.sponsor))
        .where(WorkItem.id == work_item_id)
    )
    work_item = result.scalar_one_or_none()
    if not work_item:
        raise ValueError("工作项不存在")

    if work_item.status != WorkItemStatus.completed.value:
        raise ValueError("只有已完成的工作项才能发起考核")

    # 检查是否已有进行中的考核
    existing_result = await db.execute(
        select(Assessment).where(
            Assessment.work_item_id == work_item_id,
            Assessment.status != AssessmentStatus.cancelled.value,
        )
    )
    if existing_result.scalar_one_or_none():
        raise ValueError("该工作项已有进行中的考核")

    # 检查是否为非考核项
    non_result = await db.execute(
        select(NonAssessmentItem).where(
            NonAssessmentItem.work_item_id == work_item_id,
            NonAssessmentItem.is_active == True,  # noqa
        )
    )
    if non_result.scalar_one_or_none():
        raise ValueError("该工作项已标记为非考核项")

    # 权限检查
    level = initiator.role_level or 2
    if level < RoleLevel.REGULATOR:
        if level == RoleLevel.DEPT_DIRECTOR:
            if work_item.department_id != initiator.department_id:
                raise ValueError("无权限发起其他部门的考核")
        elif level == RoleLevel.DISTRICT_MANAGER:
            # 检查是否属于本区域
            dept_result = await db.execute(
                select(Department.district_id).where(Department.id == work_item.department_id)
            )
            dept_row = dept_result.scalar_one_or_none()
            if dept_row != initiator.district_id:
                raise ValueError("无权限发起其他区域的考核")
        else:
            # 普通员工只能发起自己主办的
            if work_item.sponsor_id != initiator.id:
                raise ValueError("只能发起自己主办工作项的考核")

    # 获取主办人
    sponsor = work_item.sponsor
    if not sponsor and work_item.sponsor_id:
        sponsor_result = await db.execute(select(User).where(User.id == work_item.sponsor_id))
        sponsor = sponsor_result.scalar_one_or_none()

    # 计算跳过规则
    skip_dept, skip_district, skip_regulator, skip_reason = await calculate_skip_rules(
        db, work_item, sponsor
    )

    # 确定初始状态
    initial_status = get_initial_status(skip_dept, skip_district, skip_regulator)
    current_level = get_current_level_from_status(initial_status)

    # 获取区域ID
    district_id = None
    if work_item.department_id:
        dept_result = await db.execute(
            select(Department.district_id).where(Department.id == work_item.department_id)
        )
        district_id = dept_result.scalar_one_or_none()

    # 创建考核记录
    assessment = Assessment(
        work_item_id=work_item.id,
        initiator_id=initiator.id,
        sponsor_id=work_item.sponsor_id,
        department_id=work_item.department_id,
        district_id=district_id,
        status=initial_status,
        current_level=current_level,
        skip_dept_confirm=skip_dept,
        skip_district_score=skip_district,
        skip_regulator_score=skip_regulator,
        initiated_at=datetime.utcnow(),
    )
    db.add(assessment)
    await db.flush()

    # 操作日志
    await add_operation_log(
        db,
        assessment_id=assessment.id,
        work_item_id=work_item.id,
        operator_id=initiator.id,
        action="initiate",
        detail=f"发起考核，初始状态：{initial_status}。跳过规则：{skip_reason or '无'}",
    )

    await db.commit()
    await db.refresh(assessment)
    return assessment


# ======================================================================
# 部门总监确认
# ======================================================================


async def get_dept_confirm_list(
    db: AsyncSession,
    user: User,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[int, List[Assessment]]:
    """获取待部门总监确认的列表"""
    if user.role_level < RoleLevel.DEPT_DIRECTOR:
        return 0, []

    query = select(Assessment).where(
        Assessment.status == AssessmentStatus.pending_dept_confirm.value,
        Assessment.department_id == user.department_id,
    )

    query = query.options(
        selectinload(Assessment.work_item),
        selectinload(Assessment.sponsor),
        selectinload(Assessment.department),
        selectinload(Assessment.district),
    )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    query = query.order_by(Assessment.initiated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()
    return total, items


async def dept_confirm(
    db: AsyncSession,
    assessment_id: int,
    user: User,
) -> Assessment:
    """部门总监确认完成，流转到区总评分"""
    result = await db.execute(
        select(Assessment)
        .options(selectinload(Assessment.work_item))
        .where(Assessment.id == assessment_id)
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise ValueError("考核记录不存在")

    if assessment.status != AssessmentStatus.pending_dept_confirm.value:
        raise ValueError("当前状态不允许部门总监确认")

    if user.role_level < RoleLevel.DEPT_DIRECTOR:
        raise ValueError("无权限：需要部门总监及以上角色")

    # 部门总监只能确认本部门的
    if assessment.department_id != user.department_id:
        raise ValueError("无权限：只能确认本部门的考核项")

    # 流转到下一层
    if assessment.skip_district_score:
        next_status = AssessmentStatus.pending_regulator_score.value
        next_level = ScoreLevel.regulator.value
    else:
        next_status = AssessmentStatus.pending_district_score.value
        next_level = ScoreLevel.district.value

    assessment.status = next_status
    assessment.current_level = next_level
    assessment.updated_at = datetime.utcnow()

    await add_operation_log(
        db,
        assessment_id=assessment.id,
        work_item_id=assessment.work_item_id,
        operator_id=user.id,
        action="dept_confirm",
        detail=f"确认完成，流转到：{next_status}",
    )

    await db.commit()
    await db.refresh(assessment)
    return assessment


async def dept_reject(
    db: AsyncSession,
    assessment_id: int,
    user: User,
    reason: Optional[str] = None,
) -> Assessment:
    """部门总监退回（不确认），考核取消，工作项改回进行中"""
    result = await db.execute(
        select(Assessment)
        .options(selectinload(Assessment.work_item))
        .where(Assessment.id == assessment_id)
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise ValueError("考核记录不存在")

    if assessment.status != AssessmentStatus.pending_dept_confirm.value:
        raise ValueError("当前状态不允许退回")

    if user.role_level < RoleLevel.DEPT_DIRECTOR:
        raise ValueError("无权限：需要部门总监及以上角色")

    if assessment.department_id != user.department_id:
        raise ValueError("无权限：只能退回本部门的考核项")

    # 取消考核
    assessment.status = AssessmentStatus.cancelled.value
    assessment.current_level = None
    assessment.updated_at = datetime.utcnow()

    # 工作项改回进行中
    if assessment.work_item:
        assessment.work_item.status = WorkItemStatus.pending.value
        assessment.work_item.updated_at = datetime.utcnow()

    await add_operation_log(
        db,
        assessment_id=assessment.id,
        work_item_id=assessment.work_item_id,
        operator_id=user.id,
        action="dept_reject",
        detail=f"退回原因：{reason or '未说明'}，工作项改回进行中",
    )

    await db.commit()
    await db.refresh(assessment)
    return assessment


# ======================================================================
# 评分流程
# ======================================================================


async def get_to_score_list(
    db: AsyncSession,
    user: User,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[int, List[Assessment]]:
    """获取待我评分的列表（按角色层级过滤）"""
    level = user.role_level or 2

    # 确定当前用户能评哪一层
    target_level = None
    status_target = None
    if level == RoleLevel.DISTRICT_MANAGER:
        target_level = ScoreLevel.district.value
        status_target = AssessmentStatus.pending_district_score.value
    elif level == RoleLevel.REGULATOR:
        target_level = ScoreLevel.regulator.value
        status_target = AssessmentStatus.pending_regulator_score.value
    elif level >= RoleLevel.GROUP_DIRECTOR:
        target_level = ScoreLevel.group.value
        status_target = AssessmentStatus.pending_group_score.value
    else:
        return 0, []

    query = select(Assessment).where(Assessment.status == status_target)

    # 区总只能看到本区域的
    if level == RoleLevel.DISTRICT_MANAGER:
        query = query.where(Assessment.district_id == user.district_id)

    query = query.options(
        selectinload(Assessment.work_item),
        selectinload(Assessment.sponsor),
        selectinload(Assessment.department),
        selectinload(Assessment.district),
    )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    query = query.order_by(Assessment.initiated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()
    return total, items


def validate_score(total_score: int, participants: list) -> Tuple[bool, str]:
    """校验评分参数：总分档位 + 参与人分配和"""
    if total_score not in ScoreTier.TIERS:
        return False, f"总分必须是以下档位之一：{sorted(ScoreTier.TIERS)}"

    if participants:
        total_allocated = sum(p["score"] if isinstance(p, dict) else p.score for p in participants)
        # 浮点数比较，允许0.01误差
        if abs(total_allocated - total_score) > 0.01:
            return False, f"参与人分配总分({total_allocated})必须等于总分({total_score})"

    return True, ""


async def submit_score(
    db: AsyncSession,
    assessment_id: int,
    user: User,
    score_level: str,
    total_score: int,
    opinion: Optional[str] = None,
    participants: Optional[list] = None,
    attachments: Optional[list] = None,
) -> Assessment:
    """提交评分"""
    participants = participants or []
    attachments = attachments or []

    # 校验总分档位
    valid, msg = validate_score(total_score, participants)
    if not valid:
        raise ValueError(msg)

    # 获取考核记录
    result = await db.execute(
        select(Assessment)
        .options(
            selectinload(Assessment.work_item),
            selectinload(Assessment.scores),
        )
        .where(Assessment.id == assessment_id)
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise ValueError("考核记录不存在")

    # 校验状态
    expected_status_map = {
        ScoreLevel.district.value: AssessmentStatus.pending_district_score.value,
        ScoreLevel.regulator.value: AssessmentStatus.pending_regulator_score.value,
        ScoreLevel.group.value: AssessmentStatus.pending_group_score.value,
    }
    expected_status = expected_status_map.get(score_level)
    if assessment.status != expected_status:
        raise ValueError(f"当前状态为{assessment.status}，不能进行{score_level}层评分")

    # 检查该层是否已有评分（幂等性 + 不可修改保证）
    existing_score = None
    for s in assessment.scores:
        if s.level == score_level:
            existing_score = s
            break
    if existing_score:
        raise ValueError("该层评分已提交，不可修改")

    # 权限校验
    user_level = user.role_level or 2
    if score_level == ScoreLevel.district.value:
        if user_level < RoleLevel.DISTRICT_MANAGER:
            raise ValueError("无权限：需要区总及以上角色")
        # 区总只能评本区域的
        if user_level == RoleLevel.DISTRICT_MANAGER and assessment.district_id != user.district_id:
            raise ValueError("无权限：只能评分本区域的考核项")
    elif score_level == ScoreLevel.regulator.value:
        if user_level < RoleLevel.REGULATOR:
            raise ValueError("无权限：需要监察主任及以上角色")
    elif score_level == ScoreLevel.group.value:
        if user_level < RoleLevel.GROUP_DIRECTOR:
            raise ValueError("无权限：需要集团总监及以上角色")

    # 创建评分记录
    score = AssessmentScore(
        assessment_id=assessment.id,
        level=score_level,
        scorer_id=user.id,
        total_score=total_score,
        opinion=opinion,
        submitted_at=datetime.utcnow(),
    )
    db.add(score)
    await db.flush()

    # 创建参与人分配
    if participants:
        for p in participants:
            p_dict = p if isinstance(p, dict) else p.model_dump()
            # 获取用户名
            user_result = await db.execute(select(User).where(User.id == p_dict["user_id"]))
            u = user_result.scalar_one_or_none()
            user_name = u.real_name if u and u.real_name else (u.username if u else "")
            participant = AssessmentScoreParticipant(
                score_id=score.id,
                user_id=p_dict["user_id"],
                user_name=user_name,
                score=p_dict["score"],
            )
            db.add(participant)

    # 创建附件
    if attachments:
        for att in attachments:
            att_dict = att if isinstance(att, dict) else att.model_dump()
            attachment = AssessmentAttachment(
                assessment_id=assessment.id,
                type=AttachmentType.scoring.value,
                score_id=score.id,
                uploader_id=user.id,
                file_type=att_dict.get("file_type", "image"),
                file_name=att_dict.get("file_name"),
                file_path=att_dict.get("file_path"),
                content=att_dict.get("content"),
            )
            db.add(attachment)

    # 状态流转
    action_map = {
        ScoreLevel.district.value: "district_score",
        ScoreLevel.regulator.value: "regulator_score",
        ScoreLevel.group.value: "group_score",
    }

    if score_level == ScoreLevel.district.value:
        # 区总 → 监察
        next_status = AssessmentStatus.pending_regulator_score.value
        next_level = ScoreLevel.regulator.value
    elif score_level == ScoreLevel.regulator.value:
        # 监察 → 集团总监
        if assessment.skip_regulator_score:
            # 理论上不会到这里，跳过的话不会有regulator层
            next_status = AssessmentStatus.pending_group_score.value
            next_level = ScoreLevel.group.value
        else:
            next_status = AssessmentStatus.pending_group_score.value
            next_level = ScoreLevel.group.value
    else:  # group
        # 集团总监 → 异议期
        next_status = AssessmentStatus.appeal_period.value
        next_level = None
        # 设置异议截止时间（次日起3个工作日）
        assessment.appeal_deadline = _calculate_appeal_deadline(datetime.utcnow())
        assessment.final_score = total_score

    assessment.status = next_status
    assessment.current_level = next_level
    assessment.updated_at = datetime.utcnow()

    # 操作日志
    await add_operation_log(
        db,
        assessment_id=assessment.id,
        work_item_id=assessment.work_item_id,
        operator_id=user.id,
        action=action_map.get(score_level, "score"),
        detail=f"{score_level}层评分：{total_score}分，流转到：{next_status}",
    )

    await db.commit()
    await db.refresh(assessment)
    return assessment


def _calculate_appeal_deadline(from_date: datetime) -> datetime:
    """计算异议截止时间：从次日起3个工作日"""
    current = from_date + timedelta(days=1)
    current = current.replace(hour=23, minute=59, second=59, microsecond=0)
    workdays_found = 0
    while workdays_found < 3:
        # 简单处理：周一到周五为工作日
        # 后续可接入holidays表
        if current.weekday() < 5:  # 0-4 = 周一到周五
            workdays_found += 1
        if workdays_found < 3:
            current += timedelta(days=1)
    return current


# ======================================================================
# 补充凭证
# ======================================================================


async def request_supplement(
    db: AsyncSession,
    assessment_id: int,
    user: User,
    note: str,
) -> AssessmentSupplementRequest:
    """要求补充凭证"""
    result = await db.execute(
        select(Assessment).options(selectinload(Assessment.work_item))
        .where(Assessment.id == assessment_id)
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise ValueError("考核记录不存在")

    # 检查当前状态是否可以要求补充
    valid_statuses = [
        AssessmentStatus.pending_district_score.value,
        AssessmentStatus.pending_regulator_score.value,
        AssessmentStatus.pending_group_score.value,
    ]
    if assessment.status not in valid_statuses:
        raise ValueError("当前状态不允许要求补充凭证")

    current_level = assessment.current_level
    user_level = user.role_level or 2

    # 权限：当前层评分人才能要求补充
    if current_level == ScoreLevel.district.value:
        if user_level < RoleLevel.DISTRICT_MANAGER:
            raise ValueError("无权限：区总层评分只能由区总要求补充")
        if user_level == RoleLevel.DISTRICT_MANAGER and assessment.district_id != user.district_id:
            raise ValueError("无权限：只能要求本区域考核项的补充")
    elif current_level == ScoreLevel.regulator.value:
        if user_level < RoleLevel.REGULATOR:
            raise ValueError("无权限：监察层评分只能由监察主任要求补充")
    elif current_level == ScoreLevel.group.value:
        if user_level < RoleLevel.GROUP_DIRECTOR:
            raise ValueError("无权限：集团层评分只能由集团总监要求补充")

    # 创建补充请求
    req = AssessmentSupplementRequest(
        assessment_id=assessment.id,
        requester_id=user.id,
        request_level=current_level,
        request_note=note,
        status=SupplementRequestStatus.pending.value,
    )
    db.add(req)

    # 状态变为待补充
    prev_status = assessment.status
    assessment.status = AssessmentStatus.pending_supplement.value
    assessment.supplement_by_level = current_level
    assessment.updated_at = datetime.utcnow()

    await add_operation_log(
        db,
        assessment_id=assessment.id,
        work_item_id=assessment.work_item_id,
        operator_id=user.id,
        action="request_supplement",
        detail=f"要求补充凭证（{current_level}层）：{note}，原状态：{prev_status}",
    )

    await db.commit()
    await db.refresh(req)
    return req


async def submit_supplement(
    db: AsyncSession,
    assessment_id: int,
    user: User,
    supplement_request_id: int,
    response: Optional[str] = None,
    attachments: Optional[list] = None,
) -> Assessment:
    """提交补充凭证"""
    attachments = attachments or []

    result = await db.execute(
        select(Assessment).options(selectinload(Assessment.work_item))
        .where(Assessment.id == assessment_id)
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise ValueError("考核记录不存在")

    if assessment.status != AssessmentStatus.pending_supplement.value:
        raise ValueError("当前状态不需要补充凭证")

    # 只能主办人补充
    if assessment.sponsor_id != user.id and user.role_level < RoleLevel.REGULATOR:
        raise ValueError("无权限：只能由主办人提交补充凭证")

    # 获取补充请求
    req_result = await db.execute(
        select(AssessmentSupplementRequest).where(
            AssessmentSupplementRequest.id == supplement_request_id,
            AssessmentSupplementRequest.assessment_id == assessment_id,
        )
    )
    req = req_result.scalar_one_or_none()
    if not req:
        raise ValueError("补充请求不存在")

    if req.status != SupplementRequestStatus.pending.value:
        raise ValueError("该补充请求已处理")

    # 标记为已补充
    req.status = SupplementRequestStatus.completed.value
    req.submitted_at = datetime.utcnow()
    req.supplier_id = user.id

    # 创建附件
    for att in attachments:
        att_dict = att if isinstance(att, dict) else att.model_dump()
        attachment = AssessmentAttachment(
            assessment_id=assessment.id,
            type=AttachmentType.supplement.value,
            supplement_request_id=req.id,
            uploader_id=user.id,
            file_type=att_dict.get("file_type", "image"),
            file_name=att_dict.get("file_name"),
            file_path=att_dict.get("file_path"),
            content=att_dict.get("content"),
        )
        db.add(attachment)

    # 回到要求补充的那一层继续
    back_level = assessment.supplement_by_level
    status_map = {
        ScoreLevel.district.value: AssessmentStatus.pending_district_score.value,
        ScoreLevel.regulator.value: AssessmentStatus.pending_regulator_score.value,
        ScoreLevel.group.value: AssessmentStatus.pending_group_score.value,
    }
    back_status = status_map.get(back_level, AssessmentStatus.pending_district_score.value)
    assessment.status = back_status
    assessment.current_level = back_level
    assessment.supplement_by_level = None
    assessment.updated_at = datetime.utcnow()

    await add_operation_log(
        db,
        assessment_id=assessment.id,
        work_item_id=assessment.work_item_id,
        operator_id=user.id,
        action="submit_supplement",
        detail=f"提交补充凭证，回到{back_level}层继续评分。补充说明：{response or '无'}",
    )

    await db.commit()
    await db.refresh(assessment)
    return assessment


# ======================================================================
# 考核详情
# ======================================================================


async def get_assessment_detail(
    db: AsyncSession,
    assessment_id: int,
    user: User,
) -> Optional[Assessment]:
    """获取考核详情（含权限校验）"""
    result = await db.execute(
        select(Assessment)
        .options(
            selectinload(Assessment.work_item),
            selectinload(Assessment.initiator),
            selectinload(Assessment.sponsor),
            selectinload(Assessment.department),
            selectinload(Assessment.district),
            selectinload(Assessment.scores).selectinload(AssessmentScore.scorer),
            selectinload(Assessment.scores).selectinload(AssessmentScore.participants),
            selectinload(Assessment.scores).selectinload(AssessmentScore.attachments).selectinload(AssessmentAttachment.uploader),
            selectinload(Assessment.supplement_requests).selectinload(AssessmentSupplementRequest.requester),
            selectinload(Assessment.supplement_requests).selectinload(AssessmentSupplementRequest.supplier),
            selectinload(Assessment.supplement_requests).selectinload(AssessmentSupplementRequest.attachments).selectinload(AssessmentAttachment.uploader),
            selectinload(Assessment.operation_logs).selectinload(AssessmentOperationLog.operator),
        )
        .where(Assessment.id == assessment_id)
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        return None

    # 权限校验
    level = user.role_level or 2
    if level >= RoleLevel.REGULATOR:
        return assessment
    if level == RoleLevel.DEPT_DIRECTOR:
        if assessment.department_id == user.department_id:
            return assessment
    elif level == RoleLevel.DISTRICT_MANAGER:
        if assessment.district_id == user.district_id:
            return assessment
    else:
        # 普通员工：只能看自己主办的
        if assessment.sponsor_id == user.id:
            return assessment

    return None  # 无权限


async def get_my_assessments(
    db: AsyncSession,
    user: User,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    month: Optional[str] = None,
    keyword: Optional[str] = None,
) -> Tuple[int, List[Assessment]]:
    """获取我主办的考核列表"""
    query = select(Assessment).where(Assessment.sponsor_id == user.id)

    if status:
        query = query.where(Assessment.status == status)
    if keyword:
        query = query.where(
            Assessment.work_item.has(WorkItem.title.contains(keyword))
        )
    if month:
        from sqlalchemy import text as sa_text
        query = query.where(sa_text(
            "strftime('%Y-%m', initiated_at) = :month"
        ).params(month=month))

    query = query.options(
        selectinload(Assessment.work_item),
        selectinload(Assessment.sponsor),
        selectinload(Assessment.department),
        selectinload(Assessment.district),
    )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    query = query.order_by(Assessment.initiated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()
    return total, items


# ======================================================================
# 非考核项
# ======================================================================


async def mark_non_assessment(
    db: AsyncSession,
    work_item_id: int,
    user: User,
    remark: Optional[str] = None,
) -> NonAssessmentItem:
    """标记为非考核项"""
    # 检查工作项
    wi_result = await db.execute(select(WorkItem).where(WorkItem.id == work_item_id))
    work_item = wi_result.scalar_one_or_none()
    if not work_item:
        raise ValueError("工作项不存在")

    # 权限检查
    level = user.role_level or 2
    if level < RoleLevel.REGULATOR:
        if level == RoleLevel.DEPT_DIRECTOR:
            if work_item.department_id != user.department_id:
                raise ValueError("无权限：只能标记本部门的工作项")
        elif level == RoleLevel.DISTRICT_MANAGER:
            # 检查区域
            dept_result = await db.execute(
                select(Department.district_id).where(Department.id == work_item.department_id)
            )
            dept_dist = dept_result.scalar_one_or_none()
            if dept_dist != user.district_id:
                raise ValueError("无权限：只能标记本区域的工作项")
        else:
            if work_item.sponsor_id != user.id:
                raise ValueError("无权限：只能标记自己主办的工作项")

    # 检查是否有进行中的考核
    assess_result = await db.execute(
        select(Assessment).where(
            Assessment.work_item_id == work_item_id,
            Assessment.status != AssessmentStatus.cancelled.value,
        )
    )
    if assess_result.scalar_one_or_none():
        raise ValueError("该工作项已有进行中的考核，不能标记为非考核项")

    # 检查是否已标记
    existing_result = await db.execute(
        select(NonAssessmentItem).where(NonAssessmentItem.work_item_id == work_item_id)
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        if existing.is_active:
            raise ValueError("该工作项已标记为非考核项")
        else:
            # 已撤销的，重新激活
            existing.is_active = True
            existing.marked_by = user.id
            existing.remark = remark
            existing.revoked_by = None
            existing.revoked_at = None
            existing.created_at = datetime.utcnow()
            item = existing
    else:
        item = NonAssessmentItem(
            work_item_id=work_item_id,
            marked_by=user.id,
            remark=remark,
            is_active=True,
        )
        db.add(item)

    await add_operation_log(
        db,
        assessment_id=None,
        work_item_id=work_item_id,
        operator_id=user.id,
        action="mark_non_assessment",
        detail=f"标记为非考核项。备注：{remark or '无'}",
    )

    await db.commit()
    await db.refresh(item)
    return item


async def revoke_non_assessment(
    db: AsyncSession,
    work_item_id: int,
    user: User,
) -> NonAssessmentItem:
    """撤销非考核项标记"""
    result = await db.execute(
        select(NonAssessmentItem)
        .options(selectinload(NonAssessmentItem.work_item))
        .where(NonAssessmentItem.work_item_id == work_item_id)
    )
    item = result.scalar_one_or_none()
    if not item or not item.is_active:
        raise ValueError("非考核项标记不存在或已撤销")

    # 部门总监及以上可撤销
    level = user.role_level or 2
    if level < RoleLevel.DEPT_DIRECTOR:
        raise ValueError("无权限：需要部门总监及以上角色")

    # 部门总监只能撤销本部门的
    if level == RoleLevel.DEPT_DIRECTOR:
        if item.work_item and item.work_item.department_id != user.department_id:
            raise ValueError("无权限：只能撤销本部门的非考核项")

    item.is_active = False
    item.revoked_by = user.id
    item.revoked_at = datetime.utcnow()

    await add_operation_log(
        db,
        assessment_id=None,
        work_item_id=work_item_id,
        operator_id=user.id,
        action="revoke_non_assessment",
        detail="撤销非考核项标记",
    )

    await db.commit()
    await db.refresh(item)
    return item


async def get_non_assessment_list(
    db: AsyncSession,
    user: User,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    department_id: Optional[int] = None,
    district_id: Optional[int] = None,
    month: Optional[str] = None,
) -> Tuple[int, List[NonAssessmentItem]]:
    """获取非考核项列表"""
    query = select(NonAssessmentItem).where(NonAssessmentItem.is_active == True)  # noqa

    # 权限过滤
    level = user.role_level or 2
    if level >= RoleLevel.REGULATOR:
        pass
    elif level == RoleLevel.DEPT_DIRECTOR:
        query = query.where(
            NonAssessmentItem.work_item.has(WorkItem.department_id == user.department_id)
        )
    elif level == RoleLevel.DISTRICT_MANAGER:
        query = query.where(
            NonAssessmentItem.work_item.has(
                WorkItem.department_id.in_(
                    select(Department.id).where(Department.district_id == user.district_id)
                )
            )
        )
    else:
        query = query.where(
            NonAssessmentItem.work_item.has(WorkItem.sponsor_id == user.id)
        )

    if keyword:
        query = query.where(
            NonAssessmentItem.work_item.has(WorkItem.title.contains(keyword))
        )
    if department_id:
        query = query.where(
            NonAssessmentItem.work_item.has(WorkItem.department_id == department_id)
        )
    if district_id:
        query = query.where(
            NonAssessmentItem.work_item.has(
                WorkItem.department_id.in_(
                    select(Department.id).where(Department.district_id == district_id)
                )
            )
        )
    if month:
        from sqlalchemy import text as sa_text
        query = query.where(
            sa_text("strftime('%Y-%m', non_assessment_items.created_at) = :month").params(month=month)
        )

    query = query.options(
        selectinload(NonAssessmentItem.work_item),
        selectinload(NonAssessmentItem.marker),
    )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    query = query.order_by(NonAssessmentItem.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()
    return total, items
