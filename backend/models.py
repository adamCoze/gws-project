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
    "dept_director": RoleLevel.DEPT_DIRECTOR,
    "group_director": RoleLevel.GROUP_DIRECTOR,
    "consultant": RoleLevel.CONSULTANT,
    "intern": RoleLevel.CONSULTANT,  # 向后兼容
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
    secondary_roles = Column(JSON, default=list, nullable=False)
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
    assessment = relationship("Assessment", back_populates="work_item", uselist=False)
    non_assessment_item = relationship("NonAssessmentItem", back_populates="work_item", uselist=False)
    assessment_operation_logs = relationship("AssessmentOperationLog", back_populates="work_item", cascade="all, delete-orphan")


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
    """考核状态枚举"""
    pending_dept_confirm = "pending_dept_confirm"       # 待部门总监确认
    pending_district_score = "pending_district_score"   # 待区总评分
    pending_regulator_score = "pending_regulator_score" # 待监察主任评分
    pending_group_score = "pending_group_score"         # 待集团总监评分
    pending_supplement = "pending_supplement"           # 待补充凭证
    appeal_period = "appeal_period"                     # 异议期
    appealed = "appealed"                               # 已提异议
    ai_reviewing = "ai_reviewing"                       # AI审查中
    pending_ruling = "pending_ruling"                   # 待裁定
    completed = "completed"                             # 已完结
    cancelled = "cancelled"                             # 已终止


class ScoreLevel(str, Enum):
    """评分层级枚举"""
    district = "district"   # 区总评分（第1层）
    regulator = "regulator" # 监察主任评分（第2层）
    group = "group"         # 集团总监评分（第3层）


class AttachmentType(str, Enum):
    """附件类型枚举"""
    scoring = "scoring"       # 评分依据凭证
    supplement = "supplement" # 补充凭证
    appeal = "appeal"         # 异议凭证


class ScoreTier:
    """总分档位"""
    TIERS = {1, 5, 10, 20, 30}


class SupplementRequestStatus(str, Enum):
    """补充请求状态"""
    pending = "pending"
    completed = "completed"


class AppealStatus(str, Enum):
    """异议状态"""
    pending = "pending"          # 待补充意见
    ai_reviewing = "ai_reviewing" # AI审查中
    ai_completed = "ai_completed" # AI审查完成
    pending_ruling = "pending_ruling" # 待裁定
    closed = "closed"            # 已结案


# ======================================================================
# 区域 / 部门

# ======================================================================


class Assessment(Base):
    """考核主表 - 每个工作项一条考核记录"""
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=False, index=True)
    initiator_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    sponsor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False, index=True)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=True, index=True)
    status = Column(String(30), nullable=False, index=True)
    initiator_role_level = Column(Integer, nullable=True)
    current_level = Column(String(20), nullable=True)    # 当前评分层级 district/regulator/group
    supplement_by_level = Column(String(20), nullable=True)  # 哪一层要求补充的
    skip_dept_confirm = Column(Boolean, default=False, nullable=False)
    skip_district_score = Column(Boolean, default=False, nullable=False)
    skip_regulator_score = Column(Boolean, default=False, nullable=False)
    appeal_deadline = Column(DateTime, nullable=True, index=True)
    final_score = Column(Float, nullable=True)  # 最终得分（集团总监总分）
    initiated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    work_item = relationship("WorkItem", back_populates="assessment")
    initiator = relationship("User", foreign_keys=[initiator_id])
    sponsor = relationship("User", foreign_keys=[sponsor_id])
    department = relationship("Department", foreign_keys=[department_id])
    district = relationship("District", foreign_keys=[district_id])
    scores = relationship("AssessmentScore", back_populates="assessment", cascade="all, delete-orphan")
    attachments = relationship("AssessmentAttachment", back_populates="assessment", cascade="all, delete-orphan")
    supplement_requests = relationship("AssessmentSupplementRequest", back_populates="assessment", cascade="all, delete-orphan")
    appeal = relationship("AssessmentAppeal", back_populates="assessment", uselist=False)
    operation_logs = relationship("AssessmentOperationLog", back_populates="assessment", cascade="all, delete-orphan")

    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class AssessmentScore(Base):
    """每层评分记录"""
    __tablename__ = "assessment_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False, index=True)
    level = Column(String(20), nullable=False)  # district/regulator/group
    scorer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scorer_role_level = Column(Integer, nullable=True)
    total_score = Column(Integer, nullable=False)  # 1/5/10/20/30
    opinion = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assessment = relationship("Assessment", back_populates="scores")
    scorer = relationship("User", foreign_keys=[scorer_id])
    participants = relationship("AssessmentScoreParticipant", back_populates="score", cascade="all, delete-orphan")
    attachments = relationship("AssessmentAttachment", back_populates="score", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("assessment_id", "level", name="uq_assessment_score_level"),
        {"sqlite_autoincrement": True},
    )


