"""状态变更日志路由"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import get_db
from models import StatusLog
from schemas import StatusLogOut
from auth import require_role

router = APIRouter(prefix="/status-logs", tags=["状态日志"])


@router.get("", response_model=List[StatusLogOut])
async def list_logs(
    work_item_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(2)),
):
    query = select(StatusLog).options(selectinload(StatusLog.operator))
    if work_item_id:
        query = query.where(StatusLog.work_item_id == work_item_id)
    query = query.order_by(StatusLog.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()
