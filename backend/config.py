"""应用配置"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "集团工作跟进系统"
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # 数据库
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/gws.db")

    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "gws-secret-key-change-in-production-2024")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("TOKEN_EXPIRE_MINUTES", "1440"))

    # Coze AI (邮件分析)
    COZE_API_TOKEN: str = os.getenv("COZE_API_TOKEN", "")
    COZE_BOT_ID: str = os.getenv("COZE_BOT_ID", "")
    COZE_API_BASE: str = os.getenv("COZE_API_BASE", "https://api.coze.cn")

    # 邮件检查间隔（分钟）
    EMAIL_CHECK_INTERVAL: int = int(os.getenv("EMAIL_CHECK_INTERVAL", "5"))

    # 阿里邮箱API (跳转原邮件)
    ALIMAIL_APP_ID: str = os.getenv("ALIMAIL_APP_ID", "")
    ALIMAIL_APP_SECRET: str = os.getenv("ALIMAIL_APP_SECRET", "")
    ALIMAIL_API_BASE: str = os.getenv("ALIMAIL_API_BASE", "https://alimail-sg.aliyuncs.com")
    ALIMAIL_WEBMAIL_BASE: str = os.getenv("ALIMAIL_WEBMAIL_BASE", "https://mail.sg.aliyun.com/alimail/entries/v5.1/mail/inbox/all/")

    class Config:
        env_file = ".env"


settings = Settings()
