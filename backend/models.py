"""数据库模型"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
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


# 9级角色等级定义
class RoleLevel:
    CONSULTANT = 1
    STAFF = 2
    MANAGER = 3
    DISTRICT_MANAGER = 4
    DEPT_DIRECTOR = 5
    REGULATOR = 6
    GROUP_DIRECTOR = 7
    PRESIDENT = 8
    ADMIN = 9


# 角色字符串 → 等级的默认映射（迁移用）
ROLE_TO_LEVEL_DEFAULT = {
    "admin": RoleLevel.ADMIN,
    "president": RoleLevel.PRESIDENT,
    "regulator": RoleLevel.REGULATOR,
    "district_manager": RoleLevel.DISTRICT_MANAGER,
    "manager": RoleLevel.MANAGER,
    "staff": RoleLevel.STAFF,
}


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
    report = "report"


class EmailProcessResult(str, Enum):
    SUCCESS = "success"
    AI_FAILED = "ai_failed"
    RETRY = "retry"


# ========== 区域 ==========

class District(Base):
    __tablename__ = "districts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    departments = relationship("Department", back_populates="district")
    users = relationship("User", back_populates="district")


# ========== 部门 ==========

class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), nullable=False)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    district = relationship("District", back_populates="departments")
    users = relationship("User", back_populates="department")
    work_items = relationship("WorkItem", back_populates="department")


# ========== 用户 ==========

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(200), unique=True, nullable=True)
    email_prefix = Column(String(50), unique=True, nullable=True)
    real_name = Column(String(50), nullable=True)
    role = Column(String(16), default="staff", nullable=False)
    role_level = Column(Integer, default=RoleLevel.STAFF, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=True)
    region = Column(String(20), nullable=True)
    hashed_password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    department = relationship("Department", back_populates="users")
    district = relationship("District", back_populates="users")
    assigned_items = relationship("WorkItem", back_populates="assignee", foreign_keys="WorkItem.assignee_id")


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
    sponsor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    completed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    completed_at = Column(DateTime, nullable=True)
    due_date = Column(DateTime, nullable=True)
    is_confidential = Column(Boolean, default=False, nullable=False)
    message_id = Column(String(500), nullable=True)
    email_subject = Column(String(500), nullable=True)
    email_from = Column(String(200), nullable=True)
    sender_email = Column(String(200), nullable=True)
    email_date = Column(DateTime, nullable=True)
    # 会签自动完成追踪字段
    cosign_designated_signers = Column(Text, nullable=True)    # JSON list of signer prefixes
    cosign_replied_signers = Column(Text, nullable=True)       # JSON list of replied signer prefixes
    cosign_requires_xiangxin = Column(Boolean, default=False)  # 是否需要向总会签
    cosign_blocked = Column(Boolean, default=False)            # 是否被阻止自动完成
    cosign_auto_complete_at = Column(DateTime, nullable=True)  # 计划自动完成时间
    cosign_payment_confirmed = Column(Boolean, default=False)  # 支付确认标记（收到"已完成支付"等表述）
    latest_progress = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    department = relationship("Department", back_populates="work_items")
    assignee = relationship("User", back_populates="assigned_items", foreign_keys=[assignee_id])
    sponsor = relationship("User", foreign_keys=[sponsor_id])
    completer = relationship("User", foreign_keys=[completed_by])
    status_logs = relationship("StatusChangeLog", back_populates="work_item", cascade="all, delete-orphan")
    assessment_scores = relationship("AssessmentScore", back_populates="work_item")
    non_assessment_items = relationship("NonAssessmentItem", back_populates="work_item")


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
    smtp_host = Column(String(200), nullable=True)
    smtp_port = Column(Integer, nullable=True)
    use_tls = Column(Boolean, default=True)
    check_interval = Column(Integer, nullable=True)
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


# ======================================================================
# 考核模块模型
# ======================================================================

class AssessmentStatus(str, Enum):
    draft = "draft"          # 草稿
    scoring = "scoring"      # 评分中
    reviewing = "reviewing"  # 复核中
    completed = "completed"  # 已完成
    cancelled = "cancelled"  # 已取消


class SupplementRequestStatus(str, Enum):
    pending = "pending"    # 待处理
    supplied = "supplied"  # 已补充
    rejected = "rejected"  # 已拒绝


class AppealStatus(str, Enum):
    pending = "pending"      # 待处理
    approved = "approved"    # 已通过
    rejected = "rejected"    # 已驳回
    withdrawn = "withdrawn"  # 已撤回


class Assessment(Base):
    """考核主表"""
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)  # 0=季度/年度考核, 1-12=月度
    status = Column(String(20), default=AssessmentStatus.draft.value, nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = relationship("User", foreign_keys=[created_by])
    scores = relationship("AssessmentScore", back_populates="assessment", cascade="all, delete-orphan")
    operation_logs = relationship("AssessmentOperationLog", back_populates="assessment", cascade="all, delete-orphan")

    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class AssessmentScore(Base):
    """每层评分记录"""
    __tablename__ = "assessment_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=False)
    scorer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    level = Column(Integer, nullable=False)  # 评分层级 1-9
    score = Column(Integer, nullable=True)   # 总分档位：1/5/10/20/30
    comment = Column(Text, nullable=True)
    scored_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assessment = relationship("Assessment", back_populates="scores")
    work_item = relationship("WorkItem", back_populates="assessment_scores")
    scorer = relationship("User", foreign_keys=[scorer_id])
    participants = relationship("AssessmentScoreParticipant", back_populates="score", cascade="all, delete-orphan")
    attachments = relationship("AssessmentAttachment", back_populates="score", cascade="all, delete-orphan")
    supplement_requests = relationship("AssessmentSupplementRequest", back_populates="score", cascade="all, delete-orphan")
    appeals = relationship("AssessmentAppeal", back_populates="score", cascade="all, delete-orphan")

    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class AssessmentScoreParticipant(Base):
    """参与人分数分配"""
    __tablename__ = "assessment_score_participants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    score_id = Column(Integer, ForeignKey("assessment_scores.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    allocated_score = Column(Float, nullable=False)  # 支持1位小数
    created_at = Column(DateTime, default=datetime.utcnow)

    score = relationship("AssessmentScore", back_populates="participants")
    user = relationship("User", foreign_keys=[user_id])


class AssessmentAttachment(Base):
    """附件凭证"""
    __tablename__ = "assessment_attachments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    score_id = Column(Integer, ForeignKey("assessment_scores.id"), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)  # bytes
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    score = relationship("AssessmentScore", back_populates="attachments")
    uploader = relationship("User", foreign_keys=[uploaded_by])


class AssessmentSupplementRequest(Base):
    """补充凭证请求"""
    __tablename__ = "assessment_supplement_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    score_id = Column(Integer, ForeignKey("assessment_scores.id"), nullable=False)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reason = Column(Text, nullable=False)
    status = Column(String(20), default=SupplementRequestStatus.pending.value, nullable=False)
    response = Column(Text, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    score = relationship("AssessmentScore", back_populates="supplement_requests")
    requester = relationship("User", foreign_keys=[requester_id])


class AssessmentAppeal(Base):
    """异议记录"""
    __tablename__ = "assessment_appeals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    score_id = Column(Integer, ForeignKey("assessment_scores.id"), nullable=False)
    appellant_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reason = Column(Text, nullable=False)
    status = Column(String(20), default=AppealStatus.pending.value, nullable=False)
    handler_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    handle_comment = Column(Text, nullable=True)
    handled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    score = relationship("AssessmentScore", back_populates="appeals")
    appellant = relationship("User", foreign_keys=[appellant_id])
    handler = relationship("User", foreign_keys=[handler_id])


class NonAssessmentItem(Base):
    """非考核项标记"""
    __tablename__ = "non_assessment_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=False)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=True)
    reason = Column(Text, nullable=True)
    marked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    work_item = relationship("WorkItem", back_populates="non_assessment_items")
    assessment = relationship("Assessment")
    marker = relationship("User", foreign_keys=[marked_by])


class AssessmentOperationLog(Base):
    """操作日志"""
    __tablename__ = "assessment_operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(50), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    assessment = relationship("Assessment", back_populates="operation_logs")
    operator = relationship("User", foreign_keys=[operator_id])
