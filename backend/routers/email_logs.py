"""邮件处理日志路由"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import EmailLog
from schemas import EmailLogOut
from auth import require_role

router = APIRouter(prefix="/email-logs", tags=["邮件日志"])


@router.get("", response_model=List[EmailLogOut])
async def list_email_logs(
    process_result: Optional[str] = None,
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(2)),
):
    """获取邮件处理日志列表"""
    query = select(EmailLog)
    if process_result:
        query = query.where(EmailLog.process_result == process_result)
    query = query.order_by(EmailLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{log_id}", response_model=EmailLogOut)
async def get_email_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(2)),
):
    """获取单个邮件日志详情"""
    result = await db.execute(select(EmailLog).where(EmailLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="邮件日志不存在")
    return log
