import React, { useEffect, useState } from 'react';
import { Table, Typography, Tag, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { statusChangeLogApi } from '../../services/api';
import type { StatusChangeLog } from '../../types';
import { STATUS_LABELS, STATUS_COLORS } from '../../types';
import type { WorkItemStatus } from '../../types';
import dayjs from 'dayjs';

const { Title } = Typography;

const StatusLogPage: React.FC = () => {
  const [logs, setLogs] = useState<StatusChangeLog[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => { loadLogs(); }, []);

  const loadLogs = async () => {
    setLoading(true);
    try { const res = await statusChangeLogApi.list(); setLogs(res.data); } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  const columns: ColumnsType<StatusChangeLog> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '工作项ID', dataIndex: 'work_item_id', key: 'work_item_id', width: 90 },
    { title: '原状态', dataIndex: 'old_status', key: 'old_status', width: 100, render: (s: string) => <Tag color={STATUS_COLORS[s as WorkItemStatus]}>{STATUS_LABELS[s as WorkItemStatus]}</Tag> },
    { title: '新状态', dataIndex: 'new_status', key: 'new_status', width: 100, render: (s: string) => <Tag color={STATUS_COLORS[s as WorkItemStatus]}>{STATUS_LABELS[s as WorkItemStatus]}</Tag> },
    { title: '操作人', key: 'operator', width: 120, render: (_: unknown, r: StatusChangeLog) => r.operator?.username || '-' },
    { title: '备注', dataIndex: 'remark', key: 'remark', ellipsis: true },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 170, render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm:ss') },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Title level={4} style={{ margin: 0 }}>状态变更日志</Title>
      <Table columns={columns} dataSource={logs} rowKey="id" loading={loading} pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }} />
    </Space>
  );
};

export default StatusLogPage;
