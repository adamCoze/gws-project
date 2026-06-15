"""邮箱配置路由"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import EmailConfig
from schemas import EmailConfigOut, EmailConfigCreate, EmailConfigUpdate
from auth import require_role

router = APIRouter(prefix="/email-configs", tags=["邮箱配置"])


@router.get("", response_model=List[EmailConfigOut])
async def list_configs(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(5)),
):
    result = await db.execute(select(EmailConfig).order_by(EmailConfig.id))
    return result.scalars().all()


@router.post("", response_model=EmailConfigOut)
async def create_config(
    data: EmailConfigCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(5)),
):
    config = EmailConfig(**data.model_dump())
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return config


@router.put("/{config_id}", response_model=EmailConfigOut)
async def update_config(
    config_id: int,
    data: EmailConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(5)),
):
    result = await db.execute(select(EmailConfig).where(EmailConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    await db.flush()
    await db.refresh(config)
    return config


@router.delete("/{config_id}")
async def delete_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(5)),
):
    result = await db.execute(select(EmailConfig).where(EmailConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    await db.delete(config)
    return {"message": "删除成功"}


@router.post("/{config_id}/test")
async def test_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(5)),
):
    """测试邮箱连接"""
    result = await db.execute(select(EmailConfig).where(EmailConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    try:
        import imaplib
        mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port, timeout=10)
        mail.login(config.username, config.password)
        mail.select("INBOX")
        mail.logout()
        return {"message": "连接测试成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"连接测试失败: {str(e)}")
