export type UserRole = 'admin' | 'president' | 'regulator' | 'district_manager' | 'manager' | 'staff' | 'consultant';
export type RoleType = UserRole;
export type WorkItemStatus = 'pending' | 'completed' | 'overdue' | 'cancelled';
export type WorkItemType = 'task' | 'cosign';
export type EmailProcessResult = 'success' | 'ai_failed' | 'retry';

// 9级角色等级
export const ROLE_LEVEL = {
  CONSULTANT: 1,
  STAFF: 2,
  MANAGER: 3,
  DISTRICT_MANAGER: 4,
  DEPT_DIRECTOR: 5,
  REGULATOR: 6,
  GROUP_DIRECTOR: 7,
  PRESIDENT: 8,
  ADMIN: 9,
} as const;

export type RoleLevel = typeof ROLE_LEVEL[keyof typeof ROLE_LEVEL];

// 角色等级标签
export const ROLE_LEVEL_LABELS: Record<number, string> = {
  1: '顾问',
  2: '专员',
  3: '经理',
  4: '区域总监',
  5: '部门总监',
  6: '监察主任',
  7: '集团总监',
  8: '总裁',
  9: '管理员',
};

// 角色等级选项（用于下拉选择）
export const ROLE_LEVEL_OPTIONS = [
  { value: 1, label: '顾问' },
  { value: 2, label: '专员' },
  { value: 3, label: '经理' },
  { value: 4, label: '区域总监' },
  { value: 5, label: '部门总监' },
  { value: 6, label: '监察主任' },
  { value: 7, label: '集团总监' },
  { value: 8, label: '总裁' },
  { value: 9, label: '管理员' },
];

export const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  president: '总裁',
  regulator: '监察主任',
  district_manager: '区域总监',
  manager: '经理',
  staff: '专员',
  consultant: '顾问',
  intern: '顾问',
};

// 向后兼容：旧代码通过 role 字符串获取等级
// 新代码应直接使用 user.role_level 字段
export const ROLE_LEVELS: Record<string, number> = {
  consultant: 1,
  intern: 1,
  staff: 2,
  manager: 3,
  district_manager: 4,
  dept_director: 5,
  regulator: 6,
  group_director: 7,
  president: 8,
  admin: 9,
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

export const TYPE_LABELS: Record<string, string> = {
  task: '任务',
  cosign: '会签',
  report: '汇报',
};

export const TYPE_COLORS: Record<string, string> = {
  task: 'blue',
  cosign: 'purple',
  report: 'cyan',
};

export interface District {
  id: number;
  name: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Department {
  id: number;
  name: string;
  code: string;
  district_id?: number;
  created_at: string;
  district?: District;
}

export interface User {
  id: number;
  username: string;
  email?: string;
  email_prefix?: string;
  real_name?: string;
  role: UserRole;
  role_level: RoleLevel;
  secondary_roles: number[];
  department_id?: number;
  district_id?: number;
  region?: string;
  is_active: boolean;
  created_at: string;
  department?: Department;
  district?: District;
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
  assignee_names?: string;
  due_date?: string;
  is_confidential: boolean;
  sponsor_id?: number;
  completed_by?: number;
  completed_at?: string;
  email_subject?: string;
  email_from?: string;
  email_date?: string;
  message_id?: string;
  sender_email?: string;
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
// ============ 考核模块 ============

export type AssessmentStatus = 'draft' | 'scoring' | 'reviewing' | 'completed' | 'cancelled';

export const ASSESSMENT_STATUS_LABELS: Record<AssessmentStatus, string> = {
  draft: '草稿',
  scoring: '评分中',
  reviewing: '复核中',
  completed: '已完成',
  cancelled: '已取消',
};

export const ASSESSMENT_STATUS_COLORS: Record<AssessmentStatus, string> = {
  draft: 'default',
  scoring: 'processing',
  reviewing: 'warning',
  completed: 'success',
  cancelled: 'default',
};

export const ASSESSMENT_STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'scoring', label: '评分中' },
  { value: 'reviewing', label: '复核中' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
];

export interface Assessment {
  id: number;
  title: string;
  year: number;
  month: number;
  status: AssessmentStatus;
  description?: string;
  initiator_role_level?: number;
  initiator_department_id?: number;
  initiator_district_id?: number;
  created_by?: number;
  created_at: string;
  updated_at: string;
  creator?: User;
  scores_count?: number;
}

export interface AssessmentScore {
  id: number;
  assessment_id: number;
  work_item_id: number;
  scorer_id?: number;
  scorer_role_level?: number;
  scorer_department_id?: number;
  scorer_district_id?: number;
  level: number;
  score?: number;
  comment?: string;
  scored_at?: string;
  created_at: string;
  work_item?: WorkItem;
  scorer?: User;
}

export interface AssessmentOperationLog {
  id: number;
  assessment_id: number;
  action: string;
  operator_id?: number;
  operator?: User;
  remark?: string;
  created_at: string;
}

export interface PendingScore {
  id: number;
  assessment_id: number;
  assessment_title: string;
  work_item_id: number;
  work_item_title: string;
  assignee_name?: string;
  level: number;
  status: 'pending' | 'scored';
  created_at: string;
}

// 评分档位
export const SCORE_OPTIONS = [
  { value: 1, label: '1分 - 待改进' },
  { value: 5, label: '5分 - 一般' },
  { value: 10, label: '10分 - 良好' },
  { value: 20, label: '20分 - 优秀' },
  { value: 30, label: '30分 - 卓越' },
];
