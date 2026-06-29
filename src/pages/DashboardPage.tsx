import React, { useEffect, useState, useMemo } from 'react';
import { Table, Tag, Card, Typography, Space, Statistic, Row, Col, Spin, message, notification, Collapse, Button, Tooltip, Modal, Form, Input, Select } from 'antd';
import { CheckCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined, StopOutlined, SyncOutlined, LinkOutlined, LoadingOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { workItemApi, departmentApi, userApi } from '../services/api';
import { useAuth } from '../components/AuthProvider';
import type { WorkItem, Department, WorkItemStatus as WorkItemStatusType, RoleType } from '../types';
import { STATUS_LABELS, STATUS_COLORS, ROLE_LEVELS, TYPE_LABELS, TYPE_COLORS } from '../types';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
dayjs.extend(utc);
import { formatUTCDate } from '../utils/date';

const { Title } = Typography;
const { TextArea } = Input;

const DEPT_COLORS = ['#1890ff', '#52c41a', '#faad14', '#722ed1'];
const HR_COMMERCE_DEPT_ID = 1;

interface UserBrief {
  id: number;
  real_name: string;
  username: string;
  email_prefix: string;
}

function canChangeStatus(role: string, departmentId?: number | null): boolean {
  const roleLevel = ROLE_LEVELS[role as RoleType] || 0;
  if (roleLevel >= 4) return true;
  if (departmentId === HR_COMMERCE_DEPT_ID && roleLevel >= 1 && roleLevel <= 2) return true;
  return false;
}

const DashboardPage: React.FC = () => {
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [users, setUsers] = useState<UserBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [emailLoadingId, setEmailLoadingId] = useState<number | null>(null);
  const [emailLinkStatus, setEmailLinkStatus] = useState<Record<number, boolean>>({});

  // Edit modal state
  const [modalVisible, setModalVisible] = useState(false);
  const [editingItem, setEditingItem] = useState<WorkItem | null>(null);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  // Status change modal state
  const [statusModal, setStatusModal] = useState<{ visible: boolean; item?: WorkItem }>({ visible: false });
  const [newStatus, setNewStatus] = useState<WorkItemStatusType>('pending');
  const [remark, setRemark] = useState('');

  const { user } = useAuth();

  const canChange = useMemo(() => {
    if (!user) return false;
    return canChangeStatus(user.role, user.department_id);
  }, [user]);

  useEffect(() => {
    loadMyWork();
  }, []);

  const loadMyWork = async () => {
    try {
      const [data, deptsData, usersData] = await Promise.all([
        workItemApi.myWork(user?.email_prefix),
        departmentApi.list(),
        userApi.listBrief(),
      ]);
      setWorkItems(data);
      setDepartments(deptsData);
      setUsers(usersData);

      // 获取邮件链接状态
      const itemIds = data.map(i => i.id);
      if (itemIds.length > 0) {
        try {
          const linkRes = await workItemApi.getEmailLinkStatus(itemIds) as any;
          if (linkRes?.items) setEmailLinkStatus(linkRes.items);
        } catch {}
      }
    } catch {
      message.error('加载工作项失败');
    } finally {
      setLoading(false);
    }
  };

  const stats = {
    total: workItems.length,
    pending: workItems.filter((i) => i.status === 'pending').length,
    completed: workItems.filter((i) => i.status === 'completed').length,
    overdue: workItems.filter((i) => i.status === 'overdue').length,
    cancelled: workItems.filter((i) => i.status === 'cancelled').length,
  };

  const handleEmailLink = async (item: WorkItem) => {
    setEmailLoadingId(item.id);
    try {
      const res = await workItemApi.getEmailUrl(item.id) as any;
      if (res.url) {
        window.open(res.url, '_blank');
      } else if (res.search_url) {
        notification.warning({
          message: '未找到原邮件',
          description: (
            <span>
              可尝试搜索原邮件：
              <a href={res.search_url} target="_blank" rel="noopener noreferrer" style={{ color: '#1890ff' }}>
                在邮箱中搜索「{item.email_subject || item.title}」
              </a>
            </span>
          ),
          duration: 8,
        });
        setEmailLinkStatus(prev => ({ ...prev, [item.id]: false }));
      } else {
        message.warning(res.error || '未找到原邮件');
        setEmailLinkStatus(prev => ({ ...prev, [item.id]: false }));
      }
    } catch {
      message.error('获取邮件链接失败');
    } finally {
      setEmailLoadingId(null);
    }
  };

  const groupedByDept = useMemo(() => {
    const groups: Record<number, WorkItem[]> = {};
    const unassigned: WorkItem[] = [];

    workItems.forEach((item) => {
      if (item.department_id && item.department_id > 0) {
        if (!groups[item.department_id]) groups[item.department_id] = [];
        groups[item.department_id].push(item);
      } else {
        unassigned.push(item);
      }
    });

    const result: { deptId: number | null; deptName: string; items: WorkItem[] }[] = [];

    departments.forEach((dept) => {
      if (groups[dept.id] && groups[dept.id].length > 0) {
        result.push({ deptId: dept.id, deptName: dept.name, items: groups[dept.id] });
      }
    });

    if (unassigned.length > 0) {
      result.push({ deptId: null, deptName: '未分类', items: unassigned });
    }

    return result;
  }, [workItems, departments]);

  // --- Edit modal helpers ---
  const resolveAssigneeIds = (item: WorkItem): number[] => {
    if (item.assignee_email_prefix) {
      const prefixes = item.assignee_email_prefix.replace(/ /g, ',').split(',').map(s => s.trim()).filter(Boolean);
      return prefixes
        .map(prefix => users.find(u => u.email_prefix === prefix)?.id)
        .filter((id): id is number => id !== undefined);
    }
    if (item.assignee_id) return [item.assignee_id];
    return [];
  };

  const openEditModal = (item: WorkItem) => {
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
    setModalVisible(true);
  };

  const handleEditSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

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
      }

      setModalVisible(false);
      loadMyWork();
    } catch {
      message.error('操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  // --- Status change modal helpers ---
  const openStatusModal = (item: WorkItem) => {
    if (!canChange) {
      message.warning('您没有权限变更状态');
      return;
    }
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
      loadMyWork();
    } catch {
      message.error('状态更新失败');
    } finally {
      setSubmitting(false);
    }
  };

  const statusOptions = Object.entries(STATUS_LABELS).filter(([k]) => k !== 'overdue').map(([k, v]) => ({ value: k, label: v }));

  const columns: ColumnsType<WorkItem> = [
    {
      title: '标题', dataIndex: 'title', key: 'title', ellipsis: true, width: 250,
      render: (text: string, record: WorkItem) => (
        <a onClick={() => openEditModal(record)} style={{ cursor: 'pointer' }}>{text}</a>
      ),
    },
    {
      title: '类型', dataIndex: 'item_type', key: 'item_type', width: 80,
      render: (type: string) => <Tag color={TYPE_COLORS[type] || 'blue'}>{TYPE_LABELS[type] || type}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (status: string, record: WorkItem) => (
        <Tag
          color={STATUS_COLORS[status]}
          style={{ cursor: canChange ? 'pointer' : 'default' }}
          onClick={() => openStatusModal(record)}
        >
          {STATUS_LABELS[status]}
        </Tag>
      ),
    },
    {
      title: '截止日期', dataIndex: 'due_date', key: 'due_date', width: 120,
      render: (date: string) => formatUTCDate(date),
    },
    {
      title: '机密', dataIndex: 'is_confidential', key: 'is_confidential', width: 70,
      render: (v: boolean) => v ? <Tag color="red">机密</Tag> : <Tag>普通</Tag>,
    },
    {
      title: '邮件日期', dataIndex: 'email_date', key: 'email_date', width: 120,
      render: (date: string) => formatUTCDate(date),
    },
    {
      title: '原邮件', key: 'email_link', width: 70,
      render: (_: unknown, record: WorkItem) =>
        emailLinkStatus[record.id] ? (
          <Tooltip title="查看原邮件">
            <Button
              type="text"
              size="small"
              icon={emailLoadingId === record.id ? <LoadingOutlined /> : <LinkOutlined />}
              onClick={() => handleEmailLink(record)}
              style={{ color: '#1890ff' }}
            />
          </Tooltip>
        ) : null,
    },
  ];

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Title level={4}>我的工作 - {user?.real_name || user?.username}</Title>
      <Row gutter={16}>
        <Col span={5}><Card><Statistic title="全部" value={stats.total} prefix={<SyncOutlined />} /></Card></Col>
        <Col span={5}><Card><Statistic title="待处理" value={stats.pending} valueStyle={{ color: '#faad14' }} prefix={<ClockCircleOutlined />} /></Card></Col>
        <Col span={5}><Card><Statistic title="已完成" value={stats.completed} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col span={5}><Card><Statistic title="已逾时" value={stats.overdue} valueStyle={{ color: '#ff4d4f' }} prefix={<ExclamationCircleOutlined />} /></Card></Col>
        <Col span={4}><Card><Statistic title="不再进行" value={stats.cancelled} valueStyle={{ color: '#999' }} prefix={<StopOutlined />} /></Card></Col>
      </Row>

      <Collapse
        defaultActiveKey={groupedByDept.map((g) => String(g.deptId ?? 'none'))}
        style={{ background: 'transparent' }}
      >
        {groupedByDept.map((group, idx) => (
          <Collapse.Panel
            key={String(group.deptId ?? 'none')}
            header={
              <Space>
                <span style={{ fontWeight: 600 }}>{group.deptName}</span>
                <Tag color={DEPT_COLORS[idx % DEPT_COLORS.length]}>{group.items.length}</Tag>
              </Space>
            }
          >
            <Table
              columns={columns}
              dataSource={group.items}
              rowKey="id"
              pagination={false}
              size="small"
            />
          </Collapse.Panel>
        ))}
      </Collapse>

      {/* 编辑工作项弹窗 */}
      <Modal
        title="编辑工作项"
        open={modalVisible}
        onOk={handleEditSubmit}
        onCancel={() => setModalVisible(false)}
        confirmLoading={submitting}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="content" label="内容"><TextArea rows={4} /></Form.Item>
          <Form.Item name="item_type" label="类型" initialValue="task">
            <Select options={[{ value: 'task', label: '任务' }, { value: 'cosign', label: '会签' }, { value: 'report', label: '汇报' }]} />
          </Form.Item>
          <Form.Item name="status" label="状态" initialValue="pending">
            <Select options={statusOptions} disabled={!canChange} />
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

      {/* 状态变更弹窗 */}
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
    </Space>
  );
};

export default DashboardPage;
