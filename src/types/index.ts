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
// ============ 考核模块（需求v0.3完整版） ============

// 考核状态机
export type AssessmentStatus =
  | 'pending_dept_confirm'       // 待部门总监确认
  | 'pending_district_score'     // 待区总评分
  | 'pending_regulator_score'    // 待监察主任评分
  | 'pending_group_score'        // 待集团总监评分
  | 'pending_supplement'         // 待补充凭证
  | 'appeal_period'              // 异议期
  | 'appealed'                   // 已提异议
  | 'ai_reviewing'               // AI审查中
  | 'pending_ruling'             // 待裁定
  | 'completed'                  // 已完结
  | 'cancelled';                 // 已终止

export const ASSESSMENT_STATUS_LABELS: Record<string, string> = {
  pending_dept_confirm: '待部门总监确认',
  pending_district_score: '待区总评分',
  pending_regulator_score: '待监察主任评分',
  pending_group_score: '待集团总监评分',
  pending_supplement: '待补充凭证',
  appeal_period: '异议期',
  appealed: '已提异议',
  ai_reviewing: 'AI审查中',
  pending_ruling: '待裁定',
  completed: '已完结',
  cancelled: '已终止',
};

export const ASSESSMENT_STATUS_COLORS: Record<string, string> = {
  pending_dept_confirm: 'gold',
  pending_district_score: 'processing',
  pending_regulator_score: 'processing',
  pending_group_score: 'processing',
  pending_supplement: 'warning',
  appeal_period: 'purple',
  appealed: 'magenta',
  ai_reviewing: 'geekblue',
  pending_ruling: 'volcano',
  completed: 'success',
  cancelled: 'default',
};

// 评分层级
export type ScoreLevel = 'district' | 'regulator' | 'group';
export const SCORE_LEVEL_LABELS: Record<string, string> = {
  district: '区总评分',
  regulator: '监察主任评分',
  group: '集团总监评分',
};

// 总分档位
export const SCORE_TIERS = [1, 5, 10, 20, 30];

// 凭证附件
export interface AssessmentAttachment {
  id?: number;
  file_type: 'image' | 'text';
  file_name?: string | null;
  file_path?: string | null;
  content?: string | null;
  uploader_id?: number;
  uploader_name?: string;
  created_at?: string;
}

// 参与人分配
export interface ScoreParticipant {
  user_id: number;
  user_name?: string;
  score: number;
}

// 评分记录
export interface AssessmentScore {
  id: number;
  assessment_id: number;
  level: ScoreLevel;
  scorer_id: number;
  scorer_name?: string;
  total_score: number;
  opinion?: string | null;
  submitted_at?: string | null;
  participants?: ScoreParticipant[];
  attachments?: AssessmentAttachment[];
}

// 补充凭证请求
export interface SupplementRequest {
  id: number;
  assessment_id: number;
  requester_id: number;
  requester_name?: string;
  by_level?: string;
  note?: string | null;
  status: 'pending' | 'completed';
  response?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  attachments?: AssessmentAttachment[];
}

// 待考核项（工作项视角）
export interface PendingAssessmentItem {
  work_item_id: number;
  title: string;
  department_id?: number | null;
  department_name?: string | null;
  district_id?: number | null;
  district_name?: string | null;
  sponsor_id?: number | null;
  sponsor_name?: string | null;
  completed_at?: string | null;
  has_email?: boolean;
  email_url?: string | null;
}

// 考核列表项
export interface AssessmentListItem {
  id: number;
  work_item_id: number;
  work_item_title?: string;
  status: AssessmentStatus;
  current_level?: ScoreLevel | null;
  department_name?: string | null;
  district_name?: string | null;
  sponsor_id?: number | null;
  sponsor_name?: string | null;
  initiator_name?: string | null;
  final_score?: number | null;
  initiated_at?: string | null;
  completed_at?: string | null;
}

// 考核详情
export interface AssessmentDetail {
  id: number;
  work_item_id: number;
  work_item_title?: string;
  work_item_content?: string | null;
  status: AssessmentStatus;
  current_level?: ScoreLevel | null;
  department_id?: number | null;
  department_name?: string | null;
  district_id?: number | null;
  district_name?: string | null;
  sponsor_id?: number | null;
  sponsor_name?: string | null;
  initiator_id?: number | null;
  initiator_name?: string | null;
  skip_dept_confirm?: boolean;
  skip_district_score?: boolean;
  skip_regulator_score?: boolean;
  final_score?: number | null;
  appeal_deadline?: string | null;
  initiated_at?: string | null;
  completed_at?: string | null;
  has_email?: boolean;
  email_url?: string | null;
  scores?: AssessmentScore[];
  supplement_requests?: SupplementRequest[];
  attachments?: AssessmentAttachment[];
  operation_logs?: AssessmentOperationLog[];
}

export interface AssessmentOperationLog {
  id: number;
  action: string;
  detail?: string | null;
  operator_name?: string;
  created_at?: string | null;
}

// 非考核项
export interface NonAssessmentItem {
  id: number;
  work_item_id: number;
  work_item_title?: string;
  department_name?: string | null;
  district_name?: string | null;
  sponsor_name?: string | null;
  remark?: string | null;
  marked_by_name?: string;
  marked_at?: string | null;
  revoked?: boolean;
}

// 跳过规则信息
export interface SkipRuleInfo {
  skip_dept_confirm: boolean;
  skip_district_score: boolean;
  skip_regulator_score: boolean;
  initial_status: string;
  reason?: string;
}

// 评分提交
export interface ScoreSubmitPayload {
  total_score: number;
  opinion?: string;
  participants?: ScoreParticipant[];
  attachments?: AssessmentAttachment[];
}
