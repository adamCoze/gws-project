import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './components/AuthProvider';
import MainLayout from './components/MainLayout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import KanbanPage from './pages/KanbanPage';
import UserManagementPage from './pages/admin/UserManagementPage';
import EmailConfigPage from './pages/admin/EmailConfigPage';
import EmailLogPage from './pages/admin/EmailLogPage';
import HolidayConfigPage from './pages/admin/HolidayConfigPage';
import WorkItemManagementPage from './pages/admin/WorkItemManagementPage';
import StatusLogPage from './pages/admin/StatusLogPage';

const ProtectedRoute: React.FC<{ children: React.ReactNode; requiredLevel?: number }> = ({
  children,
  requiredLevel = 0,
}) => {
  const { user, isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user && requiredLevel > 0) {
    const { ROLE_LEVELS } = require('./types');
    const userLevel = ROLE_LEVELS[user.role as keyof typeof ROLE_LEVELS] || 0;
    if (userLevel < requiredLevel) return <Navigate to="/dashboard" replace />;
  }
  return <>{children}</>;
};

const AppRoutes: React.FC = () => {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <LoginPage />} />
      <Route path="/" element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="kanban" element={<KanbanPage />} />
        <Route path="admin/users" element={<ProtectedRoute requiredLevel={5}><UserManagementPage /></ProtectedRoute>} />
        <Route path="admin/email" element={<ProtectedRoute requiredLevel={5}><EmailConfigPage /></ProtectedRoute>} />
        <Route path="admin/email-logs" element={<ProtectedRoute requiredLevel={2}><EmailLogPage /></ProtectedRoute>} />
        <Route path="admin/holidays" element={<ProtectedRoute requiredLevel={4}><HolidayConfigPage /></ProtectedRoute>} />
        <Route path="admin/work-items" element={<ProtectedRoute requiredLevel={2}><WorkItemManagementPage /></ProtectedRoute>} />
        <Route path="admin/status-logs" element={<ProtectedRoute requiredLevel={2}><StatusLogPage /></ProtectedRoute>} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
};

const App: React.FC = () => (
  <BrowserRouter>
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  </BrowserRouter>
);

export default App;
