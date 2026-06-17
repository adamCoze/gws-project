"""状态变更日志路由"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import get_db
from models import StatusChangeLog
from schemas import StatusChangeLogOut
from auth import require_role

router = APIRouter(prefix="/status-change-logs", tags=["状态变更日志"])


@router.get("", response_model=List[StatusChangeLogOut])
async def list_logs(
    work_item_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(2)),
):
    query = select(StatusChangeLog).options(
        selectinload(StatusChangeLog.operator),
        selectinload(StatusChangeLog.work_item),
    )
    if work_item_id:
        query = query.where(StatusChangeLog.work_item_id == work_item_id)
    query = query.order_by(StatusChangeLog.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()
