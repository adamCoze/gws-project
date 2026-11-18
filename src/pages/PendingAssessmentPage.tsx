import React, { useEffect, useState } from 'react';
import { Table, Button, Input, Space, Tag, Modal, Typography, message, Tooltip, Select, Spin } from 'antd';
import { PlayCircleOutlined, StopOutlined, MailOutlined, ReloadOutlined, EditOutlined } from '@ant-design/icons';
import WorkItemEditModal from '../components/WorkItemEditModal';
import type { WorkItem } from '../types';
import { workItemApi, userApi } from '../services/api';
import type { ColumnsType } from 'antd/es/table';
import type { PendingAssessmentItem, SkipRuleInfo, SponsorRoleOption } from '../types';
import { ASSESSMENT_STATUS_LABELS, ROLE_LEVEL_LABELS } from '../types';
import { assessmentApi, departmentApi, districtApi } from '../services/api';
import { useAuth } from '../components/AuthProvider';

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
  const [sponsorFilter, setSponsorFilter] = useState<number | undefined>(undefined);
  const [districtFilter, setDistrictFilter] = useState<number | undefined>(undefined);
  const [districts, setDistricts] = useState<{ id: number; name: string }[]>([]);
  const isMobile = useIsMobile();
  const [users, setUsers] = useState<{ id: number; real_name: string; username: string }[]>([]);
  const [editTarget, setEditTarget] = useState<WorkItem | null>(null);

  // 发起考核确认弹窗
  const [initiateTarget, setInitiateTarget] = useState<PendingAssessmentItem | null>(null);
  const [skipRule, setSkipRule] = useState<SkipRuleInfo | null>(null);
  const [initiating, setInitiating] = useState(false);
  // 发起角色选择（仅主办人本人发起且有副角色时出现）
  const { user } = useAuth();
  const [roleOptions, setRoleOptions] = useState<SponsorRoleOption[]>([]);
  const [selectedRoleIndex, setSelectedRoleIndex] = useState<number | null>(null);
  const [roleRuleLoading, setRoleRuleLoading] = useState(false);
  const [nameMaps, setNameMaps] = useState<{ dept: Record<number, string>; dist: Record<number, string> }>({ dept: {}, dist: {} });

  useEffect(() => {
    (async () => {
      try {
        const [depts, dists] = await Promise.all([
          departmentApi.list().catch(() => []),
          districtApi.list().catch(() => []),
        ]);
        setNameMaps({
          dept: Object.fromEntries((depts as any[]).map((d) => [d.id, d.name])),
          dist: Object.fromEntries((dists as any[]).map((d) => [d.id, d.name])),
        });
      } catch {
        // 名称映射失败不阻塞，选项退化为仅显示角色名
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const buildRoleOptions = (deptMap: Record<number, string>, distMap: Record<number, string>): SponsorRoleOption[] => {
    if (!user) return [];
    const locName = (id?: number | null) => (id != null ? deptMap[id] || distMap[id] || '' : '');
    const primaryLabel = [ROLE_LEVEL_LABELS[user.role_level] || `等级${user.role_level}`, locName(user.department_id) || locName(user.district_id)].filter(Boolean).join(' · ');
    const options: SponsorRoleOption[] = [{ index: null, label: `${primaryLabel}（主角色）`, level: user.role_level, department_id: user.department_id, district_id: user.district_id }];
    (user.secondary_roles || []).forEach((sr, i) => {
      const label = [ROLE_LEVEL_LABELS[sr.role_level] || `等级${sr.role_level}`, locName(sr.department_id) || locName(sr.district_id)].filter(Boolean).join(' · ');
      options.push({ index: i, label, level: sr.role_level, department_id: sr.department_id, district_id: sr.district_id });
    });
    return options;
  };

  // 标记非考核弹窗
  const [markTarget, setMarkTarget] = useState<PendingAssessmentItem | null>(null);
  const [markRemark, setMarkRemark] = useState('');
  const [marking, setMarking] = useState(false);

  const fetchData = async (
    p = page,
    ps = pageSize,
    kw = keyword,
    sp: number | undefined = sponsorFilter,
    dt: number | undefined = districtFilter,
  ) => {
    if (sp !== undefined) setSponsorFilter(sp);
    setLoading(true);
    try {
      const res = await assessmentApi.pendingItems({ page: p, page_size: ps, keyword: kw || undefined, sponsor_id: sp, district_id: dt });
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
    userApi.listBrief().then((u) => setUsers(u)).catch(() => { /* 忽略 */ });
    districtApi.list().then((d) => setDistricts(d as unknown as { id: number; name: string }[])).catch(() => { /* 忽略 */ });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleTitleClick = async (record: PendingAssessmentItem) => {
    try {
      const wi = await workItemApi.get(record.work_item_id) as unknown as WorkItem;
      setEditTarget(wi);
    } catch {
      message.error('获取工作项详情失败');
    }
  };

  const handleInitiateClick = async (item: PendingAssessmentItem) => {
    setInitiateTarget(item);
    setSkipRule(null);
    // 仅主办人本人发起且配置了副角色时，提供发起角色选择
    const selfInitiate = user && item.sponsor_id === user.id;
    const options = selfInitiate ? buildRoleOptions(nameMaps.dept, nameMaps.dist) : [];
    const selectable = options.length > 1;
    setRoleOptions(selectable ? options : []);
    setSelectedRoleIndex(null);
    try {
      const rule = await assessmentApi.checkSkipRule(item.work_item_id);
      setSkipRule(rule);
    } catch {
      // 跳过规则查询失败不阻塞，后端发起时仍会校验
    }
  };

  // 切换发起角色：按所选角色重新预览跳过规则
  const handleRoleChange = async (index: number | null) => {
    if (!initiateTarget) return;
    setSelectedRoleIndex(index);
    setRoleRuleLoading(true);
    try {
      const rule = await assessmentApi.checkSkipRule(initiateTarget.work_item_id, index);
      setSkipRule(rule);
    } catch {
      // 查询失败不阻塞，后端发起时仍会校验
    } finally {
      setRoleRuleLoading(false);
    }
  };

  const handleInitiateConfirm = async () => {
    if (!initiateTarget) return;
    setInitiating(true);
    try {
      const res = await assessmentApi.initiate(initiateTarget.work_item_id, selectedRoleIndex);
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
          <Text strong style={{ cursor: 'pointer' }} onClick={() => handleTitleClick(record)}>{title}</Text>
          <Tooltip title="编辑工作项">
            <EditOutlined style={{ color: '#1677ff', cursor: 'pointer' }} onClick={() => handleTitleClick(record)} />
          </Tooltip>
          {record.has_email && (
            <Tooltip title={record.email_url ? '打开关联邮件' : '暂无邮件链接'}>
              {record.email_url ? (
                <a href={record.email_url} target="_blank" rel="noreferrer"><MailOutlined /></a>
              ) : (
                <MailOutlined style={{ color: '#d9d9d9', cursor: 'not-allowed' }} />
              )}
            </Tooltip>
          )}
        </Space>
      ),
    },
    { title: '部门', dataIndex: 'department_name', key: 'department_name', width: 140, render: (v) => v || '-' },
    { title: '区域', dataIndex: 'district_name', key: 'district_name', width: 120, render: (v) => v || '-' },
    {
      title: '主办人', dataIndex: 'sponsor_name', key: 'sponsor_name', width: 130,
      render: (v) => v || <Tag color="orange">无主办人</Tag>,
    },
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
      <Space direction={isMobile ? 'vertical' : 'horizontal'} style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space direction={isMobile ? 'vertical' : 'horizontal'} style={isMobile ? { width: '100%' } : undefined}>
          <Input.Search
            placeholder="搜索工作项标题"
            allowClear
            style={{ width: isMobile ? '100%' : 280 }}
            onSearch={(kw) => { setKeyword(kw); setPage(1); fetchData(1, pageSize, kw); }}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="按主办人筛选"
            style={{ width: isMobile ? '100%' : 180 }}
            value={sponsorFilter}
            onChange={(v) => { setSponsorFilter(v); setPage(1); fetchData(1, pageSize, keyword, v); }}
            options={users.map((u) => ({ value: u.id, label: u.real_name || u.username }))}
          />
          <Select
            allowClear
            placeholder="按区域筛选"
            style={{ width: isMobile ? '100%' : 130 }}
            value={districtFilter}
            onChange={(v) => { setDistrictFilter(v); setPage(1); fetchData(1, pageSize, keyword, sponsorFilter, v); }}
            options={districts.map((d) => ({ value: d.id, label: d.name }))}
          />
          <Button style={isMobile ? { width: '100%' } : undefined} icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
        </Space>
        {!isMobile && <Text type="secondary">已完成且待处理的工作项，可发起考核或标记为非考核项</Text>}
      </Space>

      {isMobile ? (
        <MobileCardList
          items={items}
          rowKey={(r) => r.work_item_id}
          loading={loading}
          emptyText="暂无待考核工作项"
          serverSide
          total={total}
          page={page}
          pageSize={pageSize}
          onPageChange={(p, ps) => { setPage(p); setPageSize(ps); fetchData(p, ps); }}
          renderCard={(r: PendingAssessmentItem) => (
            <>
              <div className="m-card-title">{r.work_item_title || `工作项 #${r.work_item_id}`}</div>
              <div className="m-card-meta">
                <span>{r.department_name || '-'} · {r.district_name || '-'}</span>
                <span>主办人：{r.sponsor_name || '无主办人'}</span>
                {r.completed_at && <span>完成：{new Date(r.completed_at).toLocaleString('zh-CN', { hour12: false })}</span>}
              </div>
              <div className="m-card-actions">
                <Button type="primary" size="small" icon={<PlayCircleOutlined />} onClick={() => handleInitiateClick(r)}>发起考核</Button>
                <Button size="small" icon={<StopOutlined />} onClick={() => { setMarkTarget(r); setMarkRemark(''); }}>标记非考核</Button>
              </div>
            </>
          )}
        />
      ) : (
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
      )}

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
        {roleOptions.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <Paragraph style={{ marginBottom: 4 }}>
              发起角色：<Text type="secondary" style={{ fontSize: 12 }}>你有多重角色，请选择以哪个角色发起，考核将按所选角色的流程推进</Text>
            </Paragraph>
            <Select
              style={{ width: '100%' }}
              value={selectedRoleIndex === null ? 'primary' : String(selectedRoleIndex)}
              onChange={(v) => handleRoleChange(v === 'primary' ? null : Number(v))}
              options={roleOptions.map((o) => ({ value: o.index === null ? 'primary' : String(o.index), label: o.label }))}
            />
          </div>
        )}
        <Spin size="small" spinning={roleRuleLoading}>
        {skipRule && (
          <div style={{ background: '#f6f6f6', padding: 12, borderRadius: 6 }}>
            <Paragraph style={{ marginBottom: 4 }}>
              发起后初始状态：<Tag color="blue">{ASSESSMENT_STATUS_LABELS[skipRule.initial_status] || skipRule.initial_status}</Tag>
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
        </Spin>
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
          <WorkItemEditModal
        open={!!editTarget}
        item={editTarget}
        onCancel={() => setEditTarget(null)}
        onSaved={() => { setEditTarget(null); fetchData(); }}
      />
</div>
  );
};

export default PendingAssessmentPage;
