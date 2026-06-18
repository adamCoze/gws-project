import React, { useState, useEffect, useMemo } from 'react';
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm, Tooltip } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, SwapOutlined } from '@ant-design/icons';
import { workItemApi, departmentApi, userApi } from '../../services/api';
import { useAuth } from '../../components/AuthProvider';
import type { WorkItem, Department, WorkItemStatus as WorkItemStatusType, RoleType } from '../../types';
import { STATUS_LABELS, STATUS_COLORS, ROLE_LEVELS } from '../../types';

const { TextArea } = Input;

// 人事/商务部ID
const HR_COMMERCE_DEPT_ID = 1;

interface UserBrief {
  id: number;
  real_name: string;
  username: string;
  email_prefix: string;
}

function canChangeStatus(role: string, departmentId?: number | null): boolean {
  const roleLevel = ROLE_LEVELS[role as RoleType] || 0;
  // 规管(4)、总裁(5)、管理员(6)始终可以
  if (roleLevel >= 4) return true;
  // 人事/商务部 经理(2)和专员(1)可以
  if (departmentId === HR_COMMERCE_DEPT_ID && roleLevel >= 1 && roleLevel <= 2) return true;
  return false;
}

const WorkItemManagementPage: React.FC = () => {
  const [items, setItems] = useState<WorkItem[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [users, setUsers] = useState<UserBrief[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [statusModal, setStatusModal] = useState<{ visible: boolean; item?: WorkItem }>({ visible: false });
  const [editingItem, setEditingItem] = useState<WorkItem | null>(null);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [newStatus, setNewStatus] = useState<WorkItemStatusType>('pending');
  const [remark, setRemark] = useState('');
  const { user } = useAuth();

  const canDelete = useMemo(() => {
    if (!user) return false;
    const level = ROLE_LEVELS[user.role as RoleType] || 0;
    return level >= 5; // admin(6) and president(5)
  }, [user]);

  const canChange = useMemo(() => {
    if (!user) return false;
    return canChangeStatus(user.role, user.department_id);
  }, [user]);

  const fetchData = async () => {
    setLoading(true);

    // Fetch work items (core data) - independent request
    try {
      const itemsData = await workItemApi.list({ page_size: 100 });
      setItems(itemsData);
    } catch (e) {
      console.error('Failed to fetch work items:', e);
      message.error('获取工作项失败');
    }

    // Fetch departments - independent request, non-critical
    try {
      const deptsData = await departmentApi.list();
      setDepartments(deptsData);
    } catch (e) {
      console.error('Failed to fetch departments:', e);
    }

    // Fetch users brief list (low permission, works for all roles) - independent request
    try {
      const usersData = await userApi.listBrief();
      setUsers(usersData);
    } catch (e) {
      console.error('Failed to fetch users:', e);
    }

    setLoading(false);
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Resolve assignee IDs from work item's assignee_email_prefix or assignee_id
  const resolveAssigneeIds = (item: WorkItem): number[] => {
    if (item.assignee_email_prefix) {
      const prefixes = item.assignee_email_prefix.replace(/ /g, ',').split(',').map(s => s.trim()).filter(Boolean);
      return prefixes
        .map(prefix => users.find(u => u.email_prefix === prefix)?.id)
        .filter((id): id is number => id !== undefined);
    }
    if (item.assignee_id) {
      return [item.assignee_id];
    }
    return [];
  };

  const openModal = (item?: WorkItem) => {
    if (item) {
      setEditingItem(item);
      const assigneeIds = resolveAssigneeIds(item);
      form.setFieldsValue({
        title: item.title,
        content: item.content,
        item_type: item.item_type,
        status: item.status,
        department_id: item.department_id,
        assignee_ids: assigneeIds,
        due_date: item.due_date ? item.due_date.slice(0, 16) : undefined,
        is_confidential: item.is_confidential,
      });
    } else {
      setEditingItem(null);
      form.resetFields();
    }
    setModalVisible(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      // Convert assignee_ids to assignee_email_prefix and assignee_id
      const assigneeIds: number[] = values.assignee_ids || [];
      const selectedUsers = assigneeIds
        .map((id: number) => users.find(u => u.id === id))
        .filter((u): u is UserBrief => u !== undefined);

      const submitData: Record<string, unknown> = {
        title: values.title,
        content: values.content,
        item_type: values.item_type,
        status: values.status,
        department_id: values.department_id,
        due_date: values.due_date,
        is_confidential: values.is_confidential,
        assignee_email_prefix: selectedUsers.length > 0 ? selectedUsers.map(u => u.email_prefix).join(',') : null,
        assignee_id: selectedUsers.length > 0 ? selectedUsers[0].id : null,
      };

      if (editingItem) {
        await workItemApi.update(editingItem.id, submitData);
        message.success('工作项已更新');
      } else {
        await workItemApi.create(submitData);
        message.success('工作项已创建');
      }

      setModalVisible(false);
      fetchData();
    } catch {
      message.error('操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await workItemApi.delete(id);
      message.success('已删除');
      fetchData();
    } catch {
      message.error('删除失败');
    }
  };

  const openStatusModal = (item: WorkItem) => {
    setStatusModal({ visible: true, item });
    setNewStatus(item.status);
    setRemark('');
  };

  const handleStatusChange = async () => {
    if (!statusModal.item) return;
    setSubmitting(true);
    try {
      await workItemApi.changeStatus(statusModal.item.id, {
        status: newStatus,
        remark: remark || undefined,
      });
      message.success('状态已更新');
      setStatusModal({ visible: false });
      fetchData();
    } catch {
      message.error('状态更新失败');
    } finally {
      setSubmitting(false);
    }
  };

  const getAssigneeName = (item: WorkItem): string => {
    if (item.assignee_names) return item.assignee_names;
    if (item.assignee?.real_name) return item.assignee.real_name;
    return '未分配';
  };

  const statusOptions = Object.entries(STATUS_LABELS).filter(([k]) => k !== 'overdue').map(([k, v]) => ({ value: k, label: v }));

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    {
      title: '标题', dataIndex: 'title', key: 'title', width: 250, ellipsis: true,
      render: (text: string) => <Tooltip title={text}><span>{text}</span></Tooltip>,
    },
    {
      title: '类型', dataIndex: 'item_type', key: 'item_type', width: 80,
      render: (type: string) => <Tag color={type === 'cosign' ? 'purple' : 'blue'}>{type === 'cosign' ? '会签' : '任务'}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (status: string) => <Tag color={STATUS_COLORS[status]}>{STATUS_LABELS[status]}</Tag>,
    },
    {
      title: '部门', key: 'department_id', width: 120,
      render: (_: unknown, record: WorkItem) => record.department?.name || '-',
    },
    {
      title: '负责人', key: 'assignee', width: 120,
      render: (_: unknown, record: WorkItem) => getAssigneeName(record),
    },
    {
      title: '截止日期', dataIndex: 'due_date', key: 'due_date', width: 120,
      render: (v: string) => v ? new Date(v).toLocaleDateString() : '-',
    },
    {
      title: '操作', key: 'action', width: 250,
      render: (_: unknown, record: WorkItem) => (
        <Space>
          {canChange && (
            <Button size="small" icon={<SwapOutlined />} onClick={() => openStatusModal(record)}>变更状态</Button>
          )}
          <Button size="small" icon={<EditOutlined />} onClick={() => openModal(record)}>编辑</Button>
          {canDelete && (
            <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
              <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2>工作项管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>新建工作项</Button>
      </div>

      <Table columns={columns} dataSource={items} rowKey="id" loading={loading} pagination={{ pageSize: 20 }} scroll={{ x: 1100 }} />

      <Modal
        title={editingItem ? '编辑工作项' : '新建工作项'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        confirmLoading={submitting}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="content" label="内容"><TextArea rows={4} /></Form.Item>
          <Form.Item name="item_type" label="类型" initialValue="task">
            <Select options={[{ value: 'task', label: '任务' }, { value: 'cosign', label: '会签' }]} />
          </Form.Item>
          <Form.Item name="status" label="状态" initialValue="pending">
            <Select options={statusOptions} disabled={!!editingItem && !canChange} />
          </Form.Item>
          <Form.Item name="department_id" label="部门">
            <Select allowClear options={departments.map((d) => ({ value: d.id, label: d.name }))} />
          </Form.Item>
          <Form.Item name="assignee_ids" label="负责人">
            <Select
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="选择一个或多个负责人"
              options={users.map((u) => ({ value: u.id, label: u.real_name || u.username }))}
            />
          </Form.Item>
          <Form.Item name="due_date" label="截止日期"><Input type="datetime-local" /></Form.Item>
          <Form.Item name="is_confidential" label="是否机密" initialValue={false}>
            <Select options={[{ value: false, label: '否' }, { value: true, label: '是' }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`变更状态 - ${statusModal.item?.title}`}
        open={statusModal.visible}
        onOk={handleStatusChange}
        onCancel={() => setStatusModal({ visible: false })}
        confirmLoading={submitting}
      >
        <Form layout="vertical">
          <Form.Item label="新状态">
            <Select value={newStatus} onChange={setNewStatus} options={statusOptions} />
          </Form.Item>
          <Form.Item label="备注">
            <TextArea value={remark} onChange={(e) => setRemark(e.target.value)} placeholder="可选：填写状态变更原因" rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default WorkItemManagementPage;
