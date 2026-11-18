import React, { useEffect, useState } from 'react';
import { Table, Button, Input, Space, Tag, Popconfirm, Typography, message } from 'antd';
import { ReloadOutlined, RollbackOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { NonAssessmentItem } from '../types';
import { assessmentApi } from '../services/api';
import { useIsMobile } from '../hooks/useIsMobile';
import MobileCardList from '../components/MobileCardList';

const { Text } = Typography;

/**
 * 非考核项：已标记为非考核的工作项清单，支持撤销标记（撤销后回到待考核清单）
 */
const NonAssessmentPage: React.FC = () => {
  const isMobile = useIsMobile();
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
    { title: '主办人', dataIndex: 'sponsor_name', key: 'sponsor_name', width: 120, render: (v) => v || '-' },
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
      <Space direction={isMobile ? 'vertical' : 'horizontal'} style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space direction={isMobile ? 'vertical' : 'horizontal'} style={isMobile ? { width: '100%' } : undefined}>
          <Input.Search
            placeholder="搜索工作项标题"
            allowClear
            style={{ width: isMobile ? '100%' : 280 }}
            onSearch={(kw) => { setKeyword(kw); setPage(1); fetchData(1, pageSize, kw); }}
          />
          <Button style={isMobile ? { width: '100%' } : undefined} icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
        </Space>
        {!isMobile && <Text type="secondary">标记为非考核的工作项，撤销后回到待考核清单</Text>}
      </Space>

      {isMobile ? (
        <MobileCardList
          items={items}
          rowKey={(r) => r.id}
          loading={loading}
          emptyText="暂无已标记的非考核项"
          serverSide
          total={total}
          page={page}
          pageSize={pageSize}
          onPageChange={(p, ps) => { setPage(p); setPageSize(ps); fetchData(p, ps); }}
          renderCard={(r: NonAssessmentItem) => (
            <>
              <div className="m-card-title">{r.work_item_title || `工作项 #${r.work_item_id}`}</div>
              <div className="m-card-meta">
                {r.revoked && <Tag style={{ margin: 0 }}>已撤销</Tag>}
                <span>{r.department_name || '-'} · {r.district_name || '-'}</span>
                <span>主办人：{r.sponsor_name || '-'}</span>
                <span>标记人：{r.marked_by_name || '-'}</span>
                {r.marked_at && <span>{new Date(r.marked_at).toLocaleString('zh-CN', { hour12: false })}</span>}
                {r.remark && <span>备注：{r.remark}</span>}
              </div>
              {!r.revoked && (
                <div className="m-card-actions">
                  <Popconfirm title="撤销后将回到待考核清单，确认撤销？" onConfirm={() => handleRevoke(r)}>
                    <Button size="small" icon={<RollbackOutlined />}>撤销标记</Button>
                  </Popconfirm>
                </div>
              )}
            </>
          )}
        />
      ) : (
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
      )}
    </div>
  );
};

export default NonAssessmentPage;
