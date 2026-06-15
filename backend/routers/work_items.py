"""工作项路由"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from database import get_db
from models import WorkItem, User, StatusChangeLog, WorkItemStatus, RoleType
from schemas import WorkItemOut, WorkItemCreate, WorkItemUpdate, StatusUpdateRequest
from auth import get_current_user, require_role, ROLE_LEVELS

router = APIRouter(prefix="/work-items", tags=["工作项"])


def _apply_role_filter(query, user: User):
    """根据角色过滤机密工作项"""
    user_level = ROLE_LEVELS.get(user.role, 0)
    if user_level < 4:  # 低于总裁级别不能看机密
        query = query.where(or_(WorkItem.is_confidential == False, WorkItem.assignee_email_prefix == user.email_prefix))  # noqa: E712
    return query


@router.get("", response_model=List[WorkItemOut])
async def list_work_items(
    department_id: Optional[int] = None,
    status: Optional[str] = None,
    assignee_email_prefix: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(WorkItem).options(selectinload(WorkItem.department), selectinload(WorkItem.assignee))
    query = _apply_role_filter(query, user)
    if department_id:
        query = query.where(WorkItem.department_id == department_id)
    if status:
        query = query.where(WorkItem.status == status)
    if assignee_email_prefix:
        query = query.where(WorkItem.assignee_email_prefix == assignee_email_prefix)
    query = query.order_by(WorkItem.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/my", response_model=List[WorkItemOut])
async def my_work_items(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取当前用户的工作项（按邮箱前缀匹配）"""
    query = (
        select(WorkItem)
        .options(selectinload(WorkItem.department), selectinload(WorkItem.assignee))
        .where(WorkItem.assignee_email_prefix == user.email_prefix)
        .order_by(WorkItem.created_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{item_id}", response_model=WorkItemOut)
async def get_work_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WorkItem).where(WorkItem.id == item_id).options(selectinload(WorkItem.department), selectinload(WorkItem.assignee))
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")
    # 机密检查
    user_level = ROLE_LEVELS.get(user.role, 0)
    if item.is_confidential and user_level < 4 and item.assignee_email_prefix != user.email_prefix:
        raise HTTPException(status_code=403, detail="无权查看机密工作项")
    return item


@router.post("", response_model=WorkItemOut)
async def create_work_item(
    data: WorkItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(2)),
):
    item = WorkItem(**data.model_dump())
    db.add(item)
    await db.flush()
    await db.refresh(item, ["department", "assignee"])
    return item


@router.put("/{item_id}", response_model=WorkItemOut)
async def update_work_item(
    item_id: int,
    data: WorkItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(2)),
):
    result = await db.execute(select(WorkItem).where(WorkItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await db.flush()
    await db.refresh(item, ["department", "assignee"])
    return item


@router.patch("/{item_id}/status", response_model=WorkItemOut)
async def update_status(
    item_id: int,
    data: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(WorkItem).where(WorkItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")
    old_status = item.status
    new_status = WorkItemStatus(data.status)
    item.status = new_status
    # 记录状态变更日志
    log = StatusChangeLog(
        work_item_id=item.id,
        old_status=old_status,
        new_status=new_status,
        operator_id=user.id,
        remark=data.remark,
    )
    db.add(log)
    await db.flush()
    await db.refresh(item, ["department", "assignee"])
    return item


@router.delete("/{item_id}")
async def delete_work_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(2)),
):
    result = await db.execute(select(WorkItem).where(WorkItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")
    await db.delete(item)
    return {"message": "删除成功"}
