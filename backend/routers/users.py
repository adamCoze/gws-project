"""用户管理路由"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import get_db
from models import User, Department, District, RoleLevel
from schemas import UserOut, UserCreate, UserUpdate, ResetPasswordRequest, UserBriefOut
from auth import get_password_hash, require_role, get_current_user

router = APIRouter(prefix="/users", tags=["用户管理"])


def _validate_role_fields(role_level: int, department_id, district_id):
    """根据主角色等级校验部门/区域字段的必填规则

    - admin(9)/president(8)/group_director(7)/regulator(6): 不强求，可为空
    - dept_director(5): department_id 必填
    - district_manager(4): district_id 必填
    - manager(3)/staff(2)/consultant(1): department_id 必填
    """
    if role_level >= RoleLevel.REGULATOR:  # 6,7,8,9
        return
    if role_level == RoleLevel.DEPT_DIRECTOR:  # 5
        if not department_id:
            raise HTTPException(status_code=400, detail="部门总监必须选择部门")
    elif role_level == RoleLevel.DISTRICT_MANAGER:  # 4
        if not district_id:
            raise HTTPException(status_code=400, detail="区域总监必须选择区域")
    else:  # 3, 2, 1
        if not department_id:
            raise HTTPException(status_code=400, detail="该角色必须选择部门")


def _normalize_secondary_roles(secondary_roles, role_level: int) -> list:
    """规范化副角色列表：去重、排除主角色、排序"""
    if not secondary_roles:
        return []
    # 去重 + 排除主角色 + 转 int + 排序
    roles = sorted({int(r) for r in secondary_roles if int(r) != role_level})
    return roles


@router.get("/brief", response_model=List[dict])
async def list_users_brief(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """获取用户简要列表（id+姓名），供非管理员选择负责人时使用，需登录但无角色限制"""
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return [{"id": u.id, "real_name": u.real_name, "username": u.username, "email_prefix": u.email_prefix, "role_level": u.role_level, "secondary_roles": u.secondary_roles or []} for u in users]


@router.get("", response_model=List[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(RoleLevel.ADMIN)),
):
    result = await db.execute(
        select(User)
        .options(selectinload(User.department), selectinload(User.district))
        .order_by(User.id)
    )
    return result.scalars().all()


@router.post("", response_model=UserOut)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(RoleLevel.ADMIN)),
):
    # 检查唯一性
    existing = await db.execute(select(User).where((User.username == data.username) | (User.email == data.email) | (User.email_prefix == data.email_prefix)))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名、邮箱或邮箱前缀已存在")

    # 角色联动校验（只校验主角色）
    _validate_role_fields(data.role_level, data.department_id, data.district_id)

    # 规范化副角色
    secondary_roles = _normalize_secondary_roles(data.secondary_roles, data.role_level)

    user = User(
        username=data.username,
        email=data.email,
        email_prefix=data.email_prefix,
        real_name=data.real_name,
        role=data.role,
        role_level=data.role_level,
        secondary_roles=secondary_roles,
        department_id=data.department_id,
        district_id=data.district_id,
        region=data.region,
        hashed_password=get_password_hash(data.password),
        is_active=data.is_active,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user, ["department", "district"])
    return user


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(RoleLevel.ADMIN)),
):
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.department), selectinload(User.district))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    update_data = data.model_dump(exclude_unset=True)

    # 处理密码特殊字段
    if "password" in update_data and update_data["password"]:
        user.hashed_password = get_password_hash(update_data.pop("password"))

    # 规范化副角色（如果有提交）
    if "secondary_roles" in update_data:
        # 以更新后的 role_level 为准（如果同时改了主角色）
        effective_role_level = update_data.get("role_level", user.role_level)
        update_data["secondary_roles"] = _normalize_secondary_roles(
            update_data["secondary_roles"], effective_role_level
        )

    # 角色联动校验（如果主角色或部门/区域有变动）
    if "role_level" in update_data or "department_id" in update_data or "district_id" in update_data:
        effective_role_level = update_data.get("role_level", user.role_level)
        effective_dept = update_data.get("department_id", user.department_id)
        effective_district = update_data.get("district_id", user.district_id)
        _validate_role_fields(effective_role_level, effective_dept, effective_district)

    for field, value in update_data.items():
        setattr(user, field, value)
    await db.flush()
    await db.refresh(user, ["department", "district"])
    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(RoleLevel.ADMIN)),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    await db.delete(user)
    return {"message": "删除成功"}


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(RoleLevel.ADMIN)),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.hashed_password = get_password_hash(data.password)
    return {"message": "密码重置成功"}
