"""看板路由"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from database import get_db
from models import WorkItem, Department, User, WorkItemStatus, StatusChangeLog
from schemas import KanbanDeptData, WorkItemOut
from auth import get_current_user, ROLE_LEVELS

router = APIRouter(prefix="/kanban", tags=["看板"])


@router.get("", response_model=List[KanbanDeptData])
async def get_kanban(
    department_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取看板数据（按部门分组）"""
    # 获取部门列表
    dept_query = select(Department).order_by(Department.id)
    if department_id:
        dept_query = dept_query.where(Department.id == department_id)
    dept_result = await db.execute(dept_query)
    departments = dept_result.scalars().all()

    user_level = ROLE_LEVELS.get(user.role, 0)

    kanban_data = []
    for dept in departments:
        # 查询该部门的工作项
        item_query = (
            select(WorkItem)
            .where(WorkItem.department_id == dept.id)
            .options(
                selectinload(WorkItem.department),
                selectinload(WorkItem.assignee),
                selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
                selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
            )
        )
        # 机密过滤
        if user_level < 4:
            item_query = item_query.where(
                or_(WorkItem.is_confidential == False, WorkItem.assignee_email_prefix == user.email_prefix)  # noqa: E712
            )
        item_result = await db.execute(item_query)
        items = item_result.scalars().all()

        kanban_data.append(KanbanDeptData(
            department_id=dept.id,
            department_name=dept.name,
            pending=[WorkItemOut.model_validate(i) for i in items if i.status == "pending"],
            shelved=[WorkItemOut.model_validate(i) for i in items if i.status == "shelved"],
            completed=[WorkItemOut.model_validate(i) for i in items if i.status == "completed"],
            cancelled=[WorkItemOut.model_validate(i) for i in items if i.status == "cancelled"],
        ))

    return kanban_data
