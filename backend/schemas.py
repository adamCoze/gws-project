"""Pydantic 数据模型"""
from datetime import datetime, date
from typing import Optional, List, Any

from pydantic import BaseModel, EmailStr, model_validator

from models import RoleType, WorkItemStatus, WorkItemType, EmailProcessResult


# ========== 通用：角色等级选项 ==========

ROLE_LEVEL_OPTIONS = [
    (1, "顾问"),
    (2, "专员"),
    (3, "经理"),
    (4, "区域总监"),
    (5, "部门总监"),
    (6, "监察主任"),
    (7, "集团总监"),
    (8, "总裁"),
    (9, "管理员"),
]

ROLE_LEVEL_LABELS = {level: label for level, label in ROLE_LEVEL_OPTIONS}


# ========== District ==========

class DistrictBase(BaseModel):
    name: str
    sort_order: int = 0
    is_active: bool = True


class DistrictCreate(DistrictBase):
    pass


class DistrictUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class DistrictOut(DistrictBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ========== User ==========

class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    email_prefix: Optional[str] = None
    real_name: Optional[str] = None
    role: str = "staff"
    role_level: int = 2
    secondary_roles: Optional[List[dict]] = None
    department_id: Optional[int] = None
    district_id: Optional[int] = None
    region: Optional[str] = None


class UserCreate(UserBase):
    password: str
    is_active: bool = True


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    email_prefix: Optional[str] = None
    real_name: Optional[str] = None
    role: Optional[str] = None
    role_level: Optional[int] = None
    secondary_roles: Optional[List[dict]] = None
    department_id: Optional[int] = None
    district_id: Optional[int] = None
    region: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None


class UserOut(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    department: Optional["DepartmentOut"] = None
    district: Optional[DistrictOut] = None

    class Config:
        from_attributes = True


class UserBriefOut(BaseModel):
    id: int
    real_name: Optional[str] = None
    username: str
    email_prefix: Optional[str] = None
    role_level: int = 2
    secondary_roles: List[dict]

    class Config:
        from_attributes = True


# ========== Department ==========

class DepartmentBase(BaseModel):
    name: str
    code: str
    district_id: Optional[int] = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    district_id: Optional[int] = None


class DepartmentOut(DepartmentBase):
    id: int
    created_at: datetime
    district: Optional[DistrictOut] = None

    class Config:
        from_attributes = True


# ========== WorkItem ==========

class WorkItemBase(BaseModel):
    title: str
    content: Optional[str] = None
    item_type: str = "task"
    status: str = "pending"
    department_id: Optional[int] = None
    assignee_id: Optional[int] = None
    assignee_email_prefix: Optional[str] = None
    due_date: Optional[datetime] = None
    is_confidential: bool = False


class WorkItemCreate(WorkItemBase):
    pass


class WorkItemUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    item_type: Optional[str] = None
    status: Optional[str] = None
    department_id: Optional[int] = None
    assignee_id: Optional[int] = None
    assignee_email_prefix: Optional[str] = None
    due_date: Optional[datetime] = None
    is_confidential: Optional[bool] = None
    latest_progress: Optional[str] = None


class StatusChangeRequest(BaseModel):
    status: str
    remark: Optional[str] = None


class StatusChangeLogOut(BaseModel):
    id: int
    work_item_id: int
    work_item_title: Optional[str] = None
    old_status: Optional[str]
    new_status: str
    operator_id: Optional[int] = None
    changed_by: Optional[str] = None
    remark: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

    @model_validator(mode='before')
    @classmethod
    def populate_fields(cls, data: Any) -> Any:
        # 从 work_item 关系中提取标题
        if hasattr(data, 'work_item') and data.work_item:
            if hasattr(data.work_item, 'title'):
                data.work_item_title = data.work_item.title
        # 从 operator 关系中提取用户名
        if hasattr(data, 'operator') and data.operator:
            if hasattr(data.operator, 'real_name') and data.operator.real_name:
                data.changed_by = data.operator.real_name
            elif hasattr(data.operator, 'username'):
                data.changed_by = data.operator.username
        return data


class WorkItemOut(WorkItemBase):
    id: int
    message_id: Optional[str] = None
    email_subject: Optional[str] = None
    email_from: Optional[str] = None
    sender_email: Optional[str] = None
    email_date: Optional[datetime] = None
    latest_progress: Optional[str] = None
    sponsor_id: Optional[int] = None
    completed_by: Optional[int] = None
    completed_at: Optional[datetime] = None
    assignee_names: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    department: Optional[DepartmentOut] = None
    assignee: Optional[UserOut] = None
    status_logs: List[StatusChangeLogOut] = []

    class Config:
        from_attributes = True


# ========== Kanban ==========

class KanbanDeptData(BaseModel):
    department_id: int
    department_name: str
    pending: List[WorkItemOut] = []
    overdue: List[WorkItemOut] = []
    completed: List[WorkItemOut] = []
    cancelled: List[WorkItemOut] = []


# ========== Holiday ==========

class HolidayCreate(BaseModel):
    name: str
    date: str
    year: int


class HolidayOut(HolidayCreate):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ========== EmailConfig ==========

class EmailConfigBase(BaseModel):
    email_address: str
    imap_host: str
    imap_port: int = 993
    username: str
    is_active: bool = True


class EmailConfigCreate(EmailConfigBase):
    password: str


class EmailConfigUpdate(BaseModel):
    email_address: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None


class EmailConfigOut(EmailConfigBase):
    id: int
    last_check_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ========== EmailLog ==========

class EmailLogOut(BaseModel):
    id: int
    message_id: str
    subject: Optional[str]
    from_addr: Optional[str]
    received_at: datetime
    process_result: str
    retry_count: int
    error_message: Optional[str]
    work_item_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ========== SystemConfig ==========

class SystemConfigBase(BaseModel):
    config_key: str
    config_value: Optional[str] = None


class SystemConfigCreate(SystemConfigBase):
    pass


class SystemConfigUpdate(BaseModel):
    config_value: str


class SystemConfigOut(SystemConfigBase):
    id: int
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ========== Auth ==========

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenResponse(BaseModel):
    access_token: str
    user: UserOut


class LoginRequest(BaseModel):
    username: str
    password: str


class ResetPasswordRequest(BaseModel):
    password: str


# ========== Email URL ==========

class EmailUrlResponse(BaseModel):
    url: Optional[str] = None
    error: Optional[str] = None
    search_url: Optional[str] = None


class EmailLinkStatusResponse(BaseModel):
    """批量查询工作项邮件链接状态"""
    items: dict  # {work_item_id: bool} - True=有链接, False=无链接


# ======================================================================


# ---- 通用：附件 ----

class AssessmentAttachmentBase(BaseModel):
    file_type: str  # image/text
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    content: Optional[str] = None


class AssessmentAttachmentOut(BaseModel):
    id: int
    type: str  # scoring/supplement/appeal
    uploader_id: int
    uploader_name: Optional[str] = None
    file_type: str
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    content: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @model_validator(mode='before')
    @classmethod
    def populate_uploader_name(cls, data: Any) -> Any:
        if hasattr(data, 'uploader') and data.uploader:
            data.uploader_name = data.uploader.real_name or data.uploader.username
        return data


# ---- 参与人分配 ----

class ScoreParticipantCreate(BaseModel):
    user_id: int
    score: float  # 支持1位小数


class ScoreParticipantOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    score: float

    class Config:
        from_attributes = True


# ---- 评分记录 ----

class ScoreSubmitRequest(BaseModel):
    total_score: int  # 1/5/10/20/30
    opinion: Optional[str] = None
    participants: List[ScoreParticipantCreate] = []
    attachments: List[AssessmentAttachmentBase] = []


class AssessmentScoreOut(BaseModel):
    id: int
    assessment_id: int
    level: str  # district/regulator/group
    scorer_id: int
    scorer_name: Optional[str] = None
    total_score: int
    opinion: Optional[str] = None
    submitted_at: datetime
    participants: List[ScoreParticipantOut] = []
    attachments: List[AssessmentAttachmentOut] = []

    class Config:
        from_attributes = True

    @model_validator(mode='before')
    @classmethod
    def populate_scorer_name(cls, data: Any) -> Any:
        if hasattr(data, 'scorer') and data.scorer:
            data.scorer_name = data.scorer.real_name or data.scorer.username
        return data


# ---- 补充凭证请求 ----

class SupplementRequestCreate(BaseModel):
    note: str  # 要求补充的说明


class SupplementSubmitRequest(BaseModel):
    supplement_request_id: int
    response: Optional[str] = None
    attachments: List[AssessmentAttachmentBase] = []


class SupplementRequestOut(BaseModel):
    id: int
    assessment_id: int
    requester_id: int
    requester_name: Optional[str] = None
    request_level: str
    request_note: str
    status: str
    submitted_at: Optional[datetime] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    created_at: datetime
    attachments: List[AssessmentAttachmentOut] = []

    class Config:
        from_attributes = True

    @model_validator(mode='before')
    @classmethod
    def populate_names(cls, data: Any) -> Any:
        if hasattr(data, 'requester') and data.requester:
            data.requester_name = data.requester.real_name or data.requester.username
        if hasattr(data, 'supplier') and data.supplier:
            data.supplier_name = data.supplier.real_name or data.supplier.username
        return data


# ---- 非考核项 ----

class NonAssessmentMarkRequest(BaseModel):
    remark: Optional[str] = None


class NonAssessmentItemOut(BaseModel):
    id: int
    work_item_id: int
    work_item_title: Optional[str] = None
    marked_by: int
    marker_name: Optional[str] = None
    remark: Optional[str] = None
    is_active: bool
    revoked_by: Optional[int] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @model_validator(mode='before')
    @classmethod
    def populate_fields(cls, data: Any) -> Any:
        if hasattr(data, 'work_item') and data.work_item:
            data.work_item_title = data.work_item.title
        if hasattr(data, 'marker') and data.marker:
            data.marker_name = data.marker.real_name or data.marker.username
        return data


# ---- 待考核项 ----

class PendingAssessmentItemOut(BaseModel):
    work_item_id: int
    title: str
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    district_id: Optional[int] = None
    district_name: Optional[str] = None
    sponsor_id: Optional[int] = None
    sponsor_name: Optional[str] = None
    completed_at: Optional[datetime] = None
    has_email: bool = False
    email_url: Optional[str] = None


# ---- 考核列表项（我的考核 / 待办列表）----

class AssessmentListItemOut(BaseModel):
    id: int
    work_item_id: int
    work_item_title: str
    status: str
    status_text: str = ""
    current_level: Optional[str] = None
    sponsor_id: int
    sponsor_name: Optional[str] = None
    department_name: Optional[str] = None
    district_name: Optional[str] = None
    final_score: Optional[float] = None
    appeal_deadline: Optional[datetime] = None
    initiated_at: datetime
    has_email: bool = False

    class Config:
        from_attributes = True

    @model_validator(mode='before')
    @classmethod
    def populate_fields(cls, data: Any) -> Any:
        if hasattr(data, 'work_item') and data.work_item:
            data.work_item_title = data.work_item.title
            data.has_email = bool(data.work_item.message_id)
        if hasattr(data, 'sponsor') and data.sponsor:
            data.sponsor_name = data.sponsor.real_name or data.sponsor.username
        if hasattr(data, 'department') and data.department:
            data.department_name = data.department.name
        if hasattr(data, 'district') and data.district:
            data.district_name = data.district.name
        # 状态中文
        from models import AssessmentStatus
        status_map = {
            AssessmentStatus.pending_dept_confirm.value: "待部门总监确认",
            AssessmentStatus.pending_district_score.value: "待区总评分",
            AssessmentStatus.pending_regulator_score.value: "待监察主任评分",
            AssessmentStatus.pending_group_score.value: "待集团总监评分",
            AssessmentStatus.pending_supplement.value: "待补充凭证",
            AssessmentStatus.appeal_period.value: "异议期",
            AssessmentStatus.appealed.value: "已提异议",
            AssessmentStatus.ai_reviewing.value: "AI审查中",
            AssessmentStatus.pending_ruling.value: "待裁定",
            AssessmentStatus.completed.value: "已完结",
            AssessmentStatus.cancelled.value: "已终止",
        }
        if hasattr(data, 'status'):
            data.status_text = status_map.get(data.status, data.status)
        return data


# ---- 考核详情 ----

class AssessmentDetailOut(BaseModel):
    id: int
    work_item_id: int
    work_item_title: str
    work_item_content: Optional[str] = None
    status: str
    status_text: str = ""
    current_level: Optional[str] = None
    supplement_by_level: Optional[str] = None
    initiator_id: int
    initiator_name: Optional[str] = None
    sponsor_id: int
    sponsor_name: Optional[str] = None
    department_id: int
    department_name: Optional[str] = None
    district_id: Optional[int] = None
    district_name: Optional[str] = None
    skip_dept_confirm: bool = False
    skip_district_score: bool = False
    skip_regulator_score: bool = False
    final_score: Optional[float] = None
    appeal_deadline: Optional[datetime] = None
    initiated_at: datetime
    completed_at: Optional[datetime] = None
    has_email: bool = False
    email_message_id: Optional[str] = None
    scores: List[AssessmentScoreOut] = []
    supplement_requests: List[SupplementRequestOut] = []
    operation_logs: List["OperationLogOut"] = []

    class Config:
        from_attributes = True

    @model_validator(mode='before')
    @classmethod
    def populate_fields(cls, data: Any) -> Any:
        if hasattr(data, 'work_item') and data.work_item:
            data.work_item_title = data.work_item.title
            data.work_item_content = data.work_item.content
            data.has_email = bool(data.work_item.message_id)
            data.email_message_id = data.work_item.message_id
        if hasattr(data, 'initiator') and data.initiator:
            data.initiator_name = data.initiator.real_name or data.initiator.username
        if hasattr(data, 'sponsor') and data.sponsor:
            data.sponsor_name = data.sponsor.real_name or data.sponsor.username
        if hasattr(data, 'department') and data.department:
            data.department_name = data.department.name
        if hasattr(data, 'district') and data.district:
            data.district_name = data.district.name
        from models import AssessmentStatus
        status_map = {
            AssessmentStatus.pending_dept_confirm.value: "待部门总监确认",
            AssessmentStatus.pending_district_score.value: "待区总评分",
            AssessmentStatus.pending_regulator_score.value: "待监察主任评分",
            AssessmentStatus.pending_group_score.value: "待集团总监评分",
            AssessmentStatus.pending_supplement.value: "待补充凭证",
            AssessmentStatus.appeal_period.value: "异议期",
            AssessmentStatus.appealed.value: "已提异议",
            AssessmentStatus.ai_reviewing.value: "AI审查中",
            AssessmentStatus.pending_ruling.value: "待裁定",
            AssessmentStatus.completed.value: "已完结",
            AssessmentStatus.cancelled.value: "已终止",
        }
        if hasattr(data, 'status'):
            data.status_text = status_map.get(data.status, data.status)
        return data


# ---- 操作日志 ----

class OperationLogOut(BaseModel):
    id: int
    assessment_id: Optional[int] = None
    work_item_id: int
    operator_id: int
    operator_name: Optional[str] = None
    action: str
    action_text: str = ""
    detail: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @model_validator(mode='before')
    @classmethod
    def populate_fields(cls, data: Any) -> Any:
        if hasattr(data, 'operator') and data.operator:
            data.operator_name = data.operator.real_name or data.operator.username
        action_map = {
            "initiate": "发起考核",
            "dept_confirm": "部门总监确认",
            "dept_reject": "部门总监退回",
            "district_score": "区总评分",
            "regulator_score": "监察主任评分",
            "group_score": "集团总监评分",
            "request_supplement": "要求补充凭证",
            "submit_supplement": "提交补充凭证",
            "appeal_submit": "提交异议",
            "regulator_comment": "监察补充意见",
            "group_comment": "集团总监补充意见",
            "ai_review_complete": "AI审查完成",
            "mark_non_assessment": "标记非考核项",
            "revoke_non_assessment": "撤销非考核项",
            "cancel": "考核终止",
        }
        if hasattr(data, 'action'):
            data.action_text = action_map.get(data.action, data.action)
        return data


# ---- 跳过规则查询 ----

class SkipRuleInfoOut(BaseModel):
    skip_dept_confirm: bool = False
    skip_district_score: bool = False
    skip_regulator_score: bool = False
    initial_status: str
    reason: str = ""


# ---- 发起考核响应 ----

class InitiateAssessmentResponse(BaseModel):
    assessment_id: int
    status: str
    status_text: str = ""
    message: str = ""


# ---- 通用响应 ----

class SuccessResponse(BaseModel):
    success: bool = True
    message: Optional[str] = None


# ---- 分页响应 ----

class PaginatedResponse(BaseModel):
    total: int
    items: List[Any]


# ---- 异议 ----

class AppealCreateRequest(BaseModel):
    reason: str
    attachments: List[AssessmentAttachmentBase] = []


class AppealOut(BaseModel):
    id: int
    assessment_id: int
    appellant_id: int
    appellant_name: Optional[str] = None
    reason: str
    regulator_comment: Optional[str] = None
    group_director_comment: Optional[str] = None
    ai_opinion: Optional[str] = None
    ai_status: str = "pending"
    submitted_at: datetime
    ai_completed_at: Optional[datetime] = None
    attachments: List[AssessmentAttachmentOut] = []

    class Config:
        from_attributes = True

    @model_validator(mode='before')
    @classmethod
    def populate_appellant_name(cls, data: Any) -> Any:
        if hasattr(data, 'appellant') and data.appellant:
            data.appellant_name = data.appellant.real_name or data.appellant.username
        return data


class AppealCommentRequest(BaseModel):
    comment: str


# 前向引用解析
AssessmentDetailOut.model_rebuild()
