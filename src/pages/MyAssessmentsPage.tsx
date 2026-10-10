import React, { useEffect, useState } from 'react';
import { Table, Button, Input, Select, Space, Tag, Typography, message, Modal, Form } from 'antd';
import { ReloadOutlined, UploadOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
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
  const [monthFilter, setMonthFilter] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(false);

  // 近13个月选项（按发起时间筛选）
  const monthOptions = React.useMemo(() => {
    const now = new Date();
    const list: { value: string; label: string }[] = [];
    for (let i = 0; i < 13; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      list.push({ value, label: `${d.getFullYear()}年${d.getMonth() + 1}月` });
    }
    return list;
  }, []);

  // 补充凭证
  const [supplementAssessmentId, setSupplementAssessmentId] = useState<number | null>(null);
  const [supplementRequest, setSupplementRequest] = useState<SupplementRequest | null>(null);

  // 发起异议
  const [appealOpen, setAppealOpen] = useState(false);
  const [appealTarget, setAppealTarget] = useState<AssessmentListItem | null>(null);
  const [appealReason, setAppealReason] = useState('');
  const [appealing, setAppealing] = useState(false);
  const [form] = Form.useForm();

  const fetchData = async (p = page, ps = pageSize, kw = keyword, st = statusFilter, mo = monthFilter) => {
    setLoading(true);
    try {
      const res = await assessmentApi.myAssessments({
        page: p,
        page_size: ps,
        keyword: kw || undefined,
        status: st,
        month: mo,
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
          {record.status === 'appeal_period' && (
            <Button
              type="primary"
              danger
              size="small"
              icon={<ExclamationCircleOutlined />}
              onClick={() => {
                setAppealTarget(record);
                setAppealReason('');
                form.resetFields();
                setAppealOpen(true);
              }}
            >
              发起异议
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
            onChange={(v) => { setStatusFilter(v); setPage(1); fetchData(1, pageSize, keyword, v, monthFilter); }}
            options={Object.entries(ASSESSMENT_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
          />
          <Select
            placeholder="月份筛选（按发起时间）"
            allowClear
            style={{ width: 190 }}
            value={monthFilter}
            onChange={(v) => { setMonthFilter(v); setPage(1); fetchData(1, pageSize, keyword, statusFilter, v); }}
            options={monthOptions}
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

      <Modal
        title="发起异议"
        open={appealOpen}
        onCancel={() => setAppealOpen(false)}
        confirmLoading={appealing}
        okText="提交异议"
        okButtonProps={{ danger: true }}
        onOk={async () => {
          if (!appealTarget) return;
          try {
            await form.validateFields();
          } catch {
            return;
          }
          setAppealing(true);
          try {
            await assessmentApi.submitAppeal(appealTarget.id, { reason: appealReason });
            message.success('异议已提交');
            setAppealOpen(false);
            fetchData();
          } catch (e: any) {
            message.error(e?.response?.data?.detail || '提交失败');
          } finally {
            setAppealing(false);
          }
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="reason"
            label="异议理由"
            rules={[{ required: true, message: '请填写异议理由' }]}
          >
            <Input.TextArea
              rows={4}
              value={appealReason}
              onChange={(e) => setAppealReason(e.target.value)}
              placeholder="请详细说明异议理由..."
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default MyAssessmentsPage;
