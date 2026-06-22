"""数据库模型"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from database import Base


class RoleType(str, Enum):
    staff = "staff"
    manager = "manager"
    district_manager = "district_manager"
    regulator = "regulator"
    president = "president"
    admin = "admin"


# 向后兼容
UserRole = RoleType


class WorkItemStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    overdue = "overdue"
    cancelled = "cancelled"


class WorkItemType(str, Enum):
    task = "task"
    cosign = "cosign"


class EmailProcessResult(str, Enum):
    SUCCESS = "success"
    AI_FAILED = "ai_failed"
    RETRY = "retry"


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="department")
    work_items = relationship("WorkItem", back_populates="department")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(200), unique=True, nullable=True)
    email_prefix = Column(String(50), unique=True, nullable=True)
    real_name = Column(String(50), nullable=True)
    role = Column(String(16), default="staff", nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    region = Column(String(20), nullable=True)
    hashed_password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    department = relationship("Department", back_populates="users")
    assigned_items = relationship("WorkItem", back_populates="assignee")


class Holiday(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    date = Column(String(10), nullable=False)
    year = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkItem(Base):
    __tablename__ = "work_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    item_type = Column(String(10), default="task", nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assignee_email_prefix = Column(String(50), nullable=True)
    due_date = Column(DateTime, nullable=True)
    is_confidential = Column(Boolean, default=False, nullable=False)
    message_id = Column(String(500), nullable=True)
    email_subject = Column(String(500), nullable=True)
    email_from = Column(String(200), nullable=True)
    sender_email = Column(String(200), nullable=True)
    email_date = Column(DateTime, nullable=True)
    latest_progress = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    department = relationship("Department", back_populates="work_items")
    assignee = relationship("User", back_populates="assigned_items")
    status_logs = relationship("StatusChangeLog", back_populates="work_item", cascade="all, delete-orphan")


class StatusChangeLog(Base):
    __tablename__ = "status_change_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=False)
    old_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    work_item = relationship("WorkItem", back_populates="status_logs")
    operator = relationship("User", foreign_keys=[operator_id])


class EmailConfig(Base):
    __tablename__ = "email_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email_address = Column(String(120), nullable=False)
    imap_host = Column(String(200), nullable=False)
    imap_port = Column(Integer, default=993, nullable=False)
    username = Column(String(120), nullable=False)
    password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_check_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(500), nullable=False, index=True)
    subject = Column(String(500), nullable=True)
    from_addr = Column(String(200), nullable=True)
    received_at = Column(DateTime, default=datetime.utcnow)
    process_result = Column(String(20), nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SystemConfig(Base):
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(100), unique=True, nullable=False)
    config_value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EmailUrlCache(Base):
    """邮件URL缓存 - 记录邮件链接查找结果，避免重复调API"""
    __tablename__ = "email_url_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_email = Column(String(200), nullable=False, index=True)
    work_item_id = Column(Integer, nullable=False, index=True)
    conversation_id = Column(String(200), nullable=True)
    status = Column(String(20), nullable=False, default="found")  # found / not_found
    created_at = Column(DateTime, default=datetime.utcnow)

    # 联合唯一索引：同一用户+同一工作项只有一条缓存
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )
