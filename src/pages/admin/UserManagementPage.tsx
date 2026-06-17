import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { userApi, departmentApi } from '../../services/api';
import type { User, Department } from '../../types';

const UserManagementPage: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [usersData, deptsData] = await Promise.all([
        userApi.list(),
        departmentApi.list(),
      ]);
      setUsers(usersData);
      setDepartments(deptsData);
    } catch {
      message.error('获取数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const openModal = (user?: User) => {
    if (user) {
      setEditingUser(user);
      form.setFieldsValue({
        ...user,
        password: '',
      });
    } else {
      setEditingUser(null);
      form.resetFields();
    }
    setModalVisible(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      if (editingUser) {
        const updateData = { ...values };
        if (!updateData.password) delete updateData.password;
        await userApi.update(editingUser.id, updateData);
        message.success('用户已更新');
      } else {
        await userApi.create(values);
        message.success('用户已创建');
      }

      setModalVisible(false);
      fetchData();
    } catch (err: any) {
      if (err.response?.data?.detail) {
        message.error(err.response.data.detail);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await userApi.delete(id);
      message.success('用户已删除');
      fetchData();
    } catch {
      message.error('删除失败');
    }
  };

  const getDeptName = (deptId?: number) => {
    if (!deptId) return '-';
    const dept = departments.find((d) => d.id === deptId);
    return dept?.name || '-';
  };

  const columns = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
    },
    {
      title: '姓名',
      dataIndex: 'real_name',
      key: 'real_name',
      render: (v: string) => v || '-',
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
    },
    {
      title: '邮箱前缀',
      dataIndex: 'email_prefix',
      key: 'email_prefix',
      render: (v: string) => v || '-',
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role: string) => (
        <Tag color={role === 'admin' ? 'red' : 'blue'}>
          {role === 'admin' ? '管理员' : '普通用户'}
        </Tag>
      ),
    },
    {
      title: '部门',
      dataIndex: 'department_id',
      key: 'department_id',
      render: (deptId: number) => getDeptName(deptId),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (active: boolean) => (
        <Tag color={active ? 'green' : 'default'}>
          {active ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: User) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openModal(record)}>
            编辑
          </Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2>用户管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>
          新建用户
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={users}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20 }}
      />

      <Modal
        title={editingUser ? '编辑用户' : '新建用户'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        confirmLoading={submitting}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="real_name" label="姓名">
            <Input placeholder="真实姓名，用于看板显示" />
          </Form.Item>
          <Form.Item name="email" label="邮箱">
            <Input />
          </Form.Item>
          <Form.Item name="email_prefix" label="邮箱前缀">
            <Input placeholder="如 zhangsan" />
          </Form.Item>
          <Form.Item
            name="password"
            label={editingUser ? '新密码（留空不修改）' : '密码'}
            rules={editingUser ? [] : [{ required: true }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item name="role" label="角色" initialValue="staff">
            <Select
              options={[
                { value: 'staff', label: '普通用户' },
                { value: 'admin', label: '管理员' },
              ]}
            />
          </Form.Item>
          <Form.Item name="department_id" label="部门">
            <Select
              allowClear
              options={departments.map((d) => ({ value: d.id, label: d.name }))}
            />
          </Form.Item>
          {editingUser && (
            <Form.Item name="is_active" label="状态" initialValue={true}>
              <Select
                options={[
                  { value: true, label: '启用' },
                  { value: false, label: '禁用' },
                ]}
              />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default UserManagementPage;
