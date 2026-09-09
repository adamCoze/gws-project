import React, { useEffect, useState } from 'react';
import { Table, Button, Input, Space, Tag, Modal, Typography, message, Tooltip } from 'antd';
import { PlayCircleOutlined, StopOutlined, MailOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { PendingAssessmentItem, SkipRuleInfo } from '../types';
import { assessmentApi } from '../services/api';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

/**
 * 待考核项目：已完成工作项中尚未发起考核、未标记非考核的清单
 * 操作：发起考核（展示跳过规则提示）、标记为非考核项
 */
const PendingAssessmentPage: React.FC = () => {
  const [items, setItems] = useState<PendingAssessmentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(false);

  // 发起考核确认弹窗
  const [initiateTarget, setInitiateTarget] = useState<PendingAssessmentItem | null>(null);
  const [skipRule, setSkipRule] = useState<SkipRuleInfo | null>(null);
  const [initiating, setInitiating] = useState(false);

  // 标记非考核弹窗
  const [markTarget, setMarkTarget] = useState<PendingAssessmentItem | null>(null);
  const [markRemark, setMarkRemark] = useState('');
  const [marking, setMarking] = useState(false);

  const fetchData = async (p = page, ps = pageSize, kw = keyword) => {
    setLoading(true);
    try {
      const res = await assessmentApi.pendingItems({ page: p, page_size: ps, keyword: kw || undefined });
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

  const handleInitiateClick = async (item: PendingAssessmentItem) => {
    setInitiateTarget(item);
    setSkipRule(null);
    try {
      const rule = await assessmentApi.checkSkipRule(item.work_item_id);
      setSkipRule(rule);
    } catch {
      // 跳过规则查询失败不阻塞，后端发起时仍会校验
    }
  };

  const handleInitiateConfirm = async () => {
    if (!initiateTarget) return;
    setInitiating(true);
    try {
      const res = await assessmentApi.initiate(initiateTarget.work_item_id);
      message.success(res.message || `已发起考核，当前状态：${res.status_text}`);
      setInitiateTarget(null);
      fetchData();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '发起考核失败');
    } finally {
      setInitiating(false);
    }
  };

  const handleMarkConfirm = async () => {
    if (!markTarget) return;
    setMarking(true);
    try {
      await assessmentApi.markNonAssessment(markTarget.work_item_id, markRemark.trim() || undefined);
      message.success('已标记为非考核项');
      setMarkTarget(null);
      setMarkRemark('');
      fetchData();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '标记失败');
    } finally {
      setMarking(false);
    }
  };

  const columns: ColumnsType<PendingAssessmentItem> = [
    {
      title: '工作项',
      dataIndex: 'title',
      key: 'title',
      render: (title: string, record) => (
        <Space>
          <Text strong>{title}</Text>
          {record.has_email && (
            <Tooltip title="关联邮件">
              {record.email_url ? (
                <a href={record.email_url} target="_blank" rel="noreferrer"><MailOutlined /></a>
              ) : (
                <MailOutlined style={{ color: '#1677ff' }} />
              )}
            </Tooltip>
          )}
        </Space>
      ),
    },
    { title: '部门', dataIndex: 'department_name', key: 'department_name', width: 140, render: (v) => v || '-' },
    { title: '区域', dataIndex: 'district_name', key: 'district_name', width: 120, render: (v) => v || '-' },
    { title: '责任人', dataIndex: 'sponsor_name', key: 'sponsor_name', width: 120, render: (v) => v || '-' },
    {
      title: '完成时间',
      dataIndex: 'completed_at',
      key: 'completed_at',
      width: 170,
      render: (v) => (v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_, record) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<PlayCircleOutlined />}
            onClick={() => handleInitiateClick(record)}
          >
            发起考核
          </Button>
          <Button size="small" icon={<StopOutlined />} onClick={() => { setMarkTarget(record); setMarkRemark(''); }}>
            标记非考核
          </Button>
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
            style={{ width: 280 }}
            onSearch={(kw) => { setKeyword(kw); setPage(1); fetchData(1, pageSize, kw); }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
        </Space>
        <Text type="secondary">已完成且待处理的工作项，可发起考核或标记为非考核项</Text>
      </Space>

      <Table
        rowKey="work_item_id"
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

      {/* 发起考核确认弹窗（含跳过规则提示） */}
      <Modal
        title="发起考核"
        open={!!initiateTarget}
        onCancel={() => setInitiateTarget(null)}
        onOk={handleInitiateConfirm}
        confirmLoading={initiating}
        okText="确认发起"
        cancelText="取消"
        destroyOnClose
      >
        <Paragraph>
          确认为工作项 <Text strong>{initiateTarget?.title}</Text> 发起考核？
        </Paragraph>
        {skipRule && (
          <div style={{ background: '#f6f6f6', padding: 12, borderRadius: 6 }}>
            <Paragraph style={{ marginBottom: 4 }}>
              发起后初始状态：<Tag color="blue">{skipRule.initial_status}</Tag>
            </Paragraph>
            {(skipRule.skip_dept_confirm || skipRule.skip_district_score || skipRule.skip_regulator_score) && (
              <Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 12 }}>
                按跳过规则：
                {skipRule.skip_dept_confirm && ' 跳过部门总监确认；'}
                {skipRule.skip_district_score && ' 跳过区总评分；'}
                {skipRule.skip_regulator_score && ' 跳过监察主任评分；'}
                {skipRule.reason && `（${skipRule.reason}）`}
              </Paragraph>
            )}
          </div>
        )}
      </Modal>

      {/* 标记非考核弹窗 */}
      <Modal
        title="标记为非考核项"
        open={!!markTarget}
        onCancel={() => setMarkTarget(null)}
        onOk={handleMarkConfirm}
        confirmLoading={marking}
        okText="确认标记"
        cancelText="取消"
        destroyOnClose
      >
        <Paragraph>
          将工作项 <Text strong>{markTarget?.title}</Text> 标记为非考核项？标记后可在「非考核项」页面撤销。
        </Paragraph>
        <TextArea
          rows={3}
          value={markRemark}
          onChange={(e) => setMarkRemark(e.target.value)}
          placeholder="备注（可选）"
          maxLength={500}
        />
      </Modal>
    </div>
  );
};

export default PendingAssessmentPage;
