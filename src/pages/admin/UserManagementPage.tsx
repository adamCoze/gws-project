import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, Switch, Space, Typography, message, Popconfirm, Tag } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, KeyOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { userApi, departmentApi } from '../../services/api';
import type { User, Department } from '../../types';
import { ROLE_LABELS } from '../../types';
import type { RoleType } from '../../types';

const { Title } = Typography;

const UserManagementPage: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [pwdModalOpen, setPwdModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [resetUserId, setResetUserId] = useState<number | null>(null);
  const [form] = Form.useForm();
  const [pwdForm] = Form.useForm();

  useEffect(() => { loadUsers(); loadDepartments(); }, []);

  const loadUsers = async () => {
    setLoading(true);
    try { const res = await userApi.list(); setUsers(res.data); } catch { message.error('加载用户失败'); }
    finally { setLoading(false); }
  };
  const loadDepartments = async () => {
    try { const res = await departmentApi.list(); setDepartments(res.data); } catch { /* ignore */ }
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      if (editingUser) {
        await userApi.update(editingUser.id, values);
        message.success('更新成功');
      } else {
        await userApi.create(values);
        message.success('创建成功');
      }
      setModalOpen(false);
      form.resetFields();
      setEditingUser(null);
      loadUsers();
    } catch { /* validation error */ }
  };

  const handleDelete = async (id: number) => {
    try { await userApi.delete(id); message.success('删除成功'); loadUsers(); } catch { message.error('删除失败'); }
  };

  const handleResetPwd = async () => {
    try {
      const values = await pwdForm.validateFields();
      if (resetUserId) {
        await userApi.resetPassword(resetUserId, values.password);
        message.success('密码重置成功');
        setPwdModalOpen(false);
        pwdForm.resetFields();
        setResetUserId(null);
      }
    } catch { /* validation error */ }
  };

  const columns: ColumnsType<User> = [
    { title: '用户名', dataIndex: 'username', key: 'username', width: 120 },
    { title: '邮箱', dataIndex: 'email', key: 'email', width: 200 },
    { title: '邮箱前缀', dataIndex: 'email_prefix', key: 'email_prefix', width: 120 },
    { title: '角色', dataIndex: 'role', key: 'role', width: 100, render: (r: string) => <Tag color="blue">{ROLE_LABELS[r as RoleType]}</Tag> },
    { title: '部门', key: 'dept', width: 120, render: (_: unknown, r: User) => r.department?.name || '-' },
    { title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80, render: (v: boolean) => v ? <Tag color="green">启用</Tag> : <Tag color="red">禁用</Tag> },
    {
      title: '操作', key: 'action', width: 200,
      render: (_: unknown, record: User) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => { setEditingUser(record); form.setFieldsValue(record); setModalOpen(true); }}>编辑</Button>
          <Button size="small" icon={<KeyOutlined />} onClick={() => { setResetUserId(record.id); setPwdModalOpen(true); }}>重置密码</Button>
          <Popconfirm title="确认删除?" onConfirm={() => handleDelete(record.id)}><Button size="small" danger icon={<DeleteOutlined />}>删除</Button></Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={4} style={{ margin: 0 }}>用户管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingUser(null); form.resetFields(); setModalOpen(true); }}>新增用户</Button>
      </div>
      <Table columns={columns} dataSource={users} rowKey="id" loading={loading} pagination={{ pageSize: 15 }} />
      <Modal title={editingUser ? '编辑用户' : '新增用户'} open={modalOpen} onOk={handleSave} onCancel={() => setModalOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}><Input /></Form.Item>
          {!editingUser && <Form.Item name="password" label="密码" rules={[{ required: true }]}><Input.Password /></Form.Item>}
          <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email' }]}><Input /></Form.Item>
          <Form.Item name="email_prefix" label="邮箱前缀" rules={[{ required: true }]}><Input placeholder="如 zhangsan" /></Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select options={Object.entries(ROLE_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
          </Form.Item>
          <Form.Item name="department_id" label="部门">
            <Select allowClear options={departments.map((d) => ({ value: d.id, label: d.name }))} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked" initialValue={true}><Switch /></Form.Item>
        </Form>
      </Modal>
      <Modal title="重置密码" open={pwdModalOpen} onOk={handleResetPwd} onCancel={() => setPwdModalOpen(false)} destroyOnClose>
        <Form form={pwdForm} layout="vertical">
          <Form.Item name="password" label="新密码" rules={[{ required: true, min: 6 }]}><Input.Password /></Form.Item>
        </Form>
      </Modal>
    </Space>
  );
};

export default UserManagementPage;
