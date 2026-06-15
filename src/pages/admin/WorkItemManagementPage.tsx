import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, DatePicker, Switch, Space, Typography, message, Popconfirm, Tag } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { workItemApi, departmentApi } from '../../services/api';
import type { WorkItem, Department } from '../../types';
import { STATUS_LABELS, STATUS_COLORS } from '../../types';
import type { WorkItemStatus, WorkItemType } from '../../types';
import dayjs from 'dayjs';

const { Title } = Typography;
const { TextArea } = Input;

const WorkItemManagementPage: React.FC = () => {
  const [items, setItems] = useState<WorkItem[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<WorkItem | null>(null);
  const [filterDept, setFilterDept] = useState<number | undefined>(undefined);
  const [filterStatus, setFilterStatus] = useState<string | undefined>(undefined);
  const [form] = Form.useForm();

  useEffect(() => { loadDepartments(); }, []);
  useEffect(() => { loadItems(); }, [filterDept, filterStatus]);

  const loadItems = async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {};
      if (filterDept) params.department_id = filterDept;
      if (filterStatus) params.status = filterStatus;
      const res = await workItemApi.list(params as { department_id?: number; status?: string });
      setItems(res.data);
    } catch { message.error('加载工作项失败'); }
    finally { setLoading(false); }
  };

  const loadDepartments = async () => {
    try { const res = await departmentApi.list(); setDepartments(res.data); } catch { /* ignore */ }
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      const data = { ...values, due_date: values.due_date?.format('YYYY-MM-DD') || null };
      if (editing) { await workItemApi.update(editing.id, data); message.success('更新成功'); }
      else { await workItemApi.create(data); message.success('创建成功'); }
      setModalOpen(false); form.resetFields(); setEditing(null); loadItems();
    } catch { /* validation */ }
  };

  const handleDelete = async (id: number) => {
    try { await workItemApi.delete(id); message.success('删除成功'); loadItems(); } catch { message.error('删除失败'); }
  };

  const columns: ColumnsType<WorkItem> = [
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true, width: 200 },
    { title: '类型', dataIndex: 'item_type', key: 'item_type', width: 80, render: (t: string) => <Tag color={t === 'task' ? 'blue' : 'purple'}>{t === 'task' ? '任务' : '会签'}</Tag> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={STATUS_COLORS[s as WorkItemStatus]}>{STATUS_LABELS[s as WorkItemStatus]}</Tag> },
    { title: '部门', key: 'dept', width: 100, render: (_: unknown, r: WorkItem) => r.department?.name || '-' },
    { title: '责任人', dataIndex: 'assignee_email_prefix', key: 'assignee', width: 100 },
    { title: '截止日期', dataIndex: 'due_date', key: 'due_date', width: 110, render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD') : '-' },
    { title: '机密', dataIndex: 'is_confidential', key: 'conf', width: 70, render: (v: boolean) => v ? <Tag color="red">是</Tag> : <Tag>否</Tag> },
    {
      title: '操作', key: 'action', width: 150,
      render: (_: unknown, record: WorkItem) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => { setEditing(record); form.setFieldsValue({ ...record, due_date: record.due_date ? dayjs(record.due_date) : null }); setModalOpen(true); }}>编辑</Button>
          <Popconfirm title="确认删除?" onConfirm={() => handleDelete(record.id)}><Button size="small" danger icon={<DeleteOutlined />}>删除</Button></Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={4} style={{ margin: 0 }}>工作项管理</Title>
        <Space>
          <Select placeholder="筛选部门" allowClear style={{ width: 150 }} value={filterDept} onChange={setFilterDept} options={departments.map((d) => ({ value: d.id, label: d.name }))} />
          <Select placeholder="筛选状态" allowClear style={{ width: 120 }} value={filterStatus} onChange={setFilterStatus} options={Object.entries(STATUS_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true); }}>新增工作项</Button>
        </Space>
      </div>
      <Table columns={columns} dataSource={items} rowKey="id" loading={loading} pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 条` }} />
      <Modal title={editing ? '编辑工作项' : '新增工作项'} open={modalOpen} onOk={handleSave} onCancel={() => setModalOpen(false)} destroyOnClose width={600}>
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="content" label="内容" rules={[{ required: true }]}><TextArea rows={3} /></Form.Item>
          <Space size="large" style={{ width: '100%' }}>
            <Form.Item name="item_type" label="类型" rules={[{ required: true }]} initialValue="task">
              <Select style={{ width: 120 }} options={[{ value: 'task', label: '任务' }, { value: 'cosign', label: '会签' }]} />
            </Form.Item>
            <Form.Item name="status" label="状态" rules={[{ required: true }]} initialValue="pending">
              <Select style={{ width: 120 }} options={Object.entries(STATUS_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
            </Form.Item>
            <Form.Item name="department_id" label="部门" rules={[{ required: true }]}>
              <Select style={{ width: 150 }} options={departments.map((d) => ({ value: d.id, label: d.name }))} />
            </Form.Item>
          </Space>
          <Space size="large" style={{ width: '100%' }}>
            <Form.Item name="assignee_email_prefix" label="责任人邮箱前缀"><Input placeholder="如 zhangsan" /></Form.Item>
            <Form.Item name="due_date" label="截止日期"><DatePicker /></Form.Item>
            <Form.Item name="is_confidential" label="机密" valuePropName="checked" initialValue={false}><Switch /></Form.Item>
          </Space>
        </Form>
      </Modal>
    </Space>
  );
};

export default WorkItemManagementPage;
