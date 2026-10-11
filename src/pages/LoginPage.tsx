import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, message, Space } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { Navigate } from 'react-router-dom';
import { authApi } from '../services/api';
import { useAuth } from '../components/AuthProvider';
import type { LoginRequest } from '../types';

const { Title, Text } = Typography;

const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const { login, isAuthenticated } = useAuth();

  // 已登录用户直接进入系统（防止 /login 循环）
  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  const onFinish = async (values: LoginRequest) => {
    setLoading(true);
    try {
      const res = await authApi.login(values);
      const { access_token, user } = res as any;
      login(access_token, user);
      // 整页跳转（而非 SPA navigate）：确保 AuthProvider 从 localStorage 重新初始化，
      // 彻底避免登录成功后路由守卫读到旧状态被踢回登录页的问题
      const raw = new URLSearchParams(window.location.search).get('redirect') || '';
      // 净化 redirect：必须以 / 开头且不能指向 /login 自身，否则会形成登录死循环
      const redirectUrl = raw.startsWith('/') && raw !== '/login' ? raw : '/dashboard';
      window.location.replace(redirectUrl);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      message.error(error.response?.data?.detail || '登录失败，请检查用户名和密码');
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
      <Card style={{ width: 400, borderRadius: 12, boxShadow: '0 8px 32px rgba(0,0,0,0.15)' }}>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div style={{ textAlign: 'center' }}>
            <Title level={3} style={{ marginBottom: 4 }}>集团工作跟进系统</Title>
            <Text type="secondary">Group Work Tracking System</Text>
          </div>
          <Form name="login" onFinish={onFinish} size="large" autoComplete="off">
            <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input prefix={<UserOutlined />} placeholder="用户名" />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="密码" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>登录</Button>
            </Form.Item>
          </Form>
        </Space>
      </Card>
    </div>
  );
};

export default LoginPage;
