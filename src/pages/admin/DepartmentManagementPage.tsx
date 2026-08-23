import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, ApartmentOutlined } from '@ant-design/icons';
import { departmentApi, districtApi } from '../../services/api';
import type { Department, District } from '../../types';

const DepartmentManagementPage: React.FC = () => {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [districts, setDistricts] = useState<District[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingDept, setEditingDept] = useState<Department | null>(null);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [deptsData, districtsData] = await Promise.all([
        departmentApi.list(),
        districtApi.list(),
      ]);
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

  const openModal = (dept?: Department) => {
    if (dept) {
      setEditingDept(dept);
      form.setFieldsValue(dept);
    } else {
      setEditingDept(null);
      form.resetFields();
    }
    setModalVisible(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      if (editingDept) {
        await departmentApi.update(editingDept.id, values);
        message.success('部门已更新');
      } else {
        await departmentApi.create(values);
        message.success('部门已创建');
      }

      setModalVisible(false);
      fetchData();
    } catch (err: any) {
      if (err.response?.data?.detail) {
        message.error(err.response.data.detail);
      } else {
        message.error('操作失败');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await departmentApi.delete(id);
      message.success('部门已删除');
      fetchData();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '删除失败');
    }
  };

  const getDistrictName = (districtId?: number) => {
    if (!districtId) return '-';
    const district = districts.find((d) => d.id === districtId);
    return district?.name || '-';
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: '部门名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => (
        <Space>
          <ApartmentOutlined style={{ color: '#1677ff' }} />
          {name}
        </Space>
      ),
    },
    {
      title: '部门编码',
      dataIndex: 'code',
      key: 'code',
      width: 120,
    },
    {
      title: '所属区域',
      dataIndex: 'district_id',
      key: 'district_id',
      render: (districtId: number) => getDistrictName(districtId),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      render: (_: any, record: Department) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openModal(record)}>
            编辑
          </Button>
          <Popconfirm title="确认删除该部门？" onConfirm={() => handleDelete(record.id)}>
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
        <h2>部门管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>
          新建部门
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={departments}
        rowKey="id"
        loading={loading}
        pagination={{ showTotal: (t) => `共 ${t} 条`, showSizeChanger: true, pageSizeOptions: [20, 50, 100], defaultPageSize: 20 }}
      />

      <Modal
        title={editingDept ? '编辑部门' : '新建部门'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        confirmLoading={submitting}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="部门名称" rules={[{ required: true, message: '请输入部门名称' }]}>
            <Input placeholder="如 人事/商务部" />
          </Form.Item>
          <Form.Item name="code" label="部门编码" rules={[{ required: true, message: '请输入部门编码' }]}>
            <Input placeholder="如 RS" maxLength={20} />
          </Form.Item>
          <Form.Item name="district_id" label="所属区域">
            <Select
              allowClear
              placeholder="选择所属区域"
              options={districts.map((d) => ({ value: d.id, label: d.name }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default DepartmentManagementPage;
