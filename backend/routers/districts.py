"""区域管理路由"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import District, RoleLevel
from schemas import DistrictOut, DistrictCreate, DistrictUpdate
from auth import require_role

router = APIRouter(prefix="/districts", tags=["区域管理"])


@router.get("", response_model=List[DistrictOut])
async def list_districts(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(1)),
):
    """获取区域列表（登录用户即可查看）"""
    result = await db.execute(select(District).order_by(District.sort_order, District.id))
    return result.scalars().all()


@router.post("", response_model=DistrictOut)
async def create_district(
    data: DistrictCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(RoleLevel.ADMIN)),
):
    # 检查名称唯一性
    existing = await db.execute(select(District).where(District.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="区域名称已存在")
    district = District(**data.model_dump())
    db.add(district)
    await db.flush()
    await db.refresh(district)
    return district


@router.put("/{district_id}", response_model=DistrictOut)
async def update_district(
    district_id: int,
    data: DistrictUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(RoleLevel.ADMIN)),
):
    result = await db.execute(select(District).where(District.id == district_id))
    district = result.scalar_one_or_none()
    if not district:
        raise HTTPException(status_code=404, detail="区域不存在")
    update_data = data.model_dump(exclude_unset=True)
    # 若改名称，检查唯一性
    if "name" in update_data and update_data["name"] != district.name:
        existing = await db.execute(
            select(District).where(District.name == update_data["name"])
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="区域名称已存在")
    for field, value in update_data.items():
        setattr(district, field, value)
    await db.flush()
    await db.refresh(district)
    return district


@router.delete("/{district_id}")
async def delete_district(
    district_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(RoleLevel.ADMIN)),
):
    result = await db.execute(select(District).where(District.id == district_id))
    district = result.scalar_one_or_none()
    if not district:
        raise HTTPException(status_code=404, detail="区域不存在")
    # 检查是否有部门或用户关联
    from models import Department, User
    dept_count = await db.execute(
        select(Department.id).where(Department.district_id == district_id)
    )
    if dept_count.scalars().first():
        raise HTTPException(status_code=400, detail="该区域下还有部门，无法删除")
    user_count = await db.execute(
        select(User.id).where(User.district_id == district_id)
    )
    if user_count.scalars().first():
        raise HTTPException(status_code=400, detail="该区域下还有用户，无法删除")
    await db.delete(district)
    return {"message": "删除成功"}
