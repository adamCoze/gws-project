"""节假日路由"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import Holiday
from schemas import HolidayOut, HolidayCreate
from auth import require_role

router = APIRouter(prefix="/holidays", tags=["节假日"])


@router.get("", response_model=List[HolidayOut])
async def list_holidays(
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Holiday)
    if year:
        query = query.where(Holiday.year == year)
    query = query.order_by(Holiday.date)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=HolidayOut)
async def create_holiday(
    data: HolidayCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(4)),
):
    holiday = Holiday(**data.model_dump())
    db.add(holiday)
    await db.flush()
    await db.refresh(holiday)
    return holiday


@router.put("/{holiday_id}", response_model=HolidayOut)
async def update_holiday(
    holiday_id: int,
    data: HolidayCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(4)),
):
    result = await db.execute(select(Holiday).where(Holiday.id == holiday_id))
    holiday = result.scalar_one_or_none()
    if not holiday:
        raise HTTPException(status_code=404, detail="节假日不存在")
    holiday.name = data.name
    holiday.date = data.date
    holiday.year = data.year
    await db.flush()
    await db.refresh(holiday)
    return holiday


@router.delete("/{holiday_id}")
async def delete_holiday(
    holiday_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(4)),
):
    result = await db.execute(select(Holiday).where(Holiday.id == holiday_id))
    holiday = result.scalar_one_or_none()
    if not holiday:
        raise HTTPException(status_code=404, detail="节假日不存在")
    await db.delete(holiday)
    return {"message": "删除成功"}
