import React, { useEffect, useState, useMemo } from 'react';
import { Table, Tag, Card, Typography, Space, Statistic, Row, Col, Spin, message, Collapse } from 'antd';
import { CheckCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined, StopOutlined, SyncOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { workItemApi, departmentApi } from '../services/api';
import { useAuth } from '../components/AuthProvider';
import type { WorkItem, Department } from '../types';
import { STATUS_LABELS, STATUS_COLORS } from '../types';
import dayjs from 'dayjs';

const { Title } = Typography;

const DEPT_COLORS = ['#1890ff', '#52c41a', '#faad14', '#722ed1'];

const DashboardPage: React.FC = () => {
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();

  useEffect(() => {
    loadMyWork();
  }, []);

  const loadMyWork = async () => {
    try {
      const [data, deptsData] = await Promise.all([
        workItemApi.myWork(user?.email_prefix),
        departmentApi.list(),
      ]);
      setWorkItems(data);
      setDepartments(deptsData);
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

  // Group by department
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
    
    // Add departments in order
    departments.forEach((dept) => {
      if (groups[dept.id] && groups[dept.id].length > 0) {
        result.push({ deptId: dept.id, deptName: dept.name, items: groups[dept.id] });
      }
    });
    
    // Add unassigned items at the end
    if (unassigned.length > 0) {
      result.push({ deptId: null, deptName: '未分类', items: unassigned });
    }
    
    return result;
  }, [workItems, departments]);

  const columns: ColumnsType<WorkItem> = [
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true, width: 250 },
    {
      title: '类型', dataIndex: 'item_type', key: 'item_type', width: 80,
      render: (type: string) => <Tag color={type === 'task' ? 'blue' : 'purple'}>{type === 'task' ? '任务' : '会签'}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (status: string) => <Tag color={STATUS_COLORS[status]}>{STATUS_LABELS[status]}</Tag>,
    },
    {
      title: '截止日期', dataIndex: 'due_date', key: 'due_date', width: 120,
      render: (date: string) => date ? dayjs(date).format('YYYY-MM-DD') : '-',
    },
    {
      title: '机密', dataIndex: 'is_confidential', key: 'is_confidential', width: 70,
      render: (v: boolean) => v ? <Tag color="red">机密</Tag> : <Tag>普通</Tag>,
    },
    {
      title: '邮件日期', dataIndex: 'email_date', key: 'email_date', width: 120,
      render: (date: string) => date ? dayjs(date).format('YYYY-MM-DD') : '-',
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
    </Space>
  );
};

export default DashboardPage;
