import React, { useEffect, useState } from 'react';
import { Table, Button, Input, Select, Space, Tag, Typography, message } from 'antd';
import { ReloadOutlined, UploadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { ColumnsType } from 'antd/es/table';
import { ASSESSMENT_STATUS_LABELS, ASSESSMENT_STATUS_COLORS } from '../types';
import type { AssessmentListItem, SupplementRequest } from '../types';
import { assessmentApi } from '../services/api';
import SupplementSubmitModal from '../components/assessment/SupplementSubmitModal';

const { Text } = Typography;

/**
 * 我的考核：我作为责任人的考核列表，含状态与最终得分；
 * 状态为「待补充凭证」时可直接提交补充凭证。
 */
const MyAssessmentsPage: React.FC = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState<AssessmentListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(false);

  // 补充凭证
  const [supplementAssessmentId, setSupplementAssessmentId] = useState<number | null>(null);
  const [supplementRequest, setSupplementRequest] = useState<SupplementRequest | null>(null);

  const fetchData = async (p = page, ps = pageSize, kw = keyword, st = statusFilter) => {
    setLoading(true);
    try {
      const res = await assessmentApi.myAssessments({
        page: p,
        page_size: ps,
        keyword: kw || undefined,
        status: st,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(1, pageSize, keyword, statusFilter);
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleOpenSupplement = async (record: AssessmentListItem) => {
    try {
      const detail = await assessmentApi.detail(record.id);
      const pending = (detail.supplement_requests || []).find((r) => r.status === 'pending');
      if (!pending) {
        message.info('当前没有待提交的补充凭证请求');
        return;
      }
      setSupplementAssessmentId(record.id);
      setSupplementRequest(pending);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '加载补充凭证请求失败');
    }
  };

  const columns: ColumnsType<AssessmentListItem> = [
    {
      title: '工作项',
      dataIndex: 'work_item_title',
      key: 'work_item_title',
      render: (v, record) => (
        <a onClick={() => navigate(`/assessment/${record.id}`)}>{v || `考核 #${record.id}`}</a>
      ),
    },
    { title: '部门', dataIndex: 'department_name', key: 'department_name', width: 140, render: (v) => v || '-' },
    { title: '区域', dataIndex: 'district_name', key: 'district_name', width: 120, render: (v) => v || '-' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 150,
      render: (v: string) => <Tag color={ASSESSMENT_STATUS_COLORS[v]}>{ASSESSMENT_STATUS_LABELS[v] || v}</Tag>,
    },
    {
      title: '最终得分',
      dataIndex: 'final_score',
      key: 'final_score',
      width: 100,
      render: (v) => (v !== null && v !== undefined ? <Text strong style={{ color: '#1677ff' }}>{v}</Text> : '-'),
    },
    {
      title: '发起时间',
      dataIndex: 'initiated_at',
      key: 'initiated_at',
      width: 170,
      render: (v) => (v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 170,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/assessment/${record.id}`)}>详情</Button>
          {record.status === 'pending_supplement' && (
            <Button type="primary" size="small" icon={<UploadOutlined />} onClick={() => handleOpenSupplement(record)}>
              提交补充凭证
            </Button>
          )}
        </Space>
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
            style={{ width: 260 }}
            onSearch={(kw) => { setKeyword(kw); setPage(1); fetchData(1, pageSize, kw, statusFilter); }}
          />
          <Select
            placeholder="状态筛选"
            allowClear
            style={{ width: 180 }}
            value={statusFilter}
            onChange={(v) => { setStatusFilter(v); setPage(1); fetchData(1, pageSize, keyword, v); }}
            options={Object.entries(ASSESSMENT_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
          />
          <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
        </Space>
        <Text type="secondary">我作为责任人的考核记录</Text>
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

      <SupplementSubmitModal
        open={!!supplementRequest}
        assessmentId={supplementAssessmentId}
        request={supplementRequest}
        onCancel={() => { setSupplementRequest(null); setSupplementAssessmentId(null); }}
        onSuccess={() => { setSupplementRequest(null); setSupplementAssessmentId(null); fetchData(); }}
      />
    </div>
  );
};

export default MyAssessmentsPage;
