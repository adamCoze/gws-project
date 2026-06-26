import { formatUTCDate } from '../../utils/date';
import React, { useState, useEffect } from 'react';
import { Table, Tag, Tooltip } from 'antd';
import { emailLogApi } from '../../services/api';
import type { EmailLog } from '../../types';

const resultLabels: Record<string, { label: string; color: string }> = {
  success: { label: '成功', color: 'green' },
  ai_failed: { label: 'AI失败', color: 'red' },
  retry: { label: '重试', color: 'orange' },
};

const EmailLogPage: React.FC = () => {
  const [logs, setLogs] = useState<EmailLog[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const data = await emailLogApi.list({ limit: 10000 });
      setLogs(data);
    } catch {
      // error handled
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
    },
    {
      title: '邮件主题',
      dataIndex: 'subject',
      key: 'subject',
      width: 400,
      ellipsis: true,
      render: (text: string) => (
        <Tooltip title={text} placement="topLeft">
          <span>{text || '-'}</span>
        </Tooltip>
      ),
    },
    {
      title: '发件人',
      dataIndex: 'from_addr',
      key: 'from_addr',
      width: 200,
      ellipsis: true,
    },
    {
      title: '接收时间',
      dataIndex: 'received_at',
      key: 'received_at',
      width: 180,
      render: (v: string) => formatUTCDate(v, 'YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '处理结果',
      dataIndex: 'process_result',
      key: 'process_result',
      width: 100,
      render: (result: string) => {
        const info = resultLabels[result] || { label: result, color: 'default' };
        return <Tag color={info.color}>{info.label}</Tag>;
      },
    },
    {
      title: '重试次数',
      dataIndex: 'retry_count',
      key: 'retry_count',
      width: 80,
    },
    {
      title: '关联工作项',
      dataIndex: 'work_item_id',
      key: 'work_item_id',
      width: 100,
      render: (id: number) => id ? `#${id}` : '-',
    },
    {
      title: '错误信息',
      dataIndex: 'error_message',
      key: 'error_message',
      width: 200,
      ellipsis: true,
      render: (text: string) => text ? (
        <Tooltip title={text} placement="topLeft">
          <span style={{ color: '#ff4d4f' }}>{text}</span>
        </Tooltip>
      ) : '-',
    },
  ];

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>邮件处理日志</h2>
      <Table
        columns={columns}
        dataSource={logs}
        rowKey="id"
        loading={loading}
        pagination={{ showTotal: (t) => `共 ${t} 条`, showSizeChanger: true, pageSizeOptions: [20, 50, 100], defaultPageSize: 20 }}
        scroll={{ x: 1300 }}
      />
    </div>
  );
};

export default EmailLogPage;
