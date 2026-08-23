"""JWT 认证与密码哈希"""
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from database import get_db
from models import User, RoleType, RoleLevel

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)
    except JWTError:
        raise credentials_exception
    except (ValueError, TypeError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_role(min_level: int):
    """角色权限装饰器（基于 role_level 整数）"""
    async def checker(user: User = Depends(get_current_user)):
        # 优先使用 role_level 字段，若为 0 或 None 则回退到 role 字符串映射
        if user.role_level and user.role_level > 0:
            user_level = user.role_level
        else:
            from models import ROLE_TO_LEVEL_DEFAULT
            user_level = ROLE_TO_LEVEL_DEFAULT.get(user.role, 1)
        if user_level < min_level:
            raise HTTPException(status_code=403, detail="权限不足")
        return user
    return checker


# 向后兼容：旧代码仍通过 role 字符串查等级
# 新代码应直接使用 user.role_level 字段
ROLE_LEVELS = {
    "staff": 2,
    "manager": 3,
    "district_manager": 4,
    "regulator": 6,
    "president": 8,
    "admin": 9,
}
