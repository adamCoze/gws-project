"""数据库连接与初始化"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event, text

from config import settings

# 确保数据目录存在
db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
db_dir = os.path.dirname(db_path)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False},
)


async def _set_pragma(dbapi_conn, _):
    """设置 SQLite WAL 模式"""
    cursor = await dbapi_conn.execute("PRAGMA journal_mode=WAL")
    await cursor.close()
    cursor = await dbapi_conn.execute("PRAGMA synchronous=NORMAL")
    await cursor.close()
    cursor = await dbapi_conn.execute("PRAGMA cache_size=10000")
    await cursor.close()


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=10000")
    cursor.close()

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库表"""
    from models import Department, User, WorkItem, StatusChangeLog, EmailConfig, EmailLog, SystemConfig  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 创建默认管理员和部门
    await _seed_defaults()


async def _seed_defaults():
    """创建默认数据"""
    from sqlalchemy import select
    from models import Department, User
    from auth import get_password_hash

    async with async_session() as session:
        # 默认部门
        default_depts = [
            ("人事/商务部", "RS"),
            ("财审/投资部", "CS"),
            ("行政/产品部", "XZ"),
            ("法务/媒体部", "FW"),
        ]
        for name, code in default_depts:
            result = await session.execute(select(Department).where(Department.name == name))
            if not result.scalar_one_or_none():
                session.add(Department(name=name, code=code))
        await session.commit()

        # 默认管理员
        result = await session.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            admin = User(
                username="admin",
                email="admin@example.com",
                email_prefix="admin",
                role="admin",
                hashed_password=get_password_hash("admin123"),
                is_active=True,
            )
            session.add(admin)
            await session.commit()
