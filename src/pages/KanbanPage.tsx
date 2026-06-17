import React, { useState, useEffect } from 'react';
import { Card, Tag, Select, Modal, Form, Input, message, Spin, Empty } from 'antd';
import { workItemApi } from '../services/api';
import type { WorkItem, WorkItemStatus as WorkItemStatusType } from '../types';
import { STATUS_LABELS, STATUS_COLORS } from '../types';

const { TextArea } = Input;

const statusOrder: WorkItemStatusType[] = ['pending', 'shelved', 'completed', 'cancelled'];

const KanbanPage: React.FC = () => {
  const [items, setItems] = useState<WorkItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusModal, setStatusModal] = useState<{ visible: boolean; item?: WorkItem }>({ visible: false });
  const [newStatus, setNewStatus] = useState<WorkItemStatusType>('pending');
  const [remark, setRemark] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const data = await workItemApi.list({ page_size: 100 });
      setItems(data);
    } catch {
      message.error('获取工作项失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchItems();
  }, []);

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
      fetchItems();
    } catch {
      message.error('状态更新失败');
    } finally {
      setSubmitting(false);
    }
  };

  const getAssigneeName = (item: WorkItem): string => {
    if (item.assignee?.real_name) return item.assignee.real_name;
    if (item.assignee_email_prefix) return item.assignee_email_prefix;
    return '未分配';
  };

  const columns: Record<WorkItemStatusType, WorkItem[]> = {
    pending: [],
    shelved: [],
    completed: [],
    cancelled: [],
  };

  items.forEach((item) => {
    if (columns[item.status as WorkItemStatusType]) {
      columns[item.status as WorkItemStatusType].push(item);
    }
  });

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 100 }}><Spin size="large" /></div>;
  }

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>工作看板</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        {statusOrder.map((status) => (
          <div key={status}>
            <div style={{ marginBottom: 12, fontWeight: 600, fontSize: 16 }}>
              {STATUS_LABELS[status]}
              <Tag color={STATUS_COLORS[status]} style={{ marginLeft: 8 }}>{columns[status].length}</Tag>
            </div>
            {columns[status].length === 0 ? (
              <Empty description="暂无" style={{ padding: 20 }} />
            ) : (
              columns[status].map((item) => (
                <Card
                  key={item.id}
                  size="small"
                  style={{ marginBottom: 8, cursor: 'pointer' }}
                  hoverable
                  onClick={() => openStatusModal(item)}
                >
                  <div style={{ fontWeight: 500, marginBottom: 4 }}>{item.title}</div>
                  <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>
                    {item.department?.name || '未分类'}
                  </div>
                  <div style={{ fontSize: 12, color: '#999' }}>
                    负责人: {getAssigneeName(item)}
                  </div>
                  {item.due_date && (
                    <div style={{ fontSize: 12, color: '#999' }}>
                      截止: {new Date(item.due_date).toLocaleDateString()}
                    </div>
                  )}
                  <div style={{ marginTop: 4 }}>
                    <Tag color={item.item_type === 'cosign' ? 'purple' : 'blue'}>
                      {item.item_type === 'cosign' ? '会签' : '任务'}
                    </Tag>
                    {item.is_confidential && <Tag color="red">机密</Tag>}
                  </div>
                </Card>
              ))
            )}
          </div>
        ))}
      </div>

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
              options={statusOrder.map((s) => ({ value: s, label: STATUS_LABELS[s] }))}
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
    </div>
  );
};

export default KanbanPage;
