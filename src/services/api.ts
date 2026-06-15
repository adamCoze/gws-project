import axios from 'axios';
import type { LoginRequest, LoginResponse, User, WorkItem, Department, EmailConfig, Holiday, StatusLog, KanbanData } from '../types';

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

// 响应拦截器 - 处理 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth API
export const authApi = {
  login: (data: LoginRequest) => api.post<LoginResponse>('/auth/login', data),
  me: () => api.get<User>('/auth/me'),
};

// Work Items API
export const workItemApi = {
  list: (params?: { department_id?: number; status?: string; assignee_email_prefix?: string }) =>
    api.get<WorkItem[]>('/work-items', { params }),
  get: (id: number) => api.get<WorkItem>(`/work-items/${id}`),
  create: (data: Partial<WorkItem>) => api.post<WorkItem>('/work-items', data),
  update: (id: number, data: Partial<WorkItem>) => api.put<WorkItem>(`/work-items/${id}`, data),
  delete: (id: number) => api.delete(`/work-items/${id}`),
  updateStatus: (id: number, status: string, remark: string) =>
    api.patch(`/work-items/${id}/status`, { status, remark }),
  myWork: () => api.get<WorkItem[]>('/work-items/my'),
};

// Kanban API
export const kanbanApi = {
  get: (params?: { department_id?: number }) =>
    api.get<KanbanData[]>('/kanban', { params }),
};

// Department API
export const departmentApi = {
  list: () => api.get<Department[]>('/departments'),
  create: (data: Partial<Department>) => api.post<Department>('/departments', data),
  update: (id: number, data: Partial<Department>) => api.put<Department>(`/departments/${id}`, data),
  delete: (id: number) => api.delete(`/departments/${id}`),
};

// User API
export const userApi = {
  list: () => api.get<User[]>('/users'),
  get: (id: number) => api.get<User>(`/users/${id}`),
  create: (data: Partial<User> & { password: string }) => api.post<User>('/users', data),
  update: (id: number, data: Partial<User>) => api.put<User>(`/users/${id}`, data),
  delete: (id: number) => api.delete(`/users/${id}`),
  resetPassword: (id: number, password: string) => api.post(`/users/${id}/reset-password`, { password }),
};

// Email Config API
export const emailConfigApi = {
  list: () => api.get<EmailConfig[]>('/email-configs'),
  create: (data: Partial<EmailConfig>) => api.post<EmailConfig>('/email-configs', data),
  update: (id: number, data: Partial<EmailConfig>) => api.put<EmailConfig>(`/email-configs/${id}`, data),
  delete: (id: number) => api.delete(`/email-configs/${id}`),
  test: (id: number) => api.post(`/email-configs/${id}/test`),
};

// Holiday API
export const holidayApi = {
  list: (year?: number) => api.get<Holiday[]>('/holidays', { params: { year } }),
  create: (data: Partial<Holiday>) => api.post<Holiday>('/holidays', data),
  update: (id: number, data: Partial<Holiday>) => api.put<Holiday>(`/holidays/${id}`, data),
  delete: (id: number) => api.delete(`/holidays/${id}`),
};

// Status Log API
export const statusLogApi = {
  list: (workItemId?: number) => api.get<StatusLog[]>('/status-logs', { params: { work_item_id: workItemId } }),
};

export default api;
