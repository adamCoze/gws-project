import React, { useEffect, useState } from 'react';
import { Table, Tag, Card, Typography, Space, Statistic, Row, Col, Spin, message } from 'antd';
import { CheckCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined, SyncOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { workItemApi } from '../services/api';
import { useAuth } from '../components/AuthProvider';
import type { WorkItem } from '../types';
import { STATUS_LABELS, STATUS_COLORS } from '../types';
import dayjs from 'dayjs';

const { Title } = Typography;

const DashboardPage: React.FC = () => {
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();

  useEffect(() => {
    loadMyWork();
  }, []);

  const loadMyWork = async () => {
    try {
      const res = await workItemApi.myWork();
      setWorkItems(res.data);
    } catch {
      message.error('加载工作项失败');
    } finally {
      setLoading(false);
    }
  };

  const stats = {
    total: workItems.length,
    pending: workItems.filter((i) => i.status === 'pending').length,
    inProgress: workItems.filter((i) => i.status === 'in_progress').length,
    completed: workItems.filter((i) => i.status === 'completed').length,
    overdue: workItems.filter((i) => i.status === 'overdue').length,
  };

  const columns: ColumnsType<WorkItem> = [
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true, width: 250 },
    {
      title: '类型',
      dataIndex: 'item_type',
      key: 'item_type',
      width: 80,
      render: (type: string) => <Tag color={type === 'task' ? 'blue' : 'purple'}>{type === 'task' ? '任务' : '会签'}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => <Tag color={STATUS_COLORS[status as keyof typeof STATUS_COLORS]}>{STATUS_LABELS[status as keyof typeof STATUS_LABELS]}</Tag>,
    },
    {
      title: '部门',
      key: 'department',
      width: 120,
      render: (_: unknown, record: WorkItem) => record.department?.name || '-',
    },
    {
      title: '截止日期',
      dataIndex: 'due_date',
      key: 'due_date',
      width: 120,
      render: (date: string) => date ? dayjs(date).format('YYYY-MM-DD') : '-',
    },
    {
      title: '机密',
      dataIndex: 'is_confidential',
      key: 'is_confidential',
      width: 70,
      render: (v: boolean) => v ? <Tag color="red">机密</Tag> : <Tag>普通</Tag>,
    },
    {
      title: '邮件日期',
      dataIndex: 'email_date',
      key: 'email_date',
      width: 120,
      render: (date: string) => dayjs(date).format('YYYY-MM-DD'),
    },
  ];

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Title level={4}>我的工作 - {user?.username}</Title>
      <Row gutter={16}>
        <Col span={5}><Card><Statistic title="全部" value={stats.total} prefix={<SyncOutlined />} /></Card></Col>
        <Col span={5}><Card><Statistic title="待处理" value={stats.pending} valueStyle={{ color: '#faad14' }} prefix={<ClockCircleOutlined />} /></Card></Col>
        <Col span={5}><Card><Statistic title="进行中" value={stats.inProgress} valueStyle={{ color: '#1677ff' }} prefix={<SyncOutlined />} /></Card></Col>
        <Col span={5}><Card><Statistic title="已完成" value={stats.completed} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col span={4}><Card><Statistic title="已逾期" value={stats.overdue} valueStyle={{ color: '#ff4d4f' }} prefix={<ExclamationCircleOutlined />} /></Card></Col>
      </Row>
      <Table columns={columns} dataSource={workItems} rowKey="id" pagination={{ pageSize: 15, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }} />
    </Space>
  );
};

export default DashboardPage;
