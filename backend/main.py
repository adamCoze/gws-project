"""FastAPI 主入口"""
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings
from database import init_db
from routers import auth, users, work_items, departments, email_config, status_logs, kanban, email_logs, system_config, quick_complete


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动时初始化数据库
    await init_db()
    # 启动邮件监听服务
    from services.email_service import start_email_monitor
    await start_email_monitor()

    # 启动每日逾期通报定时任务
    import asyncio
    import logging
    from datetime import datetime, timedelta
    from services.daily_notification import send_daily_overdue_notification
    logger = logging.getLogger(__name__)

    async def daily_notification_scheduler():
        while True:
            try:
                now = datetime.now()
                target = now.replace(hour=21, minute=0, second=0, microsecond=0)
                if now >= target:
                    target += timedelta(days=1)
                wait_seconds = (target - now).total_seconds()
                logger.info(f"每日通报将在 {wait_seconds/3600:.1f} 小时后发送")
                await asyncio.sleep(wait_seconds)
                await send_daily_overdue_notification()
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"每日通报调度器异常: {e}", exc_info=True)
                await asyncio.sleep(60)

    notification_task = asyncio.create_task(daily_notification_scheduler())

    # 启动会签自动完成定时检查（每10分钟检查一次）
    from services.cosign_service import check_and_auto_complete_cosign, backfill_existing_cosign_items

    async def cosign_autocomplete_scheduler():
        # 启动时先做一次存量数据迁移
        try:
            await backfill_existing_cosign_items()
        except Exception as e:
            logger.error(f"会签存量数据迁移失败: {e}", exc_info=True)

        while True:
            try:
                await asyncio.sleep(600)  # 每10分钟检查一次
                completed = await check_and_auto_complete_cosign()
                if completed:
                    logger.info(f"会签自动完成: {len(completed)} 个工作项")
            except Exception as e:
                logger.error(f"会签自动完成检查异常: {e}", exc_info=True)
                await asyncio.sleep(60)

    cosign_task = asyncio.create_task(cosign_autocomplete_scheduler())

    yield
    # 关闭邮件监听
    from services.email_service import stop_email_monitor
    await stop_email_monitor()
    notification_task.cancel()
    cosign_task.cancel()


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(work_items.router, prefix="/api")
app.include_router(departments.router, prefix="/api")
app.include_router(email_config.router, prefix="/api")
app.include_router(status_logs.router, prefix="/api")
app.include_router(kanban.router, prefix="/api")
app.include_router(email_logs.router, prefix="/api")
app.include_router(system_config.router, prefix="/api")
app.include_router(quick_complete.router)  # 快捷完成页面（无/api前缀）


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DEPLOY_RUN_PORT", "8000"))
    # 生产环境不使用 reload
    reload = os.getenv("COZE_PROJECT_ENV") != "PROD"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
