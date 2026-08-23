import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './components/AuthProvider';
import MainLayout from './components/MainLayout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import KanbanPage from './pages/KanbanPage';
import UserManagementPage from './pages/admin/UserManagementPage';
import DepartmentManagementPage from './pages/admin/DepartmentManagementPage';
import DistrictManagementPage from './pages/admin/DistrictManagementPage';
import EmailConfigPage from './pages/admin/EmailConfigPage';
import EmailLogPage from './pages/admin/EmailLogPage';
import WorkItemManagementPage from './pages/admin/WorkItemManagementPage';
import StatusLogPage from './pages/admin/StatusLogPage';
import { ROLE_LEVELS } from './types';
import type { RoleType } from './types';
import { ROLE_LEVEL } from './types';

const ProtectedRoute: React.FC<{ children: React.ReactNode; minLevel?: number }> = ({ children, minLevel = 1 }) => {
  const { isAuthenticated, user, isLoading } = useAuth();

  if (isLoading) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>加载中...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to={"/login?redirect=" + encodeURIComponent(window.location.pathname + window.location.search)} replace />;
  }

  if (user && minLevel > 1) {
    // 优先使用 role_level 字段
    const userLevel = user.role_level || ROLE_LEVELS[user.role as RoleType] || 0;
    if (userLevel < minLevel) {
      return <Navigate to="/dashboard" replace />;
    }
  }

  return <>{children}</>;
};

const AppRoutes: React.FC = () => {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <MainLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="kanban" element={<KanbanPage />} />
        <Route
          path="admin/users"
          element={
            <ProtectedRoute minLevel={ROLE_LEVEL.ADMIN}>
              <UserManagementPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="admin/departments"
          element={
            <ProtectedRoute minLevel={ROLE_LEVEL.ADMIN}>
              <DepartmentManagementPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="admin/districts"
          element={
            <ProtectedRoute minLevel={ROLE_LEVEL.ADMIN}>
              <DistrictManagementPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="admin/email"
          element={
            <ProtectedRoute minLevel={ROLE_LEVEL.ADMIN}>
              <EmailConfigPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="admin/email-logs"
          element={
            <ProtectedRoute minLevel={ROLE_LEVEL.MANAGER}>
              <EmailLogPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="admin/work-items"
          element={
            <ProtectedRoute minLevel={ROLE_LEVEL.MANAGER}>
              <WorkItemManagementPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="admin/status-logs"
          element={
            <ProtectedRoute minLevel={ROLE_LEVEL.MANAGER}>
              <StatusLogPage />
            </ProtectedRoute>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
};

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
