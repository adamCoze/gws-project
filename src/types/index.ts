export type UserRole = 'admin' | 'staff';
export type RoleType = 'admin' | 'staff';
export type WorkItemStatus = 'pending' | 'in_progress' | 'completed' | 'overdue';
export type WorkItemType = 'task' | 'cosign';
export type EmailProcessResult = 'success' | 'ai_failed' | 'retry';

export const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  staff: '普通用户',
};

export const ROLE_LEVELS: Record<string, number> = {
  admin: 1,
  staff: 2,
};

export const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  in_progress: '进行中',
  completed: '已完成',
  overdue: '已逾期',
};

export const STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  in_progress: 'processing',
  completed: 'success',
  overdue: 'error',
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
  is_active: boolean;
  created_at: string;
  department?: Department;
}

export interface StatusChangeLog {
  id: number;
  work_item_id: number;
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
