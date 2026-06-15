import React, { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Avatar, Dropdown, Space, Typography } from 'antd';
import {
  DashboardOutlined,
  ProjectOutlined,
  UserOutlined,
  MailOutlined,
  CalendarOutlined,
  FileTextOutlined,
  HistoryOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { useAuth } from './AuthProvider';
import { ROLE_LABELS, ROLE_LEVELS } from '../types';
import type { RoleType } from '../types';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();

  const userLevel = user ? ROLE_LEVELS[user.role as RoleType] || 0 : 0;

  const menuItems: MenuProps['items'] = [
    { key: '/dashboard', icon: <DashboardOutlined />, label: '我的工作' },
    { key: '/kanban', icon: <ProjectOutlined />, label: '工作看板' },
    ...(userLevel >= 2
      ? [
          {
            key: 'admin',
            label: '后台管理',
            icon: <UserOutlined />,
            children: [
              ...(userLevel >= 2 ? [{ key: '/admin/work-items', icon: <FileTextOutlined />, label: '工作项管理' }] : []),
              ...(userLevel >= 2 ? [{ key: '/admin/status-logs', icon: <HistoryOutlined />, label: '状态变更日志' }] : []),
              ...(userLevel >= 2 ? [{ key: '/admin/email-logs', icon: <UnorderedListOutlined />, label: '邮件处理日志' }] : []),
              ...(userLevel >= 4 ? [{ key: '/admin/holidays', icon: <CalendarOutlined />, label: '节假日配置' }] : []),
              ...(userLevel >= 5 ? [{ key: '/admin/users', icon: <UserOutlined />, label: '用户管理' }] : []),
              ...(userLevel >= 5 ? [{ key: '/admin/email', icon: <MailOutlined />, label: '邮箱配置' }] : []),
            ],
          },
        ]
      : []),
  ];

  const userMenuItems: MenuProps['items'] = [
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: () => {
        logout();
        navigate('/login');
      },
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider trigger={null} collapsible collapsed={collapsed} theme="dark" width={220}>
        <div style={{ height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: collapsed ? 14 : 16, fontWeight: 600 }}>
          {collapsed ? 'GWS' : '集团工作跟进系统'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          defaultOpenKeys={['admin']}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ padding: '0 24px', background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {React.createElement(collapsed ? MenuUnfoldOutlined : MenuFoldOutlined, {
              style: { fontSize: 18, cursor: 'pointer' },
              onClick: () => setCollapsed(!collapsed),
            })}
          </div>
          <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
            <Space style={{ cursor: 'pointer' }}>
              <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#1677ff' }} />
              <div>
                <Text strong style={{ display: 'block', lineHeight: 1.2 }}>{user?.username}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>{ROLE_LABELS[user?.role as RoleType] || ''}</Text>
              </div>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 24, padding: 24, background: '#fff', borderRadius: 8, minHeight: 280 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
