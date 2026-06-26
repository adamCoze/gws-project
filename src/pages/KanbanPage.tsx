import React, { useState, useEffect, useMemo } from 'react';
import { Card, Tag, Select, Modal, Form, Input, message, Spin, Empty, Typography, Collapse, Row, Col, Badge, Space, Button, Tooltip } from 'antd';
import { LinkOutlined, LoadingOutlined } from '@ant-design/icons';
import { kanbanApi, workItemApi, departmentApi, userApi } from '../services/api';
import { useAuth } from '../components/AuthProvider';
import { formatUTCDate } from '../utils/date';
import type { WorkItem, Department, WorkItemStatus as WorkItemStatusType, RoleType } from '../types';
import { STATUS_LABELS, STATUS_COLORS, ROLE_LEVELS, TYPE_LABELS, TYPE_COLORS } from '../types';

const { TextArea } = Input;

// 人事/商务部ID
const HR_COMMERCE_DEPT_ID = 1;

const statusOrder: WorkItemStatusType[] = ['pending', 'overdue', 'completed', 'cancelled'];

const DEPT_COLORS = ['#1890ff', '#52c41a', '#faad14', '#722ed1'];

interface KanbanDeptData {
  department_id: number;
  department_name: string;
  pending: WorkItem[];
  overdue: WorkItem[];
  completed: WorkItem[];
  cancelled: WorkItem[];
}

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

const KanbanPage: React.FC = () => {
  const { user } = useAuth();
  const [kanbanData, setKanbanData] = useState<KanbanDeptData[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [users, setUsers] = useState<UserBrief[]>([]);
  const [loading, setLoading] = useState(false);

  // Edit modal state
  const [editModal, setEditModal] = useState<{ visible: boolean; item?: WorkItem }>({ visible: false });
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const [emailLoadingId, setEmailLoadingId] = useState<number | null>(null);
  const [emailLinkStatus, setEmailLinkStatus] = useState<Record<number, boolean>>({});

  const canChange = useMemo(() => {
    if (!user) return false;
    return canChangeStatus(user.role, user.department_id);
  }, [user]);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const [data, deptsData, usersData] = await Promise.all([
        kanbanApi.get(),
        departmentApi.list(),
        userApi.listBrief(),
      ]);
      setKanbanData(data as unknown as KanbanDeptData[]);
      setDepartments(deptsData);
      setUsers(usersData);

      // 获取邮件链接状态
      const allItems = (data as unknown as KanbanDeptData[]).flatMap(d => [...d.pending, ...d.overdue, ...d.completed, ...d.cancelled]);
      const itemIds = allItems.map(i => i.id);
      if (itemIds.length > 0) {
        try {
          const linkRes = await workItemApi.getEmailLinkStatus(itemIds) as any;
          if (linkRes?.items) setEmailLinkStatus(linkRes.items);
        } catch {}
      }
    } catch {
      message.error('获取看板数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchItems();
  }, []);

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
    setEditModal({ visible: true, item });
  };

  const handleEditSubmit = async () => {
    if (!editModal.item) return;
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

      await workItemApi.update(editModal.item.id, submitData);
      message.success('工作项已更新');
      setEditModal({ visible: false });
      fetchItems();
    } catch {
      message.error('操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  const getAssigneeName = (item: WorkItem): string => {
    if (item.assignee_names) return item.assignee_names;
    if (item.assignee?.real_name) return item.assignee.real_name;
    return '未分配';
  };

  const handleEmailLink = async (e: React.MouseEvent, item: WorkItem) => {
    e.stopPropagation();
    setEmailLoadingId(item.id);
    try {
      const res = await workItemApi.getEmailUrl(item.id) as any;
      if (res.url) {
        window.open(res.url, '_blank');
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

  const statusOptions = Object.entries(STATUS_LABELS).filter(([k]) => k !== 'overdue').map(([k, v]) => ({ value: k, label: v }));

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 100 }}><Spin size="large" /></div>;
  }

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>工作看板</h2>
      <Collapse
        defaultActiveKey={kanbanData.map((d) => String(d.department_id))}
        style={{ background: 'transparent' }}
      >
        {kanbanData.map((dept, deptIdx) => {
          const totalItems = dept.pending.length + dept.overdue.length + dept.completed.length + dept.cancelled.length;
          return (
            <Collapse.Panel
              key={String(dept.department_id)}
              header={
                <Space>
                  <span style={{ fontWeight: 600, fontSize: 15 }}>{dept.department_name}</span>
                  <Badge count={totalItems} style={{ backgroundColor: DEPT_COLORS[deptIdx % DEPT_COLORS.length] }} />
                </Space>
              }
            >
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                {statusOrder.map((status) => {
                  const items = dept[status] as WorkItem[];
                  return (
                    <div key={status}>
                      <div style={{ marginBottom: 8, fontWeight: 600, fontSize: 14 }}>
                        {STATUS_LABELS[status]}
                        <Tag color={STATUS_COLORS[status]} style={{ marginLeft: 6 }}>{items.length}</Tag>
                      </div>
                      {items.length === 0 ? (
                        <Empty description="暂无" style={{ padding: 16 }} image={Empty.PRESENTED_IMAGE_SIMPLE} />
                      ) : (
                        items.map((item) => (
                          <Card
                            key={item.id}
                            size="small"
                            style={{ marginBottom: 6, cursor: 'pointer' }}
                            hoverable
                            onClick={() => openEditModal(item)}
                          >
                            <div style={{ fontWeight: 500, marginBottom: 4, fontSize: 13 }}>{item.title}</div>
                            <div style={{ fontSize: 12, color: '#999' }}>
                              负责人: {getAssigneeName(item)}
                            </div>
                            {item.due_date && (
                              <div style={{ fontSize: 12, color: '#999' }}>
                                截止: {formatUTCDate(item.due_date)}
                              </div>
                            )}
                            <div style={{ marginTop: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <div>
                                <Tag color={TYPE_COLORS[item.item_type] || 'blue'} style={{ fontSize: 11 }}>
                                  {TYPE_LABELS[item.item_type] || item.item_type}
                                </Tag>
                                {item.is_confidential && <Tag color="red" style={{ fontSize: 11 }}>机密</Tag>}
                              </div>
                              {emailLinkStatus[item.id] && (
                                <Tooltip title="查看原邮件">
                                  <Button
                                    type="text"
                                    size="small"
                                    icon={emailLoadingId === item.id ? <LoadingOutlined /> : <LinkOutlined />}
                                    onClick={(e) => handleEmailLink(e, item)}
                                    style={{ color: '#1890ff', padding: '0 4px' }}
                                  />
                                </Tooltip>
                              )}
                            </div>
                          </Card>
                        ))
                      )}
                    </div>
                  );
                })}
              </div>
            </Collapse.Panel>
          );
        })}
      </Collapse>

      {/* 编辑工作项弹窗 */}
      <Modal
        title={`编辑工作项 - ${editModal.item?.title || ''}`}
        open={editModal.visible}
        onOk={handleEditSubmit}
        onCancel={() => setEditModal({ visible: false })}
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
    </div>
  );
};

export default KanbanPage;
