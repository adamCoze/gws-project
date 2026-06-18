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
from routers import auth, users, work_items, departments, email_config, status_logs, kanban, email_logs, system_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动时初始化数据库
    await init_db()
    # 启动邮件监听服务
    from services.email_service import start_email_monitor
    await start_email_monitor()
    yield
    # 关闭邮件监听
    from services.email_service import stop_email_monitor
    await stop_email_monitor()


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


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DEPLOY_RUN_PORT", "8000"))
    # 生产环境不使用 reload
    reload = os.getenv("COZE_PROJECT_ENV") != "PROD"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
