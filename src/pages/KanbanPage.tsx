import React, { useEffect, useState } from 'react';
import { Card, Select, Tag, Typography, Space, Spin, Empty, message, Tooltip, Badge } from 'antd';
import { kanbanApi, departmentApi } from '../services/api';
import type { KanbanData, Department, WorkItem } from '../types';
import { STATUS_LABELS, STATUS_COLORS } from '../types';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

const KanbanPage: React.FC = () => {
  const [kanbanData, setKanbanData] = useState<KanbanData[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [selectedDept, setSelectedDept] = useState<number | undefined>(undefined);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDepartments();
  }, []);

  useEffect(() => {
    loadKanban();
  }, [selectedDept]);

  const loadDepartments = async () => {
    try {
      const res = await departmentApi.list();
      setDepartments(res.data);
    } catch {
      message.error('加载部门失败');
    }
  };

  const loadKanban = async () => {
    setLoading(true);
    try {
      const res = await kanbanApi.get(selectedDept ? { department_id: selectedDept } : undefined);
      setKanbanData(res.data);
    } catch {
      message.error('加载看板数据失败');
    } finally {
      setLoading(false);
    }
  };

  const renderCard = (item: WorkItem) => (
    <Card key={item.id} size="small" style={{ marginBottom: 8, borderLeft: item.is_confidential ? '3px solid #ff4d4f' : '3px solid #1677ff' }}>
      <Tooltip title={item.content}>
        <Text strong ellipsis style={{ display: 'block', maxWidth: 200 }}>{item.title}</Text>
      </Tooltip>
      <Space size={4} style={{ marginTop: 4 }}>
        <Tag color={item.item_type === 'task' ? 'blue' : 'purple'} style={{ fontSize: 11 }}>
          {item.item_type === 'task' ? '任务' : '会签'}
        </Tag>
        {item.is_confidential && <Tag color="red" style={{ fontSize: 11 }}>机密</Tag>}
      </Space>
      <div style={{ marginTop: 4, fontSize: 12, color: '#666' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>{item.assignee_email_prefix || '未分配'}</Text>
        {item.due_date && (
          <Text type={dayjs(item.due_date).isBefore(dayjs()) ? 'danger' : 'secondary'} style={{ fontSize: 12, marginLeft: 8 }}>
            {dayjs(item.due_date).format('MM/DD')}
          </Text>
        )}
      </div>
    </Card>
  );

  const renderColumn = (title: string, items: WorkItem[], color: string) => (
    <div style={{ flex: 1, minWidth: 250 }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12, gap: 8 }}>
        <Badge status={color as 'default' | 'processing' | 'success' | 'error'} />
        <Text strong>{title}</Text>
        <Tag>{items.length}</Tag>
      </div>
      <div style={{ background: '#f5f5f5', borderRadius: 8, padding: 8, minHeight: 200 }}>
        {items.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无" /> : items.map(renderCard)}
      </div>
    </div>
  );

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={4} style={{ margin: 0 }}>工作看板</Title>
        <Select
          placeholder="筛选部门"
          allowClear
          style={{ width: 200 }}
          value={selectedDept}
          onChange={setSelectedDept}
          options={departments.map((d) => ({ value: d.id, label: d.name }))}
        />
      </div>
      {kanbanData.length === 0 ? (
        <Empty description="暂无看板数据" />
      ) : (
        kanbanData.map((dept) => (
          <Card key={dept.department_id} title={<Text strong>{dept.department_name}</Text>} style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', gap: 16, overflowX: 'auto' }}>
              {renderColumn('待处理', dept.pending, 'default')}
              {renderColumn('进行中', dept.in_progress, 'processing')}
              {renderColumn('已完成', dept.completed, 'success')}
              {renderColumn('已逾期', dept.overdue, 'error')}
            </div>
          </Card>
        ))
      )}
    </Space>
  );
};

export default KanbanPage;
