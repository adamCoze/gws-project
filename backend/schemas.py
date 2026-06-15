"""Pydantic 数据模型"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr


# Auth
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Department
class DepartmentOut(BaseModel):
    id: int
    name: str
    code: str
    created_at: datetime

    class Config:
        from_attributes = True


class DepartmentCreate(BaseModel):
    name: str
    code: str


# User
class UserOut(BaseModel):
    id: int
    username: str
    email: str
    email_prefix: str
    role: str
    department_id: Optional[int] = None
    department: Optional[DepartmentOut] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    password: str
    email: str
    email_prefix: str
    role: str = "staff"
    department_id: Optional[int] = None
    is_active: bool = True


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    email_prefix: Optional[str] = None
    role: Optional[str] = None
    department_id: Optional[int] = None
    is_active: Optional[bool] = None


class ResetPasswordRequest(BaseModel):
    password: str


# WorkItem
class WorkItemOut(BaseModel):
    id: int
    title: str
    content: str
    item_type: str
    status: str
    department_id: int
    department: Optional[DepartmentOut] = None
    assignee_id: Optional[int] = None
    assignee: Optional[UserOut] = None
    assignee_email_prefix: Optional[str] = None
    due_date: Optional[str] = None
    is_confidential: bool
    email_subject: Optional[str] = None
    email_from: Optional[str] = None
    email_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkItemCreate(BaseModel):
    title: str
    content: str
    item_type: str = "task"
    status: str = "pending"
    department_id: int
    assignee_email_prefix: Optional[str] = None
    due_date: Optional[str] = None
    is_confidential: bool = False
    email_subject: Optional[str] = None
    email_from: Optional[str] = None


class WorkItemUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    item_type: Optional[str] = None
    status: Optional[str] = None
    department_id: Optional[int] = None
    assignee_email_prefix: Optional[str] = None
    due_date: Optional[str] = None
    is_confidential: Optional[bool] = None


class StatusUpdateRequest(BaseModel):
    status: str
    remark: str = ""


# StatusLog
class StatusLogOut(BaseModel):
    id: int
    work_item_id: int
    old_status: str
    new_status: str
    operator_id: int
    operator: Optional[UserOut] = None
    remark: str
    created_at: datetime

    class Config:
        from_attributes = True


# EmailConfig
class EmailConfigOut(BaseModel):
    id: int
    email_address: str
    imap_host: str
    imap_port: int
    username: str
    is_active: bool
    last_check_at: Optional[datetime] = None
    check_interval: int
    created_at: datetime

    class Config:
        from_attributes = True


class EmailConfigCreate(BaseModel):
    email_address: str
    imap_host: str = "imap.qiye.aliyun.com"
    imap_port: int = 993
    username: str
    password: str
    check_interval: int = 5
    is_active: bool = True


class EmailConfigUpdate(BaseModel):
    email_address: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    check_interval: Optional[int] = None
    is_active: Optional[bool] = None


# Holiday
class HolidayOut(BaseModel):
    id: int
    name: str
    date: str
    year: int
    created_at: datetime

    class Config:
        from_attributes = True


class HolidayCreate(BaseModel):
    name: str
    date: str
    year: int


# Kanban
class KanbanDeptData(BaseModel):
    department_id: int
    department_name: str
    pending: List[WorkItemOut]
    in_progress: List[WorkItemOut]
    completed: List[WorkItemOut]
    overdue: List[WorkItemOut]
