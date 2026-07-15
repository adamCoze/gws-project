"""Pydantic 数据模型"""
from datetime import datetime, date
from typing import Optional, List, Any

from pydantic import BaseModel, EmailStr, model_validator

from models import RoleType, WorkItemStatus, WorkItemType, EmailProcessResult


# ========== User ==========

class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    email_prefix: Optional[str] = None
    real_name: Optional[str] = None
    role: str = "staff"
    department_id: Optional[int] = None
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
    department_id: Optional[int] = None
    region: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None


class UserOut(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ========== Department ==========

class DepartmentBase(BaseModel):
    name: str
    code: str


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentOut(DepartmentBase):
    id: int
    created_at: datetime

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
