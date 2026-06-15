"""SQLAlchemy 数据模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum

from database import Base


class RoleType(str, enum.Enum):
    admin = "admin"
    president = "president"
    regulator = "regulator"
    district_manager = "district_manager"
    manager = "manager"
    staff = "staff"


class WorkItemType(str, enum.Enum):
    task = "task"
    cosign = "cosign"


class WorkItemStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    overdue = "overdue"


class EmailProcessResult(str, enum.Enum):
    """邮件处理结果枚举"""
    SUCCESS = "SUCCESS"
    AI_FAILED = "AI_FAILED"
    RETRY = "RETRY"


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="department")
    work_items = relationship("WorkItem", back_populates="department")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(200), unique=True, nullable=False)
    email_prefix = Column(String(50), unique=True, nullable=False, index=True)
    role = Column(SAEnum(RoleType), default=RoleType.staff, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    hashed_password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    department = relationship("Department", back_populates="users")


class WorkItem(Base):
    __tablename__ = "work_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    item_type = Column(SAEnum(WorkItemType), default=WorkItemType.task, nullable=False)
    status = Column(SAEnum(WorkItemStatus), default=WorkItemStatus.pending, nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assignee_email_prefix = Column(String(50), nullable=True, index=True)
    due_date = Column(String(10), nullable=True)
    is_confidential = Column(Boolean, default=False)
    email_subject = Column(String(500), nullable=True)
    email_from = Column(String(200), nullable=True)
    email_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    department = relationship("Department", back_populates="work_items")
    assignee = relationship("User")
    status_change_logs = relationship("StatusChangeLog", back_populates="work_item", order_by="StatusChangeLog.created_at.desc()")
    email_logs = relationship("EmailLog", back_populates="work_item")


class StatusChangeLog(Base):
    """状态变更日志表"""
    __tablename__ = "status_change_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=False, index=True)
    old_status = Column(SAEnum(WorkItemStatus), nullable=False)
    new_status = Column(SAEnum(WorkItemStatus), nullable=False)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    remark = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    work_item = relationship("WorkItem", back_populates="status_change_logs")
    operator = relationship("User")


class EmailConfig(Base):
    """邮箱配置表"""
    __tablename__ = "email_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email_address = Column(String(200), nullable=False)
    imap_host = Column(String(200), default="imap.qiye.aliyun.com")
    imap_port = Column(Integer, default=993)
    smtp_host = Column(String(200), default="smtp.qiye.aliyun.com")
    smtp_port = Column(Integer, default=465)
    use_tls = Column(Boolean, default=True)
    username = Column(String(200), nullable=False)
    password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    last_check_at = Column(DateTime, nullable=True)
    check_interval = Column(Integer, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)


class EmailLog(Base):
    """邮件处理日志表"""
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(500), nullable=False, index=True, comment="邮件唯一ID")
    subject = Column(String(500), nullable=True, comment="邮件主题")
    from_addr = Column(String(200), nullable=True, comment="发件人地址")
    received_at = Column(DateTime, nullable=True, comment="接收时间")
    process_result = Column(SAEnum(EmailProcessResult), nullable=False, comment="处理结果: SUCCESS/AI_FAILED/RETRY")
    retry_count = Column(Integer, default=0, comment="重试次数(0-2)")
    error_message = Column(Text, nullable=True, comment="错误信息")
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=True, comment="关联的工作项ID")
    created_at = Column(DateTime, default=datetime.utcnow)

    work_item = relationship("WorkItem", back_populates="email_logs")


class SystemConfig(Base):
    """系统配置表"""
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(100), unique=True, nullable=False, index=True, comment="配置键")
    config_value = Column(Text, nullable=True, comment="配置值")
    description = Column(String(500), nullable=True, comment="配置描述")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Holiday(Base):
    """节假日表"""
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    date = Column(String(10), nullable=False)
    year = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
