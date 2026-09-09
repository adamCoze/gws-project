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


async def _column_exists(table_name: str, column_name: str) -> bool:
    """检查 SQLite 表中是否存在某列"""
    async with async_session() as session:
        result = await session.execute(text(f"PRAGMA table_info({table_name})"))
        columns = result.fetchall()
        return any(col[1] == column_name for col in columns)


async def _run_migrations():
    """执行数据库迁移：新增字段、数据初始化等

    使用 system_config 表记录迁移版本，确保每个迁移只执行一次。
    """
    import logging
    logger = logging.getLogger(__name__)

    from sqlalchemy import select
    from models import SystemConfig

    async with async_session() as session:
        try:
            # 读取当前迁移版本
            result = await session.execute(
                select(SystemConfig).where(SystemConfig.config_key == "db_migration_version")
            )
            version_config = result.scalar_one_or_none()
            current_version = int(version_config.config_value) if version_config else 0

            new_version = current_version

            # ---- v1: users 表新增 role_level 字段 + 填充数据 ----
            if current_version < 1:
                if not await _column_exists("users", "role_level"):
                    await session.execute(text("ALTER TABLE users ADD COLUMN role_level INTEGER DEFAULT 2 NOT NULL"))
                    logger.info("迁移 v1：users 表新增 role_level 字段")
                new_version = 1

            # ---- v2: users 表新增 district_id 字段 ----
            if current_version < 2:
                if not await _column_exists("users", "district_id"):
                    await session.execute(text("ALTER TABLE users ADD COLUMN district_id INTEGER"))
                    logger.info("迁移 v2：users 表新增 district_id 字段")
                new_version = 2

            # ---- v3: departments 表新增 district_id 字段 ----
            if current_version < 3:
                if not await _column_exists("departments", "district_id"):
                    await session.execute(text("ALTER TABLE departments ADD COLUMN district_id INTEGER"))
                    logger.info("迁移 v3：departments 表新增 district_id 字段")
                new_version = 3

            # ---- v4: work_items 表新增 sponsor_id / completed_by / completed_at ----
            if current_version < 4:
                if not await _column_exists("work_items", "sponsor_id"):
                    await session.execute(text("ALTER TABLE work_items ADD COLUMN sponsor_id INTEGER"))
                    logger.info("迁移 v4：work_items 表新增 sponsor_id 字段")
                if not await _column_exists("work_items", "completed_by"):
                    await session.execute(text("ALTER TABLE work_items ADD COLUMN completed_by INTEGER"))
                    logger.info("迁移 v4：work_items 表新增 completed_by 字段")
                if not await _column_exists("work_items", "completed_at"):
                    await session.execute(text("ALTER TABLE work_items ADD COLUMN completed_at DATETIME"))
                    logger.info("迁移 v4：work_items 表新增 completed_at 字段")
                new_version = 4

            # ---- v5: 填充 role_level 数据（根据 role 字符串映射）----
            if current_version < 5:
                from models import ROLE_TO_LEVEL_DEFAULT, User

                result = await session.execute(select(User))
                users = result.scalars().all()
                migrated_count = 0
                for user in users:
                    target_level = ROLE_TO_LEVEL_DEFAULT.get(user.role, 2)
                    if user.role_level != target_level:
                        user.role_level = target_level
                        migrated_count += 1
                if migrated_count:
                    logger.info(f"迁移 v5：已为 {migrated_count} 个用户填充 role_level")
                new_version = 5

            # ---- v6: 主副角色体系 + 考核角色预留字段 ----
            if current_version < 6:
                # users 表新增 secondary_roles 字段
                if not await _column_exists("users", "secondary_roles"):
                    await session.execute(text("ALTER TABLE users ADD COLUMN secondary_roles TEXT NOT NULL DEFAULT '[]'"))
                    logger.info("迁移 v6：users 表新增 secondary_roles 字段")
                # assessments 表新增 initiator_role_level 字段
                if not await _column_exists("assessments", "initiator_role_level"):
                    await session.execute(text("ALTER TABLE assessments ADD COLUMN initiator_role_level INTEGER"))
                    logger.info("迁移 v6：assessments 表新增 initiator_role_level 字段")
                # assessment_scores 表新增 scorer_role_level 字段
                if not await _column_exists("assessment_scores", "scorer_role_level"):
                    await session.execute(text("ALTER TABLE assessment_scores ADD COLUMN scorer_role_level INTEGER"))
                    logger.info("迁移 v6：assessment_scores 表新增 scorer_role_level 字段")
                new_version = 6

            # ---- v7: 副角色升级为对象数组 + 考核表补充部门/区域字段 ----
            if current_version < 7:
                import json as _json
                from models import User

                # 迁移 secondary_roles 整数数组 -> 对象数组
                result = await session.execute(select(User))
                users = result.scalars().all()
                migrated_count = 0
                for user in users:
                    raw = user.secondary_roles
                    if not raw:
                        continue
                    # 尝试解析
                    try:
                        data = _json.loads(raw) if isinstance(raw, str) else raw
                    except Exception:
                        continue
                    if not isinstance(data, list) or not data:
                        continue
                    # 判断是否已经是对象数组格式
                    if isinstance(data[0], dict):
                        continue
                    # 整数数组 -> 对象数组
                    new_data = [
                        {"role_level": int(x), "department_id": None, "district_id": None}
                        for x in data
                    ]
                    user.secondary_roles = new_data
                    migrated_count += 1
                if migrated_count:
                    logger.info(f"迁移 v7：已为 {migrated_count} 个用户升级副角色为对象数组格式")

                # assessments 表补充发起部门/区域
                if not await _column_exists("assessments", "initiator_department_id"):
                    await session.execute(text("ALTER TABLE assessments ADD COLUMN initiator_department_id INTEGER"))
                    logger.info("迁移 v7：assessments 表新增 initiator_department_id 字段")
                if not await _column_exists("assessments", "initiator_district_id"):
                    await session.execute(text("ALTER TABLE assessments ADD COLUMN initiator_district_id INTEGER"))
                    logger.info("迁移 v7：assessments 表新增 initiator_district_id 字段")

                # assessment_scores 表补充评分部门/区域
                if not await _column_exists("assessment_scores", "scorer_department_id"):
                    await session.execute(text("ALTER TABLE assessment_scores ADD COLUMN scorer_department_id INTEGER"))
                    logger.info("迁移 v7：assessment_scores 表新增 scorer_department_id 字段")
                if not await _column_exists("assessment_scores", "scorer_district_id"):
                    await session.execute(text("ALTER TABLE assessment_scores ADD COLUMN scorer_district_id INTEGER"))
                    logger.info("迁移 v7：assessment_scores 表新增 scorer_district_id 字段")

                new_version = 7

            # ---- v8: 考核模块表结构重建（简化版 -> 需求v0.3完整版，测试数据清空）----
            if current_version < 8:
                old_tables = [
                    "assessment_scores",
                    "assessment_operation_logs",
                    "assessments",
                ]
                for tbl in old_tables:
                    await session.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
                    logger.info(f"迁移 v8：删除旧结构考核表 {tbl}")
                await session.commit()
                # 按完整版模型重建全部考核表（含附件/异议/补充请求/参与人/非考核项新表）
                from database import Base as _Base
                async with engine.begin() as conn:
                    await conn.run_sync(_Base.metadata.create_all)
                logger.info("迁移 v8：已按完整版模型重建考核模块全部表")
                new_version = 8

            # 更新迁移版本
            if new_version > current_version:
                if version_config:
                    version_config.config_value = str(new_version)
                else:
                    session.add(SystemConfig(config_key="db_migration_version", config_value=str(new_version)))
                await session.commit()
                logger.info(f"数据库迁移完成，当前版本: {new_version}")

        except Exception as e:
            await session.rollback()
            logger.error(f"数据库迁移失败: {e}", exc_info=True)


async def _seed_districts_from_users():
    """根据现有 users.region 字符串初始化区域数据并回填 district_id"""
    import logging
    logger = logging.getLogger(__name__)

    from sqlalchemy import select, func
    from models import User, District

    async with async_session() as session:
        try:
            # 检查是否已有区域数据
            district_count = await session.execute(select(func.count(District.id)))
            if district_count.scalar() > 0:
                return

            # 从 users.region 提取唯一的区域名称
            result = await session.execute(
                select(User.region).where(User.region.isnot(None)).distinct()
            )
            regions = [row[0] for row in result.fetchall() if row[0]]

            if not regions:
                return

            # 创建区域（按字母排序，sort_order 自增）
            sort_order = 0
            district_map = {}
            for region_name in sorted(regions):
                district = District(name=region_name, sort_order=sort_order, is_active=True)
                session.add(district)
                await session.flush()
                district_map[region_name] = district.id
                sort_order += 1

            # 回填 users.district_id
            for region_name, district_id in district_map.items():
                await session.execute(
                    text("UPDATE users SET district_id = :did WHERE region = :region"),
                    {"did": district_id, "region": region_name}
                )

            await session.commit()
            logger.info(f"迁移：从 users.region 初始化了 {len(district_map)} 个区域")
        except Exception as e:
            await session.rollback()
            logger.error(f"区域初始化失败: {e}", exc_info=True)


async def init_db():
    """初始化数据库表"""
    from models import (  # noqa: F401
        District,
        Department,
        User,
        WorkItem,
        StatusChangeLog,
        EmailConfig,
        EmailLog,
        SystemConfig,
        EmailUrlCache,
        Holiday,
        Assessment,
        AssessmentScore,
        AssessmentScoreParticipant,
        AssessmentAttachment,
        AssessmentSupplementRequest,
        AssessmentAppeal,
        NonAssessmentItem,
        AssessmentOperationLog,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 执行字段级迁移（针对已有表的 ALTER 操作）
    await _run_migrations()

    # 从现有 region 字段初始化区域数据
    await _seed_districts_from_users()

    # 创建默认管理员和部门
    await _seed_defaults()


async def _seed_defaults():
    """创建默认数据"""
    from sqlalchemy import select
    from models import Department, User, RoleLevel
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
                role_level=RoleLevel.ADMIN,
                hashed_password=get_password_hash("admin123"),
                is_active=True,
            )
            session.add(admin)
            await session.commit()
