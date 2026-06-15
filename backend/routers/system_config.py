"""系统配置路由"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import SystemConfig
from schemas import SystemConfigOut, SystemConfigCreate, SystemConfigUpdate
from auth import require_role

router = APIRouter(prefix="/system-config", tags=["系统配置"])


@router.get("", response_model=List[SystemConfigOut])
async def list_configs(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(0)),  # 仅管理员可访问
):
    """获取所有系统配置"""
    result = await db.execute(select(SystemConfig).order_by(SystemConfig.config_key))
    return result.scalars().all()


@router.get("/{config_key}", response_model=SystemConfigOut)
async def get_config(
    config_key: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(0)),
):
    """获取单个配置"""
    result = await db.execute(select(SystemConfig).where(SystemConfig.config_key == config_key))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    return config


@router.post("", response_model=SystemConfigOut)
async def create_config(
    data: SystemConfigCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(0)),
):
    """创建配置"""
    # 检查是否已存在
    result = await db.execute(select(SystemConfig).where(SystemConfig.config_key == data.config_key))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="配置键已存在")
    
    config = SystemConfig(**data.model_dump())
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


@router.put("/{config_key}", response_model=SystemConfigOut)
async def update_config(
    config_key: str,
    data: SystemConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(0)),
):
    """更新配置"""
    result = await db.execute(select(SystemConfig).where(SystemConfig.config_key == config_key))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    
    await db.commit()
    await db.refresh(config)
    return config


@router.delete("/{config_key}")
async def delete_config(
    config_key: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(0)),
):
    """删除配置"""
    result = await db.execute(select(SystemConfig).where(SystemConfig.config_key == config_key))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    await db.delete(config)
    await db.commit()
    return {"message": "删除成功"}