class AssessmentScoreParticipant(Base):
    """参与人分数分配"""
    __tablename__ = "assessment_score_participants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    score_id = Column(Integer, ForeignKey("assessment_scores.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user_name = Column(String(50), nullable=False)  # 冗余，防用户改名
    score = Column(Float, nullable=False)  # 支持1位小数
    created_at = Column(DateTime, default=datetime.utcnow)

    score = relationship("AssessmentScore", back_populates="participants")
    user = relationship("User", foreign_keys=[user_id])


class AssessmentAttachment(Base):
    """附件凭证表"""
    __tablename__ = "assessment_attachments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False, index=True)
    type = Column(String(20), nullable=False, index=True)  # scoring/supplement/appeal
    score_id = Column(Integer, ForeignKey("assessment_scores.id"), nullable=True, index=True)
    supplement_request_id = Column(Integer, ForeignKey("assessment_supplement_requests.id"), nullable=True, index=True)
    appeal_id = Column(Integer, ForeignKey("assessment_appeals.id"), nullable=True, index=True)
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_type = Column(String(10), nullable=False)  # image/text
    file_name = Column(String(200), nullable=True)
    file_path = Column(String(500), nullable=True)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    assessment = relationship("Assessment", back_populates="attachments")
    score = relationship("AssessmentScore", back_populates="attachments")
    uploader = relationship("User", foreign_keys=[uploader_id])
    supplement_request = relationship("AssessmentSupplementRequest", back_populates="attachments")
    appeal = relationship("AssessmentAppeal", back_populates="attachments")


class AssessmentSupplementRequest(Base):
    """补充凭证请求"""
    __tablename__ = "assessment_supplement_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False, index=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    request_level = Column(String(20), nullable=False)  # district/regulator/group
    request_note = Column(Text, nullable=False)
    status = Column(String(20), default=SupplementRequestStatus.pending.value, nullable=False)
    submitted_at = Column(DateTime, nullable=True)
    supplier_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    assessment = relationship("Assessment", back_populates="supplement_requests")
    requester = relationship("User", foreign_keys=[requester_id])
    supplier = relationship("User", foreign_keys=[supplier_id])
    attachments = relationship("AssessmentAttachment", back_populates="supplement_request", cascade="all, delete-orphan")


class AssessmentAppeal(Base):
    """异议记录"""
    __tablename__ = "assessment_appeals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False, unique=True)
    appellant_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    regulator_comment = Column(Text, nullable=True)
    group_director_comment = Column(Text, nullable=True)
    ai_opinion = Column(Text, nullable=True)
    ai_status = Column(String(20), default="pending", nullable=False)  # pending/processing/completed/failed
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ai_completed_at = Column(DateTime, nullable=True)
    ruling_result = Column(Text, nullable=True)
    ruled_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    ruled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    assessment = relationship("Assessment", back_populates="appeal")
    appellant = relationship("User", foreign_keys=[appellant_id])
    ruler = relationship("User", foreign_keys=[ruled_by])
    attachments = relationship("AssessmentAttachment", back_populates="appeal", cascade="all, delete-orphan")


class NonAssessmentItem(Base):
    """非考核项标记"""
    __tablename__ = "non_assessment_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=False, unique=True)
    marked_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    remark = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    revoked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    work_item = relationship("WorkItem", back_populates="non_assessment_item")
    marker = relationship("User", foreign_keys=[marked_by])
    revoker = relationship("User", foreign_keys=[revoked_by])


class AssessmentOperationLog(Base):
    """操作日志"""
    __tablename__ = "assessment_operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=True, index=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=False, index=True)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False, index=True)  # initiate/dept_confirm/district_score/...
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    assessment = relationship("Assessment", back_populates="operation_logs")
    work_item = relationship("WorkItem", back_populates="assessment_operation_logs")
    operator = relationship("User", foreign_keys=[operator_id])
