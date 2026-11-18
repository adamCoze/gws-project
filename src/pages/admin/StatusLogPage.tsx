import React, { useEffect, useState } from 'react';
import { Table, Typography, Tag, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { statusChangeLogApi } from '../../services/api';
import type { StatusChangeLog } from '../../types';
import { STATUS_LABELS, STATUS_COLORS } from '../../types';
import type { WorkItemStatus } from '../../types';
import { formatUTCDate } from '../../utils/date';
import { useIsMobile } from '../../hooks/useIsMobile';
import MobileCardList from '../../components/MobileCardList';

const { Title } = Typography;

const StatusLogPage: React.FC = () => {
  const isMobile = useIsMobile();
  const [logs, setLogs] = useState<StatusChangeLog[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => { loadLogs(); }, []);

  const loadLogs = async () => {
    setLoading(true);
    try {
      const data = await statusChangeLogApi.list();
      setLogs(data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  const columns: ColumnsType<StatusChangeLog> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '工作项ID', dataIndex: 'work_item_id', key: 'work_item_id', width: 90 },
    { title: '工作项标题', dataIndex: 'work_item_title', key: 'work_item_title', width: 250, ellipsis: true },
    { title: '原状态', dataIndex: 'old_status', key: 'old_status', width: 100, render: (s: string) => <Tag color={STATUS_COLORS[s as WorkItemStatus]}>{STATUS_LABELS[s as WorkItemStatus]}</Tag> },
    { title: '新状态', dataIndex: 'new_status', key: 'new_status', width: 100, render: (s: string) => <Tag color={STATUS_COLORS[s as WorkItemStatus]}>{STATUS_LABELS[s as WorkItemStatus]}</Tag> },
    { title: '操作人', dataIndex: 'changed_by', key: 'changed_by', width: 120, render: (v: string) => v || '-' },
    { title: '备注', dataIndex: 'remark', key: 'remark', ellipsis: true },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 170, render: (v: string) => formatUTCDate(v, 'YYYY-MM-DD HH:mm:ss') },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Title level={isMobile ? 5 : 4} style={{ margin: 0 }}>状态变更日志</Title>
      {isMobile ? (
        <MobileCardList
          items={logs}
          rowKey={(r) => r.id}
          loading={loading}
          emptyText="暂无状态变更日志"
          pageSize={20}
          renderCard={(r: StatusChangeLog) => (
            <>
              <div className="m-card-title">{r.work_item_title || `工作项 #${r.work_item_id}`}</div>
              <div className="m-card-meta">
                <span>
                  <Tag color={STATUS_COLORS[r.old_status as WorkItemStatus]} style={{ margin: 0 }}>{STATUS_LABELS[r.old_status as WorkItemStatus]}</Tag>
                  {' → '}
                  <Tag color={STATUS_COLORS[r.new_status as WorkItemStatus]} style={{ margin: 0 }}>{STATUS_LABELS[r.new_status as WorkItemStatus]}</Tag>
                </span>
                <span>操作人：{r.changed_by || '-'}</span>
                <span>{formatUTCDate(r.created_at, 'YYYY-MM-DD HH:mm')}</span>
                {r.remark ? <span>备注：{r.remark}</span> : null}
              </div>
            </>
          )}
        />
      ) : (
        <Table columns={columns} dataSource={logs} rowKey="id" loading={loading} pagination={{ showTotal: (t) => `共 ${t} 条`, showSizeChanger: true, pageSizeOptions: [20, 50, 100], defaultPageSize: 20 }} />
      )}
    </Space>
  );
};

export default StatusLogPage;
