import React, { useEffect, useState } from 'react';
import { Table, Button, Input, Select, Space, Tag, Typography, message, Modal, Form, Pagination, Empty, Spin } from 'antd';
import { ReloadOutlined, UploadOutlined, ExclamationCircleOutlined, CheckOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { ColumnsType } from 'antd/es/table';
import { ASSESSMENT_STATUS_LABELS, ASSESSMENT_STATUS_COLORS } from '../types';
import type { AssessmentListItem, SupplementRequest, ErrorBonusItem } from '../types';
import { assessmentApi } from '../services/api';
import { useIsMobile } from '../hooks/useIsMobile';
import SupplementSubmitModal from '../components/assessment/SupplementSubmitModal';

const { Text, Paragraph } = Typography;

/**
 * 我的考核：我主办或我参与的考核列表，含状态、考核总分与我的得分；
 * 异议期内可发起异议或确认无异议；「待补充凭证」时可直接提交补充凭证。
 */
const MyAssessmentsPage: React.FC = () => {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [items, setItems] = useState<AssessmentListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [monthFilter, setMonthFilter] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  // 考核指错得分（PRD 6.7.2：监察主任/集团总监独判命中总裁裁定 +1）
  const [errorBonus, setErrorBonus] = useState<{ summary: { tentative: number; confirmed: number; retracted: number; total: number }; items: ErrorBonusItem[] } | null>(null);
  const [bonusModalOpen, setBonusModalOpen] = useState(false);

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
  const [noObjectionLoadingId, setNoObjectionLoadingId] = useState<number | null>(null);
  const [form] = Form.useForm();

  // 确认无异议
  const handleNoObjection = async (record: AssessmentListItem) => {
    Modal.confirm({
      title: '确认没有异议？',
      content: '确认后本考核项将视为您无异议。若全体人员均确认无异议，考核将跳过AI审查与裁定直接完结（已裁定）。',
      okText: '确认无异议',
      cancelText: '再想想',
      onOk: async () => {
        setNoObjectionLoadingId(record.id);
        try {
          const res = await assessmentApi.confirmNoObjection(record.id);
          message.success(res?.data?.message || '已确认无异议');
          fetchData();
        } catch (e: any) {
          message.error(e?.response?.data?.detail || '操作失败');
        } finally {
          setNoObjectionLoadingId(null);
        }
      },
    });
  };

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
    // 指错得分（有记录才显示入口）
    try {
      const bonus = await assessmentApi.myErrorBonuses({ month: mo });
      setErrorBonus(bonus && (bonus.summary.tentative + bonus.summary.confirmed + bonus.summary.retracted) > 0 ? bonus : null);
    } catch { /* 未配置或无权限时静默 */ }
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
      title: '身份',
      key: 'identity',
      width: 80,
      render: (_, record) => (
        record.is_sponsor ? <Tag color="blue">主办</Tag> : <Tag color="green">参与</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 150,
      render: (v: string) => <Tag color={ASSESSMENT_STATUS_COLORS[v]}>{ASSESSMENT_STATUS_LABELS[v] || v}</Tag>,
    },
    {
      title: '考核总分',
      dataIndex: 'final_score',
      key: 'final_score',
      width: 95,
      render: (v) => (v !== null && v !== undefined ? <Text type="secondary">{v}</Text> : '-'),
    },
    {
      title: '我的得分',
      dataIndex: 'my_score',
      key: 'my_score',
      width: 95,
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
      width: 230,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/assessment/${record.id}`)}>详情</Button>
          {record.status === 'pending_supplement' && (
            <Button type="primary" size="small" icon={<UploadOutlined />} onClick={() => handleOpenSupplement(record)}>
              提交补充凭证
            </Button>
          )}
          {record.can_appeal && (
            <>
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
              {record.no_objection_confirmed ? (
                <Tag color="success">已确认无异议</Tag>
              ) : (
                <Button
                  size="small"
                  icon={<CheckOutlined />}
                  onClick={() => handleNoObjection(record)}
                  loading={noObjectionLoadingId === record.id}
                >
                  没有异议
                </Button>
              )}
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space direction={isMobile ? 'vertical' : 'horizontal'} style={{ marginBottom: isMobile ? 8 : 16, width: '100%', justifyContent: 'space-between' }}>
        <Space wrap size={isMobile ? 8 : 'middle'}>
          <Input.Search
            placeholder="搜索工作项标题"
            allowClear
            style={{ width: isMobile ? '100%' : 260 }}
            onSearch={(kw) => { setKeyword(kw); setPage(1); fetchData(1, pageSize, kw, statusFilter); }}
          />
          <Select
            placeholder="状态筛选"
            allowClear
            style={{ width: isMobile ? 'calc(50% - 4px)' : 180 }}
            value={statusFilter}
            onChange={(v) => { setStatusFilter(v); setPage(1); fetchData(1, pageSize, keyword, v, monthFilter); }}
            options={Object.entries(ASSESSMENT_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
          />
          <Select
            placeholder="月份筛选（按发起时间）"
            allowClear
            style={{ width: isMobile ? 'calc(50% - 4px)' : 190 }}
            value={monthFilter}
            onChange={(v) => { setMonthFilter(v); setPage(1); fetchData(1, pageSize, keyword, statusFilter, v); }}
            options={monthOptions}
          />
          {errorBonus && (
            <Button icon={<ExclamationCircleOutlined />} onClick={() => setBonusModalOpen(true)}>
              考核指错得分：+{errorBonus.summary.total}
              {errorBonus.summary.tentative > 0 && `（暂计${errorBonus.summary.tentative}）`}
            </Button>
          )}
          <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
        </Space>
        {!isMobile && <Text type="secondary">我主办或我参与的考核记录</Text>}
      </Space>

      {isMobile ? (
        loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : items.length === 0 ? (
          <Empty description="暂无考核记录" style={{ padding: 32 }} />
        ) : (
          <div>
            {items.map((it) => (
              <div key={it.id} className="m-card" onClick={() => navigate(`/assessment/${it.id}`)}>
                <div className="m-card-title">{it.work_item_title || `考核 #${it.id}`}</div>
                <div className="m-card-meta">
                  <Tag color={ASSESSMENT_STATUS_COLORS[it.status]} style={{ margin: 0 }}>
                    {ASSESSMENT_STATUS_LABELS[it.status] || it.status}
                  </Tag>
                  {it.is_sponsor ? <Tag color="blue" style={{ margin: 0 }}>主办</Tag> : <Tag color="green" style={{ margin: 0 }}>参与</Tag>}
                  {it.no_objection_confirmed && <Tag color="success" style={{ margin: 0 }}>已确认无异议</Tag>}
                  <span>{it.department_name || '-'} · {it.district_name || '-'}</span>
                  <span>
                    总分：
                    {it.final_score !== null && it.final_score !== undefined ? it.final_score : '-'}
                    ｜我的得分：
                    <span style={{ color: '#1677ff', fontWeight: 600 }}>
                      {it.my_score !== null && it.my_score !== undefined ? it.my_score : '-'}
                    </span>
                  </span>
                  {it.initiated_at && <span>{new Date(it.initiated_at).toLocaleString('zh-CN', { hour12: false })}</span>}
                </div>
                <div className="m-card-actions" onClick={(e) => e.stopPropagation()}>
                  <Button size="small" onClick={() => navigate(`/assessment/${it.id}`)}>详情</Button>
                  {it.status === 'pending_supplement' && (
                    <Button type="primary" size="small" icon={<UploadOutlined />} onClick={() => handleOpenSupplement(it)}>
                      补充凭证
                    </Button>
                  )}
                  {it.can_appeal && !it.no_objection_confirmed && (
                    <Button
                      type="primary"
                      danger
                      size="small"
                      icon={<ExclamationCircleOutlined />}
                      onClick={() => {
                        setAppealTarget(it);
                        setAppealReason('');
                        form.resetFields();
                        setAppealOpen(true);
                      }}
                    >
                      异议
                    </Button>
                  )}
                  {it.can_appeal && !it.no_objection_confirmed && (
                    <Button
                      size="small"
                      icon={<CheckOutlined />}
                      onClick={() => handleNoObjection(it)}
                      loading={noObjectionLoadingId === it.id}
                    >
                      无异议
                    </Button>
                  )}
                </div>
              </div>
            ))}
            {total > pageSize && (
              <Pagination
                style={{ textAlign: 'center', marginTop: 12 }}
                simple
                current={page}
                pageSize={pageSize}
                total={total}
                onChange={(p, ps) => { setPage(p); setPageSize(ps); fetchData(p, ps); }}
              />
            )}
          </div>
        )
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

      <Modal
        title="考核指错得分"
        open={bonusModalOpen}
        onCancel={() => setBonusModalOpen(false)}
        footer={null}
        width={860}
      >
        {errorBonus && (
          <>
            <Space style={{ marginBottom: 12 }}>
              <Tag color="green">已证实 +{errorBonus.summary.confirmed}</Tag>
              <Tag color="orange">暂计 +{errorBonus.summary.tentative}（总裁裁定后结算）</Tag>
              <Tag>已扣回 {errorBonus.summary.retracted}</Tag>
              <Text strong>合计 +{errorBonus.summary.total}</Text>
            </Space>
            <Table
              size="small"
              rowKey="id"
              dataSource={errorBonus.items}
              pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
              columns={[
                { title: '工作项', dataIndex: 'title', key: 'title', ellipsis: true },
                { title: '评分环节', dataIndex: 'level_name', key: 'level_name', width: 110 },
                { title: '我的评分', dataIndex: 'score', key: 'score', width: 80 },
                { title: '上一环节', dataIndex: 'prev_score', key: 'prev_score', width: 80, render: (v) => v ?? '-' },
                { title: '裁定分', dataIndex: 'ruling_score', key: 'ruling_score', width: 80, render: (v) => v ?? '待裁定' },
                {
                  title: '状态', dataIndex: 'status_name', key: 'status_name', width: 80,
                  render: (v, r: ErrorBonusItem) => (
                    <Tag color={r.bonus_status === 'confirmed' ? 'green' : r.bonus_status === 'tentative' ? 'orange' : 'default'}>{v}</Tag>
                  ),
                },
                {
                  title: '发生时间', dataIndex: 'created_at', key: 'created_at', width: 150,
                  render: (v) => (v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '-'),
                },
              ]}
            />
            <Paragraph type="secondary" style={{ marginTop: 8, fontSize: 12, marginBottom: 0 }}>
              规则：打分与上一环节不同、且与总裁最终裁定相同的，每项 +1。提交时暂计，总裁裁定后自动结算；无异议完结项以集团总监评分为裁定分。
            </Paragraph>
          </>
        )}
      </Modal>
    </div>
  );
};

export default MyAssessmentsPage;
