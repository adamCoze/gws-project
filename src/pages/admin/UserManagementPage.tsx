import React, { useState, useEffect, useMemo } from 'react';
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { userApi, departmentApi, districtApi } from '../../services/api';
import type { User, Department, District } from '../../types';
import { ROLE_LABELS, ROLE_LEVEL_LABELS, ROLE_LEVEL_OPTIONS, ROLE_LEVEL } from '../../types';

const UserManagementPage: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [districts, setDistricts] = useState<District[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  // 监听主角色变化
  const selectedRoleLevel = Form.useWatch('role_level', form);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [usersData, deptsData, districtsData] = await Promise.all([
        userApi.list(),
        departmentApi.list(),
        districtApi.list(),
      ]);
      setUsers(usersData);
      setDepartments(deptsData);
      setDistricts(districtsData);
    } catch {
      message.error('获取数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // 根据主角色等级判断字段显示与必填
  const roleFieldConfig = useMemo(() => {
    const level = selectedRoleLevel ?? 2;
    if (level >= ROLE_LEVEL.REGULATOR) {
      // admin/president/group_director/regulator：隐藏部门、区域
      return { showDept: false, showDistrict: false, deptRequired: false, districtRequired: false };
    }
    if (level === ROLE_LEVEL.DEPT_DIRECTOR) {
      // 部门总监：显示部门（必填），隐藏区域
      return { showDept: true, showDistrict: false, deptRequired: true, districtRequired: false };
    }
    if (level === ROLE_LEVEL.DISTRICT_MANAGER) {
      // 区域总监：显示区域（必填），隐藏部门
      return { showDept: false, showDistrict: true, deptRequired: false, districtRequired: true };
    }
    // manager/staff/consultant：显示部门（必填），区域随部门带出
    return { showDept: true, showDistrict: true, deptRequired: true, districtRequired: false };
  }, [selectedRoleLevel]);

  // 副角色选项：排除主角色
  const secondaryRoleOptions = useMemo(() => {
    const mainLevel = selectedRoleLevel ?? 2;
    return ROLE_LEVEL_OPTIONS.filter((opt) => opt.value !== mainLevel);
  }, [selectedRoleLevel]);

  // 部门变化时自动带出区域
  const handleDeptChange = (deptId: number | undefined) => {
    if (!deptId) return;
    const dept = departments.find((d) => d.id === deptId);
    if (dept?.district_id) {
      form.setFieldsValue({ district_id: dept.district_id });
    }
  };

  const openModal = (user?: User) => {
    if (user) {
      setEditingUser(user);
      form.setFieldsValue({
        ...user,
        secondary_roles: user.secondary_roles || [],
        password: '',
      });
    } else {
      setEditingUser(null);
      form.resetFields();
      form.setFieldsValue({
        role_level: 2,
        role: 'staff',
        secondary_roles: [],
        is_active: true,
      });
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

  const getDistrictName = (districtId?: number) => {
    if (!districtId) return '-';
    const district = districts.find((d) => d.id === districtId);
    return district?.name || '-';
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
      title: '角色',
      dataIndex: 'role_level',
      key: 'role_level',
      render: (level: number, record: User) => (
        <Space direction="vertical" size={2}>
          <Tag color={level >= 8 ? 'red' : level >= 6 ? 'orange' : 'blue'}>
            {ROLE_LEVEL_LABELS[level] || level}
          </Tag>
          {record.secondary_roles && record.secondary_roles.length > 0 && (
            <Space wrap size={4}>
              {record.secondary_roles.map((sl) => (
                <Tag key={sl} color="default" style={{ fontSize: 12 }}>
                  副: {ROLE_LEVEL_LABELS[sl]}
                </Tag>
              ))}
            </Space>
          )}
        </Space>
      ),
    },
    {
      title: '角色(旧)',
      dataIndex: 'role',
      key: 'role',
      render: (role: string) => (
        <Tag color="default">
          {ROLE_LABELS[role] || role}
        </Tag>
      ),
    },
    {
      title: '区域',
      dataIndex: 'district_id',
      key: 'district_id',
      render: (districtId: number) => getDistrictName(districtId),
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
        pagination={{ showTotal: (t) => `共 ${t} 条`, showSizeChanger: true, pageSizeOptions: [20, 50, 100], defaultPageSize: 20 }}
      />

      <Modal
        title={editingUser ? '编辑用户' : '新建用户'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        confirmLoading={submitting}
        width={600}
        destroyOnClose
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
          <Form.Item name="role_level" label="主角色等级" initialValue={2} rules={[{ required: true }]}>
            <Select options={ROLE_LEVEL_OPTIONS} />
          </Form.Item>
          <Form.Item name="secondary_roles" label="副角色（可多选）">
            <Select
              mode="multiple"
              placeholder="选择副角色（主角色不会出现在此处）"
              options={secondaryRoleOptions}
              allowClear
            />
          </Form.Item>
          <Form.Item name="role" label="角色标识（兼容旧字段）" initialValue="staff">
            <Select
              options={[
                { value: 'consultant', label: '顾问' },
                { value: 'staff', label: '专员' },
                { value: 'manager', label: '经理' },
                { value: 'district_manager', label: '区域总监' },
                { value: 'regulator', label: '监察主任' },
                { value: 'president', label: '总裁' },
                { value: 'admin', label: '管理员' },
              ]}
            />
          </Form.Item>
          {roleFieldConfig.showDistrict && (
            <Form.Item
              name="district_id"
              label="所属区域"
              rules={roleFieldConfig.districtRequired ? [{ required: true, message: '请选择区域' }] : []}
            >
              <Select
                allowClear
                options={districts.map((d) => ({ value: d.id, label: d.name }))}
              />
            </Form.Item>
          )}
          {roleFieldConfig.showDept && (
            <Form.Item
              name="department_id"
              label="部门"
              rules={roleFieldConfig.deptRequired ? [{ required: true, message: '请选择部门' }] : []}
            >
              <Select
                allowClear
                options={departments.map((d) => ({ value: d.id, label: d.name }))}
                onChange={handleDeptChange}
              />
            </Form.Item>
          )}
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
