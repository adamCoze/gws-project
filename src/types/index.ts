// 角色类型
export type RoleType = 'admin' | 'president' | 'regulator' | 'district_manager' | 'manager' | 'staff';

// 角色显示名称
export const ROLE_LABELS: Record<RoleType, string> = {
  admin: '管理员',
  president: '总裁',
  regulator: '规管',
  district_manager: '区总',
  manager: '经理',
  staff: '专员',
};

// 角色等级（数字越大权限越高）
export const ROLE_LEVELS: Record<RoleType, number> = {
  staff: 1,
  manager: 2,
  district_manager: 3,
  regulator: 3,
  president: 4,
  admin: 5,
};

// 工作项类型
export type WorkItemType = 'task' | 'cosign';

// 工作项状态
export type WorkItemStatus = 'pending' | 'in_progress' | 'completed' | 'overdue';

export const STATUS_LABELS: Record<WorkItemStatus, string> = {
  pending: '待处理',
  in_progress: '进行中',
  completed: '已完成',
  overdue: '已逾期',
};

export const STATUS_COLORS: Record<WorkItemStatus, string> = {
  pending: 'default',
  in_progress: 'processing',
  completed: 'success',
  overdue: 'error',
};

// 邮件处理结果
export type EmailProcessResult = 'SUCCESS' | 'AI_FAILED' | 'RETRY';

export const EMAIL_PROCESS_RESULT_LABELS: Record<EmailProcessResult, string> = {
  SUCCESS: '成功',
  AI_FAILED: 'AI分析失败',
  RETRY: '重试',
};

export const EMAIL_PROCESS_RESULT_COLORS: Record<EmailProcessResult, string> = {
  SUCCESS: 'success',
  AI_FAILED: 'error',
  RETRY: 'warning',
};

// 部门
export interface Department {
  id: number;
  name: string;
  code: string;
  created_at: string;
}

// 用户
export interface User {
  id: number;
  username: string;
  email: string;
  email_prefix: string;
  role: RoleType;
  department_id: number | null;
  department?: Department;
  is_active: boolean;
  created_at: string;
}

// 工作项
export interface WorkItem {
  id: number;
  title: string;
  content: string;
  item_type: WorkItemType;
  status: WorkItemStatus;
  department_id: number;
  department?: Department;
  assignee_id: number | null;
  assignee?: User;
  assignee_email_prefix: string;
  due_date: string | null;
  is_confidential: boolean;
  email_subject: string;
  email_from: string;
  email_date: string;
  created_at: string;
  updated_at: string;
}

// 状态变更日志
export interface StatusChangeLog {
  id: number;
  work_item_id: number;
  old_status: WorkItemStatus;
  new_status: WorkItemStatus;
  operator_id: number;
  operator?: User;
  remark: string;
  created_at: string;
}

// 邮箱配置
export interface EmailConfig {
  id: number;
  email_address: string;
  imap_host: string;
  imap_port: number;
  username: string;
  password: string;
  is_active: boolean;
  last_check_at: string | null;
  check_interval: number;
  created_at: string;
}

// 邮件处理日志
export interface EmailLog {
  id: number;
  message_id: string;
  subject: string | null;
  from_addr: string | null;
  received_at: string | null;
  process_result: EmailProcessResult;
  retry_count: number;
  error_message: string | null;
  work_item_id: number | null;
  created_at: string;
}

// 系统配置
export interface SystemConfig {
  id: number;
  config_key: string;
  config_value: string | null;
  description: string | null;
  updated_at: string;
}

// 节假日
export interface Holiday {
  id: number;
  name: string;
  date: string;
  year: number;
  created_at: string;
}

// 登录请求
export interface LoginRequest {
  username: string;
  password: string;
}

// 登录响应
export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// 看板数据
export interface KanbanData {
  department_id: number;
  department_name: string;
  pending: WorkItem[];
  in_progress: WorkItem[];
  completed: WorkItem[];
  overdue: WorkItem[];
}
