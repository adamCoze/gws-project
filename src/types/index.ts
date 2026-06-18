export type UserRole = 'admin' | 'president' | 'regulator' | 'district_manager' | 'manager' | 'staff';
export type RoleType = UserRole;
export type WorkItemStatus = 'pending' | 'completed' | 'overdue' | 'cancelled';
export type WorkItemType = 'task' | 'cosign';
export type EmailProcessResult = 'success' | 'ai_failed' | 'retry';

export const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  president: '总裁',
  regulator: '规管',
  district_manager: '区总',
  manager: '经理',
  staff: '专员',
};

export const ROLE_LEVELS: Record<string, number> = {
  staff: 1,
  manager: 2,
  district_manager: 3,
  regulator: 4,
  president: 5,
  admin: 6,
};

export const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  completed: '已完成',
  overdue: '已逾时',
  cancelled: '不再进行',
};

export const STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  completed: 'success',
  overdue: 'error',
  cancelled: 'default',
};

export interface Department {
  id: number;
  name: string;
  code: string;
  created_at: string;
}

export interface User {
  id: number;
  username: string;
  email?: string;
  email_prefix?: string;
  real_name?: string;
  role: UserRole;
  department_id?: number;
  region?: string;
  is_active: boolean;
  created_at: string;
  department?: Department;
}

export interface StatusChangeLog {
  id: number;
  work_item_id: number;
  work_item_title?: string;
  old_status?: WorkItemStatus;
  new_status: WorkItemStatus;
  changed_by?: string;
  remark?: string;
  created_at: string;
}

export interface WorkItem {
  id: number;
  title: string;
  content?: string;
  item_type: WorkItemType;
  status: WorkItemStatus;
  department_id?: number;
  assignee_id?: number;
  assignee_email_prefix?: string;
  due_date?: string;
  is_confidential: boolean;
  email_subject?: string;
  email_from?: string;
  email_date?: string;
  latest_progress?: string;
  created_at: string;
  updated_at: string;
  department?: Department;
  assignee?: User;
  status_logs?: StatusChangeLog[];
}

export interface EmailConfig {
  id: number;
  email_address: string;
  imap_host: string;
  imap_port: number;
  username: string;
  is_active: boolean;
  last_check_at?: string;
  created_at: string;
}

export interface EmailLog {
  id: number;
  message_id: string;
  subject?: string;
  from_addr?: string;
  received_at: string;
  process_result: EmailProcessResult;
  retry_count: number;
  error_message?: string;
  work_item_id?: number;
  created_at: string;
}

export interface SystemConfig {
  id: number;
  config_key: string;
  config_value?: string;
  updated_at?: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  user: User;
}
