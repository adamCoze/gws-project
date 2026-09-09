import React, { useEffect, useState } from 'react';
import { Table, Button, Space, Tag, Tabs, Modal, Input, Typography, message } from 'antd';
import { CheckOutlined, CloseOutlined, EditOutlined, FileSearchOutlined, ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { ColumnsType } from 'antd/es/table';
import { ASSESSMENT_STATUS_LABELS, ASSESSMENT_STATUS_COLORS, SCORE_LEVEL_LABELS } from '../types';
import type { AssessmentListItem } from '../types';
import { assessmentApi } from '../services/api';
import ScoreModal from '../components/assessment/ScoreModal';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

/**
 * 待我处理：
 * - 待确认 tab（部门总监）：确认/驳回考核
 * - 待评分 tab（区总/监察主任/集团总监）：评分、要求补充凭证
 */
const AssessmentTodoPage: React.FC = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'confirm' | 'score'>('confirm');

  const [confirmItems, setConfirmItems] = useState<AssessmentListItem[]>([]);
  const [confirmTotal, setConfirmTotal] = useState(0);
  const [scoreItems, setScoreItems] = useState<AssessmentListItem[]>([]);
  const [scoreTotal, setScoreTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);

  // 驳回弹窗
  const [rejectTarget, setRejectTarget] = useState<AssessmentListItem | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [rejecting, setRejecting] = useState(false);

  // 评分弹窗
  const [scoreTarget, setScoreTarget] = useState<AssessmentListItem | null>(null);

  // 补充凭证请求弹窗
  const [supplementTarget, setSupplementTarget] = useState<AssessmentListItem | null>(null);
  const [supplementNote, setSupplementNote] = useState('');
  const [requestingSupplement, setRequestingSupplement] = useState(false);

  const fetchConfirm = async (p = 1, ps = pageSize) => {
    setLoading(true);
    try {
      const res = await assessmentApi.toConfirm({ page: p, page_size: ps });
      setConfirmItems(res.items);
      setConfirmTotal(res.total);
    } catch {
      setConfirmItems([]);
      setConfirmTotal(0);
    } finally {
      setLoading(false);
    }
  };

  const fetchScore = async (p = 1, ps = pageSize) => {
    setLoading(true);
    try {
      const res = await assessmentApi.toScore({ page: p, page_size: ps });
      setScoreItems(res.items);
      setScoreTotal(res.total);
    } catch {
      setScoreItems([]);
      setScoreTotal(0);
    } finally {
      setLoading(false);
    }
  };

  const refresh = () => {
    if (activeTab === 'confirm') fetchConfirm(page, pageSize);
    else fetchScore(page, pageSize);
  };

  useEffect(() => {
    setPage(1);
    if (activeTab === 'confirm') fetchConfirm(1, pageSize);
    else fetchScore(1, pageSize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const handleConfirm = async (record: AssessmentListItem) => {
    try {
      await assessmentApi.deptConfirm(record.id);
      message.success('已确认');
      fetchConfirm(page, pageSize);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '确认失败');
    }
  };

  const handleReject = async () => {
    if (!rejectTarget) return;
    setRejecting(true);
    try {
      await assessmentApi.deptReject(rejectTarget.id, rejectReason.trim() || undefined);
      message.success('已驳回');
      setRejectTarget(null);
      setRejectReason('');
      fetchConfirm(page, pageSize);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '驳回失败');
    } finally {
      setRejecting(false);
    }
  };

  const handleRequestSupplement = async () => {
    if (!supplementTarget) return;
    if (!supplementNote.trim()) {
      message.warning('请填写补充说明要求');
      return;
    }
    setRequestingSupplement(true);
    try {
      await assessmentApi.requestSupplement(supplementTarget.id, supplementNote.trim());
      message.success('已发起补充凭证请求');
      setSupplementTarget(null);
      setSupplementNote('');
      fetchScore(page, pageSize);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '发起失败');
    } finally {
      setRequestingSupplement(false);
    }
  };

  const baseColumns: ColumnsType<AssessmentListItem> = [
    {
      title: '工作项',
      dataIndex: 'work_item_title',
      key: 'work_item_title',
      render: (v, record) => (
        <a onClick={() => navigate(`/assessment/${record.id}`)}>{v || `考核 #${record.id}`}</a>
      ),
    },
    { title: '部门', dataIndex: 'department_name', key: 'department_name', width: 130, render: (v) => v || '-' },
    { title: '区域', dataIndex: 'district_name', key: 'district_name', width: 110, render: (v) => v || '-' },
    { title: '责任人', dataIndex: 'sponsor_name', key: 'sponsor_name', width: 110, render: (v) => v || '-' },
    { title: '发起人', dataIndex: 'initiator_name', key: 'initiator_name', width: 110, render: (v) => v || '-' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 140,
      render: (v: string) => <Tag color={ASSESSMENT_STATUS_COLORS[v]}>{ASSESSMENT_STATUS_LABELS[v] || v}</Tag>,
    },
    {
      title: '发起时间',
      dataIndex: 'initiated_at',
      key: 'initiated_at',
      width: 160,
      render: (v) => (v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '-'),
    },
  ];

  const confirmColumns: ColumnsType<AssessmentListItem> = [
    ...baseColumns,
    {
      title: '操作',
      key: 'actions',
      width: 170,
      render: (_, record) => (
        <Space>
          <Button type="primary" size="small" icon={<CheckOutlined />} onClick={() => handleConfirm(record)}>
            确认
          </Button>
          <Button danger size="small" icon={<CloseOutlined />} onClick={() => { setRejectTarget(record); setRejectReason(''); }}>
            驳回
          </Button>
        </Space>
      ),
    },
  ];

  const scoreColumns: ColumnsType<AssessmentListItem> = [
    ...baseColumns.slice(0, 5),
    {
      title: '当前层级',
      dataIndex: 'current_level',
      key: 'current_level',
      width: 130,
      render: (v: string) => (v ? <Tag color="processing">{SCORE_LEVEL_LABELS[v] || v}</Tag> : '-'),
    },
    ...baseColumns.slice(5),
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_, record) => (
        <Space>
          <Button type="primary" size="small" icon={<EditOutlined />} onClick={() => setScoreTarget(record)}>
            评分
          </Button>
          <Button size="small" icon={<FileSearchOutlined />} onClick={() => { setSupplementTarget(record); setSupplementNote(''); }}>
            要求补充凭证
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Text strong style={{ fontSize: 16 }}>待我处理</Text>
        <Button icon={<ReloadOutlined />} onClick={refresh}>刷新</Button>
      </Space>

      <Tabs
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as 'confirm' | 'score')}
        items={[
          {
            key: 'confirm',
            label: `待确认（${confirmTotal}）`,
            children: (
              <Table
                rowKey="id"
                columns={confirmColumns}
                dataSource={confirmItems}
                loading={loading}
                pagination={{
                  current: page,
                  pageSize,
                  total: confirmTotal,
                  showSizeChanger: true,
                  showTotal: (t) => `共 ${t} 条`,
                  onChange: (p, ps) => { setPage(p); setPageSize(ps); fetchConfirm(p, ps); },
                }}
              />
            ),
          },
          {
            key: 'score',
            label: `待评分（${scoreTotal}）`,
            children: (
              <Table
                rowKey="id"
                columns={scoreColumns}
                dataSource={scoreItems}
                loading={loading}
                pagination={{
                  current: page,
                  pageSize,
                  total: scoreTotal,
                  showSizeChanger: true,
                  showTotal: (t) => `共 ${t} 条`,
                  onChange: (p, ps) => { setPage(p); setPageSize(ps); fetchScore(p, ps); },
                }}
              />
            ),
          },
        ]}
      />

      {/* 评分弹窗 */}
      <ScoreModal
        open={!!scoreTarget}
        assessmentId={scoreTarget?.id ?? null}
        workItemTitle={scoreTarget?.work_item_title}
        levelLabel={scoreTarget?.current_level ? SCORE_LEVEL_LABELS[scoreTarget.current_level] : undefined}
        onCancel={() => setScoreTarget(null)}
        onSuccess={() => { setScoreTarget(null); fetchScore(page, pageSize); }}
      />

      {/* 驳回弹窗 */}
      <Modal
        title="驳回考核"
        open={!!rejectTarget}
        onCancel={() => setRejectTarget(null)}
        onOk={handleReject}
        confirmLoading={rejecting}
        okText="确认驳回"
        okButtonProps={{ danger: true }}
        cancelText="取消"
        destroyOnClose
      >
        <Paragraph>
          驳回工作项 <Text strong>{rejectTarget?.work_item_title}</Text> 的考核？
        </Paragraph>
        <TextArea
          rows={3}
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          placeholder="驳回原因（可选）"
          maxLength={500}
        />
      </Modal>

      {/* 要求补充凭证弹窗 */}
      <Modal
        title="要求补充凭证"
        open={!!supplementTarget}
        onCancel={() => setSupplementTarget(null)}
        onOk={handleRequestSupplement}
        confirmLoading={requestingSupplement}
        okText="发起请求"
        cancelText="取消"
        destroyOnClose
      >
        <Paragraph>
          要求责任人 <Text strong>{supplementTarget?.sponsor_name || ''}</Text> 为
          <Text strong> {supplementTarget?.work_item_title} </Text>
          补充凭证，考核将进入「待补充凭证」状态。
        </Paragraph>
        <TextArea
          rows={3}
          value={supplementNote}
          onChange={(e) => setSupplementNote(e.target.value)}
          placeholder="请说明需要补充的凭证内容（必填）"
          maxLength={500}
        />
      </Modal>
    </div>
  );
};

export default AssessmentTodoPage;
