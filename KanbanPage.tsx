import React, { useState, useEffect, useMemo } from 'react';
import { Card, Tag, Select, Modal, Form, Input, message, Spin, Empty, Typography, Descriptions, Collapse, Row, Col, Badge, Space, Button, Tooltip } from 'antd';
import { LinkOutlined, LoadingOutlined } from '@ant-design/icons';
import { kanbanApi, workItemApi, departmentApi } from '../services/api';
import { useAuth } from '../components/AuthProvider';
import type { WorkItem, Department, WorkItemStatus as WorkItemStatusType, RoleType } from '../types';
import { STATUS_LABELS, STATUS_COLORS, ROLE_LEVELS } from '../types';

const { TextArea } = Input;
const { Text } = Typography;

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
  const [loading, setLoading] = useState(false);
  const [statusModal, setStatusModal] = useState<{ visible: boolean; item?: WorkItem }>({ visible: false });
  const [detailModal, setDetailModal] = useState<{ visible: boolean; item?: WorkItem }>({ visible: false });
  const [newStatus, setNewStatus] = useState<WorkItemStatusType>('pending');
  const [remark, setRemark] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [emailLoadingId, setEmailLoadingId] = useState<number | null>(null);
  const [emailLinkStatus, setEmailLinkStatus] = useState<Record<number, boolean>>({});

  const hasPermission = useMemo(() => {
    if (!user) return false;
    return canChangeStatus(user.role, user.department_id);
  }, [user]);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const [data, deptsData] = await Promise.all([
        kanbanApi.get(),
        departmentApi.list(),
      ]);
      setKanbanData(data as unknown as KanbanDeptData[]);
      setDepartments(deptsData);

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

  const openStatusModal = (item: WorkItem) => {
    if (hasPermission) {
      setStatusModal({ visible: true, item });
      setNewStatus(item.status);
      setRemark('');
    } else {
      setDetailModal({ visible: true, item });
    }
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
      fetchItems();
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

  const handleEmailLink = async (e: React.MouseEvent, item: WorkItem) => {
    e.stopPropagation();
    setEmailLoadingId(item.id);
    try {
      const res = await workItemApi.getEmailUrl(item.id) as any;
      if (res.url) {
        window.open(res.url, '_blank');
      } else {
        message.warning(res.error || '未找到原邮件');
        // 更新状态：标记为无链接
        setEmailLinkStatus(prev => ({ ...prev, [item.id]: false }));
      }
    } catch {
      message.error('获取邮件链接失败');
    } finally {
      setEmailLoadingId(null);
    }
  };


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
                            style={{ marginBottom: 6, cursor: hasPermission ? 'pointer' : 'default' }}
                            hoverable={hasPermission}
                            onClick={() => openStatusModal(item)}
                          >
                            <div style={{ fontWeight: 500, marginBottom: 4, fontSize: 13 }}>{item.title}</div>
                            <div style={{ fontSize: 12, color: '#999' }}>
                              负责人: {getAssigneeName(item)}
                            </div>
                            {item.due_date && (
                              <div style={{ fontSize: 12, color: '#999' }}>
                                截止: {new Date(item.due_date).toLocaleDateString()}
                              </div>
                            )}
                            <div style={{ marginTop: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <div>
                                <Tag color={item.item_type === 'cosign' ? 'purple' : 'blue'} style={{ fontSize: 11 }}>
                                  {item.item_type === 'cosign' ? '会签' : '任务'}
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

      {/* 有权限：状态变更弹窗 */}
      <Modal
        title={`变更状态 - ${statusModal.item?.title}`}
        open={statusModal.visible}
        onOk={handleStatusChange}
        onCancel={() => setStatusModal({ visible: false })}
        confirmLoading={submitting}
      >
        <Form layout="vertical">
          <Form.Item label="新状态">
            <Select
              value={newStatus}
              onChange={setNewStatus}
              options={statusOrder.filter((s) => s !== 'overdue').map((s) => ({ value: s, label: STATUS_LABELS[s] }))}
            />
          </Form.Item>
          <Form.Item label="备注">
            <TextArea
              value={remark}
              onChange={(e) => setRemark(e.target.value)}
              placeholder="可选：填写状态变更原因"
              rows={3}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 无权限：只读详情弹窗 */}
      <Modal
        title={`工作项详情 - ${detailModal.item?.title}`}
        open={detailModal.visible}
        onCancel={() => setDetailModal({ visible: false })}
        footer={null}
        width={600}
      >
        {detailModal.item && (
          <div>
            <Descriptions bordered column={1} size="small">
              <Descriptions.Item label="标题">{detailModal.item.title}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={STATUS_COLORS[detailModal.item.status]}>
                  {STATUS_LABELS[detailModal.item.status]}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="类型">
                <Tag color={detailModal.item.item_type === 'cosign' ? 'purple' : 'blue'}>
                  {detailModal.item.item_type === 'cosign' ? '会签' : '任务'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="部门">{detailModal.item.department?.name || '-'}</Descriptions.Item>
              <Descriptions.Item label="负责人">{getAssigneeName(detailModal.item)}</Descriptions.Item>
              <Descriptions.Item label="截止日期">
                {detailModal.item.due_date ? new Date(detailModal.item.due_date).toLocaleDateString() : '-'}
              </Descriptions.Item>
              {detailModal.item.content && (
                <Descriptions.Item label="内容">{detailModal.item.content}</Descriptions.Item>
              )}
            </Descriptions>
            <div style={{ marginTop: 16 }}>
              <Text type="warning">您没有权限变更状态，请联系管理员或规管。</Text>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default KanbanPage;
