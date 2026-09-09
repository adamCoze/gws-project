import React, { useEffect, useState } from 'react';
import { Table, Button, Input, Space, Tag, Popconfirm, Typography, message } from 'antd';
import { ReloadOutlined, RollbackOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { NonAssessmentItem } from '../types';
import { assessmentApi } from '../services/api';

const { Text } = Typography;

/**
 * 非考核项：已标记为非考核的工作项清单，支持撤销标记（撤销后回到待考核清单）
 */
const NonAssessmentPage: React.FC = () => {
  const [items, setItems] = useState<NonAssessmentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(false);

  const fetchData = async (p = page, ps = pageSize, kw = keyword) => {
    setLoading(true);
    try {
      const res = await assessmentApi.nonAssessmentList({ page: p, page_size: ps, keyword: kw || undefined });
      setItems(res.items);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(1, pageSize, keyword);
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRevoke = async (record: NonAssessmentItem) => {
    try {
      await assessmentApi.revokeNonAssessment(record.work_item_id);
      message.success('已撤销，该工作项回到待考核清单');
      fetchData();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '撤销失败');
    }
  };

  const columns: ColumnsType<NonAssessmentItem> = [
    {
      title: '工作项',
      dataIndex: 'work_item_title',
      key: 'work_item_title',
      render: (v, record) => (
        <Space>
          <Text strong>{v || `工作项 #${record.work_item_id}`}</Text>
          {record.revoked && <Tag>已撤销</Tag>}
        </Space>
      ),
    },
    { title: '部门', dataIndex: 'department_name', key: 'department_name', width: 140, render: (v) => v || '-' },
    { title: '区域', dataIndex: 'district_name', key: 'district_name', width: 120, render: (v) => v || '-' },
    { title: '责任人', dataIndex: 'sponsor_name', key: 'sponsor_name', width: 120, render: (v) => v || '-' },
    { title: '备注', dataIndex: 'remark', key: 'remark', ellipsis: true, render: (v) => v || '-' },
    { title: '标记人', dataIndex: 'marked_by_name', key: 'marked_by_name', width: 110, render: (v) => v || '-' },
    {
      title: '标记时间',
      dataIndex: 'marked_at',
      key: 'marked_at',
      width: 170,
      render: (v) => (v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 110,
      render: (_, record) =>
        record.revoked ? null : (
          <Popconfirm title="撤销后将回到待考核清单，确认撤销？" onConfirm={() => handleRevoke(record)}>
            <Button size="small" icon={<RollbackOutlined />}>撤销</Button>
          </Popconfirm>
        ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <Input.Search
            placeholder="搜索工作项标题"
            allowClear
            style={{ width: 280 }}
            onSearch={(kw) => { setKeyword(kw); setPage(1); fetchData(1, pageSize, kw); }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
        </Space>
        <Text type="secondary">标记为非考核的工作项，撤销后回到待考核清单</Text>
      </Space>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps); fetchData(p, ps); },
        }}
      />
    </div>
  );
};

export default NonAssessmentPage;
