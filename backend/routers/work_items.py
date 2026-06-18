"""工作项路由"""
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import WorkItem, WorkItemStatus, Department, User, StatusChangeLog
from schemas import (
    WorkItemCreate, WorkItemUpdate, WorkItemOut,
    StatusChangeRequest, StatusChangeLogOut,
)
from auth import get_current_user, ROLE_LEVELS
from models import RoleType

router = APIRouter(prefix="/work-items", tags=["work-items"])

# 人事/商务部ID
HR_COMMERCE_DEPT_ID = 1

# 允许变更状态的角色
STATUS_CHANGE_ROLES = {RoleType.regulator, RoleType.president, RoleType.admin}
# 人事/商务部中允许变更状态的角色
HR_COMMERCE_ALLOWED = {RoleType.manager, RoleType.staff}


def can_change_status(user: User) -> bool:
    """检查用户是否有权限变更工作项状态"""
    user_role = RoleType(user.role) if isinstance(user.role, str) else user.role
    # 规管、总裁、管理员始终可以
    if user_role in STATUS_CHANGE_ROLES:
        return True
    # 人事/商务部的经理和专员可以
    if user_role in HR_COMMERCE_ALLOWED and user.department_id == HR_COMMERCE_DEPT_ID:
        return True
    return False


@router.get("", response_model=List[WorkItemOut])
async def list_work_items(
    status: Optional[str] = None,
    department_id: Optional[int] = None,
    assignee_id: Optional[int] = None,
    assignee_email_prefix: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取工作项列表"""
    query = select(WorkItem).options(
        selectinload(WorkItem.department),
        selectinload(WorkItem.assignee),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
    )

    if status:
        query = query.where(WorkItem.status == status)
    if department_id:
        query = query.where(WorkItem.department_id == department_id)
    if assignee_id:
        query = query.where(WorkItem.assignee_id == assignee_id)
    if assignee_email_prefix:
        # 支持多个邮箱前缀（逗号分隔）
        email_prefixes = [ep.strip() for ep in assignee_email_prefix.split(',')]
        conditions = [WorkItem.assignee_email_prefix.contains(ep) for ep in email_prefixes]
        query = query.where(or_(*conditions))
    if keyword:
        query = query.where(WorkItem.title.contains(keyword))

    query = query.order_by(WorkItem.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()
    # 计算派生状态：pending 且过期 → overdue
    now = datetime.utcnow()
    for item in items:
        if item.status == "pending" and item.due_date and item.due_date < now:
            item.status = "overdue"
    return items


@router.get("/my", response_model=List[WorkItemOut])
async def list_my_work_items(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的工作项"""
    query = select(WorkItem).options(
        selectinload(WorkItem.department),
        selectinload(WorkItem.assignee),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
    )

    # 查找分配给当前用户的工作项（通过 assignee_id 或 assignee_email_prefix）
    conditions = []
    if current_user.id:
        conditions.append(WorkItem.assignee_id == current_user.id)
    if current_user.email_prefix:
        conditions.append(WorkItem.assignee_email_prefix.contains(current_user.email_prefix))

    if conditions:
        query = query.where(or_(*conditions))

    query = query.order_by(WorkItem.created_at.desc())
    result = await db.execute(query)
    items = result.scalars().all()
    # 计算派生状态：pending 且过期 → overdue
    now = datetime.utcnow()
    for item in items:
        if item.status == "pending" and item.due_date and item.due_date < now:
            item.status = "overdue"
    return items


@router.get("/{item_id}", response_model=WorkItemOut)
async def get_work_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """获取单个工作项"""
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")
    # 计算派生状态：pending 且过期 → overdue
    now = datetime.utcnow()
    if item.status == "pending" and item.due_date and item.due_date < now:
        item.status = "overdue"
    return item


@router.post("", response_model=WorkItemOut, status_code=201)
async def create_work_item(data: WorkItemCreate, db: AsyncSession = Depends(get_db)):
    """创建工作项"""
    item = WorkItem(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # 重新加载关系
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item.id)
    )
    item = result.scalar_one()
    now = datetime.utcnow()
    if item.status == "pending" and item.due_date and item.due_date < now:
        item.status = "overdue"
    return item


@router.put("/{item_id}", response_model=WorkItemOut)
async def update_work_item(
    item_id: int, data: WorkItemUpdate, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新工作项"""
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")

    update_data = data.model_dump(exclude_unset=True)

    # 如果状态变更，检查权限；无权限或尝试设置overdue则静默忽略状态字段
    if "status" in update_data and update_data["status"] != item.status:
        if update_data["status"] == "overdue":
            update_data.pop("status", None)
        elif not can_change_status(current_user):
            update_data.pop("status", None)
        else:
            log = StatusChangeLog(
                work_item_id=item.id,
                old_status=item.status,
                new_status=update_data["status"],
                operator_id=current_user.id,
                remark="通过编辑更新状态",
            )
            db.add(log)

    for key, value in update_data.items():
        setattr(item, key, value)

    item.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(item)

    # 重新加载关系
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item.id)
    )
    item = result.scalar_one()
    now = datetime.utcnow()
    if item.status == "pending" and item.due_date and item.due_date < now:
        item.status = "overdue"
    return item


@router.patch("/{item_id}/status", response_model=WorkItemOut)
async def change_status(
    item_id: int,
    data: StatusChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """变更工作项状态"""
    if not can_change_status(current_user):
        raise HTTPException(status_code=403, detail="无权限变更工作项状态，仅规管、总裁、管理员及人事/商务部经理/专员可操作")
    if data.status == "overdue":
        raise HTTPException(status_code=400, detail="已逾时是系统自动状态，不可手动设置")
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")

    old_status = item.status
    item.status = data.status
    item.updated_at = datetime.utcnow()

    log = StatusChangeLog(
        work_item_id=item.id,
        old_status=old_status,
        new_status=data.status,
        operator_id=current_user.id,
        remark=data.remark,
    )
    db.add(log)
    await db.commit()
    await db.refresh(item)

    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item.id)
    )
    item = result.scalar_one()
    now = datetime.utcnow()
    if item.status == "pending" and item.due_date and item.due_date < now:
        item.status = "overdue"
    return item


@router.get("/{item_id}/status-logs", response_model=List[StatusChangeLogOut])
async def get_status_logs(item_id: int, db: AsyncSession = Depends(get_db)):
    """获取工作项状态变更日志"""
    result = await db.execute(
        select(StatusChangeLog)
        .where(StatusChangeLog.work_item_id == item_id)
        .order_by(StatusChangeLog.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/{item_id}", status_code=204)
async def delete_work_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除工作项 - 仅管理员和总裁可操作"""
    user_role = RoleType(current_user.role) if isinstance(current_user.role, str) else current_user.role
    if user_role not in {RoleType.admin, RoleType.president}:
        raise HTTPException(status_code=403, detail="无权限删除工作项，仅管理员和总裁可操作")
    result = await db.execute(select(WorkItem).where(WorkItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")
    await db.delete(item)
    await db.commit()
