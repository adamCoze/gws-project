import axios from 'axios';
import type { LoginRequest, LoginResponse, WorkItem, Department, District, User, EmailConfig, EmailLog, SystemConfig, StatusChangeLog, PendingAssessmentItem, AssessmentListItem, AssessmentDetail, AssessmentAttachment, NonAssessmentItem, SkipRuleInfo, ScoreSubmitPayload } from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

// 请求拦截器 - 添加 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截器 - 处理 401，自动解包 data
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname + window.location.search);
    }
    return Promise.reject(error);
  }
);

// Auth
export const authApi = {
  login: (data: LoginRequest) =>
    api.post<LoginResponse>('/auth/login', data),
  me: () =>
    api.get<User>('/auth/me'),
  changePassword: (data: { current_password: string; new_password: string }) =>
    api.post('/auth/change-password', data),
};

// Work Items
export const workItemApi = {
  list: async (params?: { department_id?: number; status?: string; assignee_email_prefix?: string; page_size?: number }): Promise<WorkItem[]> => {
    const res = await api.get('/work-items', { params });
    return res as unknown as WorkItem[];
  },
  get: (id: number) =>
    api.get<WorkItem>(`/work-items/${id}`),
  create: (data: Partial<WorkItem>) =>
    api.post<WorkItem>('/work-items', data),
  update: (id: number, data: Partial<WorkItem>) =>
    api.put<WorkItem>(`/work-items/${id}`, data),
  delete: (id: number) =>
    api.delete(`/work-items/${id}`),
  changeStatus: (id: number, data: { status: string; remark?: string }) =>
    api.patch(`/work-items/${id}/status`, data),
  myWork: async (emailPrefix?: string): Promise<WorkItem[]> => {
    const res = await api.get('/work-items/my', { params: emailPrefix ? { assignee_email_prefix: emailPrefix } : {} });
    return res as unknown as WorkItem[];
  },
  getEmailUrl: (id: number) =>
    api.get<{ url?: string; error?: string; search_url?: string }>(`/work-items/${id}/email-url`),
  getEmailLinkStatus: (ids: number[]) =>
    api.get<{ items: Record<number, boolean> }>(`/work-items/email-link-status`, { params: { ids: ids.join(',') } }),
};

// Status Change Logs
export const statusChangeLogApi = {
  list: (workItemId?: number) =>
    api.get<StatusChangeLog[]>('/status-change-logs', { params: { work_item_id: workItemId } }),
};

// Kanban
export const kanbanApi = {
  get: (departmentId?: number) =>
    api.get('/kanban', { params: { department_id: departmentId } }),
};

// Districts
export const districtApi = {
  list: async (): Promise<District[]> => {
    const res = await api.get('/districts');
    return res as unknown as District[];
  },
  create: (data: Partial<District>) =>
    api.post<District>('/districts', data),
  update: (id: number, data: Partial<District>) =>
    api.put<District>(`/districts/${id}`, data),
  delete: (id: number) =>
    api.delete(`/districts/${id}`),
};

// Departments
export const departmentApi = {
  list: async (): Promise<Department[]> => {
    const res = await api.get('/departments');
    return res as unknown as Department[];
  },
  create: (data: Partial<Department>) =>
    api.post<Department>('/departments', data),
  update: (id: number, data: Partial<Department>) =>
    api.put<Department>(`/departments/${id}`, data),
  delete: (id: number) =>
    api.delete(`/departments/${id}`),
};

// Users
export const userApi = {
  list: async (): Promise<User[]> => {
    const res = await api.get('/users');
    return res as unknown as User[];
  },
  listBrief: async (): Promise<Array<{id: number; real_name: string; username: string; email_prefix: string; role_level: number}>> => {
    const res = await api.get('/users/brief');
    return res as unknown as Array<{id: number; real_name: string; username: string; email_prefix: string; role_level: number}>;
  },
  create: (data: Partial<User> & { password?: string }) =>
    api.post<User>('/users', data),
  update: (id: number, data: Partial<User> & { password?: string }) =>
    api.put<User>(`/users/${id}`, data),
  delete: (id: number) =>
    api.delete(`/users/${id}`),
};

// Email Config
export const emailConfigApi = {
  list: (params?: { limit?: number; offset?: number; process_result?: string }) =>
    api.get<EmailConfig[]>('/email-configs'),
  create: (data: Partial<EmailConfig> & { password?: string }) =>
    api.post<EmailConfig>('/email-configs', data),
  update: (id: number, data: Partial<EmailConfig> & { password?: string }) =>
    api.put<EmailConfig>(`/email-configs/${id}`, data),
  delete: (id: number) =>
    api.delete(`/email-configs/${id}`),
};

// Email Logs
export const emailLogApi = {
  list: (params?: { limit?: number; offset?: number; process_result?: string }) =>
    api.get<EmailLog[]>('/email-logs', { params }),
};


// System Config
export const systemConfigApi = {
  get: (key: string) =>
    api.get<SystemConfig>(`/system-config/${key}`),
  set: (key: string, value: string) =>
    api.put<SystemConfig>(`/system-config/${key}`, { config_value: value }),
};

// ============ 考核模块（需求v0.3完整版） ============
export const assessmentApi = {
  // 待考核项清单
  pendingItems: async (params?: { page?: number; page_size?: number; keyword?: string; department_id?: number; district_id?: number; month?: string }): Promise<{ items: PendingAssessmentItem[]; total: number }> => {
    const res = await api.get('/assessment/pending-items', { params });
    return res as unknown as { items: PendingAssessmentItem[]; total: number };
  },
  // 跳过规则查询
  checkSkipRule: async (workItemId: number): Promise<SkipRuleInfo> => {
    const res = await api.get(`/assessment/check-skip-rule/${workItemId}`);
    return res as unknown as SkipRuleInfo;
  },
  // 发起考核
  initiate: async (workItemId: number): Promise<{ assessment_id: number; status: string; status_text: string; message: string }> => {
    const res = await api.post(`/assessment/initiate/${workItemId}`);
    return res as unknown as { assessment_id: number; status: string; status_text: string; message: string };
  },
  // 非考核项
  markNonAssessment: (workItemId: number, remark?: string) =>
    api.post(`/assessment/non-assessment/${workItemId}`, remark ? { remark } : undefined),
  revokeNonAssessment: (workItemId: number) =>
    api.delete(`/assessment/non-assessment/${workItemId}`),
  nonAssessmentList: async (params?: { page?: number; page_size?: number; keyword?: string; department_id?: number; district_id?: number; month?: string }): Promise<{ items: NonAssessmentItem[]; total: number }> => {
    const res = await api.get('/assessment/non-assessment', { params });
    return res as unknown as { items: NonAssessmentItem[]; total: number };
  },
  // 部门总监确认
  toConfirm: async (params?: { page?: number; page_size?: number }): Promise<{ items: AssessmentListItem[]; total: number }> => {
    const res = await api.get('/assessment/to-confirm', { params });
    return res as unknown as { items: AssessmentListItem[]; total: number };
  },
  deptConfirm: (id: number) =>
    api.post(`/assessment/${id}/dept-confirm`),
  deptReject: (id: number, reason?: string) =>
    api.post(`/assessment/${id}/dept-reject`, null, { params: reason ? { reason } : {} }),
  // 评分
  toScore: async (params?: { page?: number; page_size?: number }): Promise<{ items: AssessmentListItem[]; total: number }> => {
    const res = await api.get('/assessment/to-score', { params });
    return res as unknown as { items: AssessmentListItem[]; total: number };
  },
  submitScore: (id: number, data: ScoreSubmitPayload) =>
    api.post(`/assessment/${id}/score`, data),
  // 补充凭证
  requestSupplement: (id: number, note: string) =>
    api.post(`/assessment/${id}/supplement-request`, { note }),
  submitSupplement: (id: number, data: { supplement_request_id: number; response?: string; attachments?: AssessmentAttachment[] }) =>
    api.post(`/assessment/${id}/supplement-submit`, data),
  // 详情
  detail: async (id: number): Promise<AssessmentDetail> => {
    const res = await api.get(`/assessment/${id}`);
    return res as unknown as AssessmentDetail;
  },
  // 我的考核
  myAssessments: async (params?: { page?: number; page_size?: number; status?: string; month?: string; keyword?: string }): Promise<{ items: AssessmentListItem[]; total: number }> => {
    const res = await api.get('/assessment/my-assessments', { params });
    return res as unknown as { items: AssessmentListItem[]; total: number };
  },
  // 上传凭证图片
  uploadAttachment: async (assessmentId: number, type: 'scoring' | 'supplement' | 'appeal', file: File): Promise<{ file_type: string; file_name: string; file_path: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await api.post(`/assessment/upload-attachment?assessment_id=${assessmentId}&type=${type}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res as unknown as { file_type: string; file_name: string; file_path: string };
  },
};
