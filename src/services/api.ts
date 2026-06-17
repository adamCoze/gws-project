import axios from 'axios';
import type { LoginRequest, LoginResponse, WorkItem, Department, User, EmailConfig, EmailLog, Holiday, SystemConfig, StatusChangeLog } from '../types';

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
      window.location.href = '/login';
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
  listBrief: async (): Promise<Array<{id: number; real_name: string; username: string; email_prefix: string}>> => {
    const res = await api.get('/users/brief');
    return res as unknown as Array<{id: number; real_name: string; username: string; email_prefix: string}>;
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
  list: () =>
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
  list: () =>
    api.get<EmailLog[]>('/email-logs'),
};

// Holidays
export const holidayApi = {
  list: (year?: number) =>
    api.get<Holiday[]>('/holidays', { params: { year } }),
  create: (data: Partial<Holiday>) =>
    api.post<Holiday>('/holidays', data),
  update: (id: number, data: Partial<Holiday>) =>
    api.put<Holiday>(`/holidays/${id}`, data),
  delete: (id: number) =>
    api.delete(`/holidays/${id}`),
};

// System Config
export const systemConfigApi = {
  get: (key: string) =>
    api.get<SystemConfig>(`/system-config/${key}`),
  set: (key: string, value: string) =>
    api.put<SystemConfig>(`/system-config/${key}`, { config_value: value }),
};
