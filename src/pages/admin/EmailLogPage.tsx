import React, { useEffect, useState } from 'react';
import { Table, Typography, Tag, Space, Select } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { emailLogApi } from '../../services/api';
import type { EmailLog, EmailProcessResult } from '../../types';
import { EMAIL_PROCESS_RESULT_LABELS, EMAIL_PROCESS_RESULT_COLORS } from '../../types';
import dayjs from 'dayjs';

const { Title } = Typography;

const EmailLogPage: React.FC = () => {
  const [logs, setLogs] = useState<EmailLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterResult, setFilterResult] = useState<string | undefined>(undefined);

  useEffect(() => { loadLogs(); }, [filterResult]);

  const loadLogs = async () => {
    setLoading(true);
    try {
      const res = await emailLogApi.list({ process_result: filterResult, limit: 100 });
      setLogs(res.data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  const columns: ColumnsType<EmailLog> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '邮件主题', dataIndex: 'subject', key: 'subject', ellipsis: true, width: 250 },
    { title: '发件人', dataIndex: 'from_addr', key: 'from_addr', ellipsis: true, width: 180 },
    { 
      title: '处理结果', 
      dataIndex: 'process_result', 
      key: 'process_result', 
      width: 120,
      render: (s: EmailProcessResult) => (
        <Tag color={EMAIL_PROCESS_RESULT_COLORS[s]}>
          {EMAIL_PROCESS_RESULT_LABELS[s]}
        </Tag>
      )
    },
    { title: '重试次数', dataIndex: 'retry_count', key: 'retry_count', width: 90 },
    { title: '工作项ID', dataIndex: 'work_item_id', key: 'work_item_id', width: 90, render: (v: number | null) => v || '-' },
    { 
      title: '错误信息', 
      dataIndex: 'error_message', 
      key: 'error_message', 
      ellipsis: true,
      render: (v: string | null) => v || '-'
    },
    { 
      title: '接收时间', 
      dataIndex: 'received_at', 
      key: 'received_at', 
      width: 170, 
      render: (v: string | null) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-'
    },
    { 
      title: '创建时间', 
      dataIndex: 'created_at', 
      key: 'created_at', 
      width: 170, 
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm:ss')
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={4} style={{ margin: 0 }}>邮件处理日志</Title>
        <Select
          placeholder="筛选处理结果"
          allowClear
          style={{ width: 150 }}
          value={filterResult}
          onChange={(v) => setFilterResult(v)}
          options={[
            { label: '成功', value: 'SUCCESS' },
            { label: 'AI分析失败', value: 'AI_FAILED' },
            { label: '重试', value: 'RETRY' },
          ]}
        />
      </div>
      <Table 
        columns={columns} 
        dataSource={logs} 
        rowKey="id" 
        loading={loading} 
        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
        scroll={{ x: 1400 }}
      />
    </Space>
  );
};

export default EmailLogPage;
