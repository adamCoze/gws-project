"""部门路由"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import get_db
from models import Department, RoleLevel
from schemas import DepartmentOut, DepartmentCreate, DepartmentUpdate
from auth import require_role

router = APIRouter(prefix="/departments", tags=["部门"])


@router.get("", response_model=List[DepartmentOut])
async def list_departments(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Department)
        .options(selectinload(Department.district))
        .order_by(Department.id)
    )
    return result.scalars().all()


@router.post("", response_model=DepartmentOut)
async def create_department(
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(RoleLevel.ADMIN)),
):
    dept = Department(**data.model_dump())
    db.add(dept)
    await db.flush()
    await db.refresh(dept, ["district"])
    return dept


@router.put("/{dept_id}", response_model=DepartmentOut)
async def update_department(
    dept_id: int,
    data: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(RoleLevel.ADMIN)),
):
    result = await db.execute(
        select(Department)
        .where(Department.id == dept_id)
        .options(selectinload(Department.district))
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="部门不存在")
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(dept, field, value)
    await db.flush()
    await db.refresh(dept, ["district"])
    return dept


@router.delete("/{dept_id}")
async def delete_department(
    dept_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(RoleLevel.ADMIN)),
):
    result = await db.execute(select(Department).where(Department.id == dept_id))
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="部门不存在")
    await db.delete(dept)
    return {"message": "删除成功"}
