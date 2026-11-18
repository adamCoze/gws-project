import React, { useState, useEffect } from 'react';
import { Table, Button, Select, Space, Card, Row, Col, Input, DatePicker, Tag, message, Modal } from 'antd';
import { ExportOutlined, SearchOutlined, BarChartOutlined } from '@ant-design/icons';
import { assessmentApi, districtApi, departmentApi, userApi } from '../../services/api';
import { ASSESSMENT_STATUS_LABELS, ASSESSMENT_STATUS_COLORS } from '../../types';
import type { District, Department } from '../../types';
import dayjs from 'dayjs';
import { useNavigate } from 'react-router-dom';
import { useIsMobile } from '../../hooks/useIsMobile';
import MobileCardList from '../../components/MobileCardList';

const { RangePicker } = DatePicker;

const AssessmentManagementPage: React.FC = () => {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [districts, setDistricts] = useState<District[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [users, setUsers] = useState<Array<{ id: number; real_name: string; username: string }>>([]);

  // 筛选条件
  const [month, setMonth] = useState<string | undefined>(undefined);
  const [status, setStatus] = useState<string | undefined>(undefined);
  const [districtId, setDistrictId] = useState<number | undefined>(undefined);
  const [departmentId, setDepartmentId] = useState<number | undefined>(undefined);
  const [keyword, setKeyword] = useState<string>('');
  const [scorerId, setScorerId] = useState<number | undefined>(undefined);

  // 按得分人统计
  const [statsOpen, setStatsOpen] = useState(false);
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsItems, setStatsItems] = useState<any[]>([]);
  const [statsScorerId, setStatsScorerId] = useState<number | undefined>(undefined);

  // 得分导出：月份必选弹窗
  const [exportOpen, setExportOpen] = useState(false);
  const [exportMonth, setExportMonth] = useState<string | undefined>(undefined);
  const [exporting, setExporting] = useState(false);

  // 取区域和部门列表
  useEffect(() => {
    const fetchMeta = async () => {
      try {
        const [dRes, deptRes] = await Promise.all([
          districtApi.list(),
          departmentApi.list(),
        ]);
        setDistricts(Array.isArray(dRes) ? dRes : (dRes as any).items || []);
        setDepartments(Array.isArray(deptRes) ? deptRes : (deptRes as any).items || []);
      } catch (e) {
        console.error('加载基础数据失败', e);
      }
      userApi.listBrief().then((u) => setUsers(u)).catch(() => { /* 忽略 */ });
    };
    fetchMeta();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await assessmentApi.adminAll({
        page,
        page_size: pageSize,
        month,
        status,
        district_id: districtId,
        department_id: departmentId,
        keyword: keyword || undefined,
        scorer_id: scorerId,
      });
      setItems(res.items || []);
      setTotal(res.total || 0);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize]);

  const handleSearch = () => {
    setPage(1);
    setTimeout(fetchData, 0);
  };

  const handleReset = () => {
    setMonth(undefined);
    setStatus(undefined);
    setDistrictId(undefined);
    setDepartmentId(undefined);
    setKeyword('');
    setScorerId(undefined);
    setPage(1);
    setTimeout(fetchData, 0);
  };

  const handleExport = () => {
    const url = assessmentApi.adminExportUrl({
      month,
      status,
      district_id: districtId,
      department_id: departmentId,
      keyword: keyword || undefined,
    });
    // token 在 axios 拦截器里加，直接 window.open 可能不带 token
    // 改用 fetch 下载
    const token = localStorage.getItem('token');
    fetch(url, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    })
      .then((res) => {
        if (!res.ok) throw new Error('导出失败');
        return res.blob();
      })
      .then((blob) => {
        const a = document.createElement('a');
        const objectUrl = URL.createObjectURL(blob);
        a.href = objectUrl;
        // 从响应头拿文件名
        a.download = `考核项目_${month || '全部'}_${dayjs().format('YYYYMMDD')}.xlsx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(objectUrl);
        message.success('导出成功');
      })
      .catch((err) => {
        message.error(err.message || '导出失败');
      });
  };

// 按得分人统计（弹窗内可再按得分人筛选）
  const openStats = async () => {
    setStatsScorerId(undefined);
    setStatsOpen(true);
    await fetchStats(undefined);
  };

  const fetchStats = async (scorer?: number) => {
    setStatsLoading(true);
    try {
      const res = await assessmentApi.personalScores({
        month,
        district_id: districtId,
        department_id: departmentId,
        scorer_id: scorer,
      });
      setStatsItems(res.items || []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '加载统计失败');
    } finally {
      setStatsLoading(false);
    }
  };

  const handleStatsScorerChange = (v: number | undefined) => {
    setStatsScorerId(v);
    fetchStats(v);
  };

  // 导出：先选月份（必选），确认后自动下载
  const openExportDialog = () => {
    setExportMonth(month); // 默认带当前筛选月份，可改
    setExportOpen(true);
  };

  const handleExportConfirm = async () => {
    if (!exportMonth) {
      message.warning('请先选择导出月份');
      return;
    }
    setExporting(true);
    try {
      const url = assessmentApi.personalScoreExportUrl({
        month: exportMonth,
        district_id: districtId,
        department_id: departmentId,
        scorer_id: statsScorerId,
      });
      const token = localStorage.getItem('token');
      const res = await fetch(url, { headers: { 'Authorization': `Bearer ${token}` } });
      if (!res.ok) {
        let detail = '导出失败';
        try { const j = await res.json(); detail = j.detail || detail; } catch { /* ignore */ }
        throw new Error(detail);
      }
      const blob = await res.blob();
      const a = document.createElement('a');
      const objectUrl = URL.createObjectURL(blob);
      a.href = objectUrl;
      a.download = `个人得分_${exportMonth}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
      message.success('导出成功');
      setExportOpen(false);
    } catch (err: any) {
      message.error(err.message || '导出失败');
    } finally {
      setExporting(false);
    }
  };

  
  const statsColumns = [
    { title: '排名', key: 'rank', width: 60, align: 'center' as const, render: (_: any, __: any, idx: number) => idx + 1 },
    { title: '姓名', dataIndex: 'user_name', key: 'user_name', width: 100 },
    { title: '部门', dataIndex: 'department_name', key: 'department_name', width: 130, render: (v: any) => v || '-' },
    { title: '考核项数', dataIndex: 'item_count', key: 'item_count', width: 90, align: 'center' as const },
    {
      title: '总得分',
      dataIndex: 'total_score',
      key: 'total_score',
      width: 100,
      align: 'center' as const,
      sorter: (a: any, b: any) => a.total_score - b.total_score,
      render: (v: number) => <strong style={{ color: '#1677ff' }}>{v}</strong>,
    },
  ];

  const getScoreByLevel = (record: any, level: string) => {
    const score = (record.scores || []).find((s: any) => s.level === level);
    return score?.total_score ?? '-';
  };

  const getFinalScore = (record: any) => {
    // 优先取裁定后的最终分（调整分数裁定会更新 final_score）
    if (record.final_score !== null && record.final_score !== undefined) {
      return record.final_score;
    }
    const scores = record.scores || [];
    // 回退：按优先级取 group > regulator > district
    const group = scores.find((s: any) => s.level === 'group');
    if (group) return group.total_score;
    const regulator = scores.find((s: any) => s.level === 'regulator');
    if (regulator) return regulator.total_score;
    const district = scores.find((s: any) => s.level === 'district');
    if (district) return district.total_score;
    return '-';
  };

  // 生成近12个月的月份选项
  const monthOptions = () => {
    const options = [];
    const now = dayjs();
    for (let i = 0; i < 13; i++) {
      const m = now.subtract(i, 'month');
      const val = m.format('YYYY-MM');
      options.push({ label: `${val}`, value: val });
    }
    return options;
  };

  const columns = [
    {
      title: '序号',
      dataIndex: 'index',
      key: 'index',
      width: 60,
      render: (_: any, __: any, idx: number) => (page - 1) * pageSize + idx + 1,
    },
    {
      title: '工作项编号',
      dataIndex: 'work_item_no',
      key: 'work_item_no',
      width: 120,
    },
    {
      title: '工作项标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
    },
    {
      title: '主办人',
      dataIndex: 'sponsor_name',
      key: 'sponsor_name',
      width: 100,
    },
    {
      title: '部门',
      dataIndex: 'department_name',
      key: 'department_name',
      width: 120,
    },
    {
      title: '区域',
      dataIndex: 'district_name',
      key: 'district_name',
      width: 100,
    },
    {
      title: '发起时间',
      dataIndex: 'initiated_at',
      key: 'initiated_at',
      width: 160,
      render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (v: string) => {
        const label = ASSESSMENT_STATUS_LABELS[v] || v;
        const color = ASSESSMENT_STATUS_COLORS[v] || 'default';
        return <Tag color={color}>{label}</Tag>;
      },
    },
    {
      title: '区总评分',
      dataIndex: 'district_score',
      key: 'district_score',
      width: 90,
      align: 'center' as const,
      render: (_: any, record: any) => getScoreByLevel(record, 'district'),
    },
    {
      title: '规管评分',
      dataIndex: 'regulator_score',
      key: 'regulator_score',
      width: 90,
      align: 'center' as const,
      render: (_: any, record: any) => getScoreByLevel(record, 'regulator'),
    },
    {
      title: '集团总监评分',
      dataIndex: 'group_score',
      key: 'group_score',
      width: 110,
      align: 'center' as const,
      render: (_: any, record: any) => getScoreByLevel(record, 'group'),
    },
    {
      title: '最终分值',
      dataIndex: 'final_score',
      key: 'final_score',
      width: 90,
      align: 'center' as const,
      render: (_: any, record: any) => {
        const v = getFinalScore(record);
        return <strong style={{ color: '#1677ff' }}>{v}</strong>;
      },
    },
    {
      title: '参与人得分',
      key: 'participant_scores',
      width: 170,
      render: (_: any, record: any) => {
        // 取集团层分摊（裁定调整时后端已同步缩放）
        const groupScore = (record.scores || []).find((s: any) => s.level === 'group');
        const parts = groupScore?.participants || [];
        if (parts.length === 0) {
          // 无参与人分配：总分归主办人
          return <span style={{ fontSize: 12 }}>{record.sponsor_name || '-'}（未分配）</span>;
        }
        return (
          <div style={{ fontSize: 12, lineHeight: '20px' }}>
            {parts.map((p: any) => (
              <div key={p.user_id}>
                {p.user_name || `用户#${p.user_id}`}：<span style={{ color: '#1677ff', fontWeight: 600 }}>{p.score}</span> 分
              </div>
            ))}
          </div>
        );
      },
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <h2 style={{ margin: 0, fontSize: isMobile ? 18 : undefined }}>考核管理</h2>
        <Space wrap>
          <Button icon={<BarChartOutlined />} onClick={openStats}>
            按得分人统计
          </Button>
          <Button type="primary" icon={<ExportOutlined />} onClick={handleExport}>
            导出 Excel
          </Button>
        </Space>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={[12, 12]}>
          <Col xs={24} sm={12} md={6}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ whiteSpace: 'nowrap' }}>月份：</span>
              <Select
                style={{ flex: 1 }}
                allowClear
                placeholder="选择月份"
                value={month}
                onChange={(v) => setMonth(v)}
                options={monthOptions()}
              />
            </div>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ whiteSpace: 'nowrap' }}>状态：</span>
              <Select
                style={{ flex: 1 }}
                allowClear
                placeholder="全部状态"
                value={status}
                onChange={(v) => setStatus(v)}
                options={Object.entries(ASSESSMENT_STATUS_LABELS).map(([k, v]) => ({
                  label: v,
                  value: k,
                }))}
              />
            </div>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ whiteSpace: 'nowrap' }}>区域：</span>
              <Select
                style={{ flex: 1 }}
                allowClear
                placeholder="全部区域"
                value={districtId}
                onChange={(v) => setDistrictId(v)}
                options={districts.map((d) => ({ label: d.name, value: d.id }))}
              />
            </div>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ whiteSpace: 'nowrap' }}>部门：</span>
              <Select
                style={{ flex: 1 }}
                allowClear
                placeholder="全部部门"
                value={departmentId}
                onChange={(v) => setDepartmentId(v)}
                options={departments.map((d) => ({ label: d.name, value: d.id }))}
              />
            </div>
          </Col>
        </Row>
        <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
          <Col xs={24} md={8}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ whiteSpace: 'nowrap' }}>关键词：</span>
              <Input
                style={{ flex: 1 }}
                placeholder="搜索工作项标题"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onPressEnter={handleSearch}
              />
            </div>
          </Col>
          <Col xs={24} md={8}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ whiteSpace: 'nowrap' }}>得分人：</span>
              <Select
                style={{ flex: 1 }}
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder="全部得分人"
                value={scorerId}
                onChange={(v) => setScorerId(v)}
                options={users.map((u) => ({ label: u.real_name || u.username, value: u.id }))}
              />
            </div>
          </Col>
          <Col xs={24} md={8} style={{ textAlign: isMobile ? 'left' : 'right' }}>
            <Space>
              <Button onClick={handleReset}>重置</Button>
              <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
                查询
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {isMobile ? (
        <MobileCardList
          items={items}
          rowKey={(r) => r.id}
          loading={loading}
          emptyText="暂无考核记录"
          serverSide
          total={total}
          page={page}
          pageSize={pageSize}
          onPageChange={(p, ps) => { setPage(p); setPageSize(ps); }}
          renderCard={(r: any) => {
            const groupScore = (r.scores || []).find((x: any) => x.level === 'group');
            const parts = groupScore?.participants || [];
            return (
              <>
                <div className="m-card-title">{r.title || r.work_item_no}</div>
                <div className="m-card-meta">
                  <Tag color={ASSESSMENT_STATUS_COLORS[r.status] || 'default'} style={{ margin: 0 }}>
                    {ASSESSMENT_STATUS_LABELS[r.status] || r.status}
                  </Tag>
                  <span>{r.department_name || '-'} · {r.district_name || '-'}</span>
                  <span>主办人：{r.sponsor_name || '-'}</span>
                  {r.initiated_at && <span>{dayjs(r.initiated_at).format('YYYY-MM-DD HH:mm')}</span>}
                  <span>区总 {getScoreByLevel(r, 'district')} · 规管 {getScoreByLevel(r, 'regulator')} · 集团 {getScoreByLevel(r, 'group')}</span>
                  <span>最终分：<b style={{ color: '#1677ff' }}>{getFinalScore(r)}</b></span>
                  {parts.length > 0 ? (
                    <span>
                      参与人：{parts.map((p: any) => `${p.user_name || '用户' + p.user_id} ${p.score}分`).join('，')}
                    </span>
                  ) : (
                    <span>参与人：{r.sponsor_name || '-'}（未分配）</span>
                  )}
                </div>
                <div className="m-card-actions">
                  <Button size="small" onClick={() => navigate(`/assessment/${r.id}`)}>查看详情</Button>
                </div>
              </>
            );
          }}
        />
      ) : (
      <Table
        rowKey="id"
        loading={loading}
        dataSource={items}
        columns={columns}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
        scroll={{ x: 1200 }}
      />
      )}

      <Modal
        title={`按得分人统计${month ? `（${month}）` : '（全部月份）'}`}
        open={statsOpen}
        onCancel={() => setStatsOpen(false)}
        width={860}
        footer={[
          <Button key="close" onClick={() => setStatsOpen(false)}>关闭</Button>,
          <Button key="export" type="primary" icon={<ExportOutlined />} onClick={openExportDialog}>
            导出 Excel
          </Button>,
        ]}
      >
        <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Tag color="blue">统计口径：{month ? `${month} 发起` : '全部月份发起'}的已完结（已裁定）考核</Tag>
          <span style={{ color: '#999', fontSize: 12 }}>得分 = 集团层参与人分摊（无分配时归主办人）</span>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            得分人：
            <Select
              style={{ width: 180 }}
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="全部得分人"
              value={statsScorerId}
              onChange={handleStatsScorerChange}
              options={users.map((u) => ({ label: u.real_name || u.username, value: u.id }))}
            />
          </span>
        </div>
        <Table
          rowKey="user_id"
          size="small"
          loading={statsLoading}
          dataSource={statsItems}
          columns={statsColumns}
          pagination={false}
          expandable={{
            expandedRowRender: (record: any) => (
              <Table
                rowKey={(r: any) => `${record.user_id}-${r.assessment_id}`}
                size="small"
                dataSource={record.items || []}
                pagination={false}
                columns={[
                  { title: '工作项', dataIndex: 'title', key: 'title' },
                  { title: '部门', dataIndex: 'department_name', key: 'department_name', width: 110, render: (v: any) => v || '-' },
                  { title: '区域', dataIndex: 'district_name', key: 'district_name', width: 90, render: (v: any) => v || '-' },
                  { title: '得分', dataIndex: 'score', key: 'score', width: 70, align: 'center' as const },
                  { title: '考核指错', dataIndex: 'error_bonus', key: 'error_bonus', width: 90, align: 'center' as const, render: (v: any) => (v ? <Tag color="orange">指错</Tag> : '-') },
                  { title: '发起时间', dataIndex: 'initiated_at', key: 'initiated_at', width: 140, render: (v: any) => (v ? new Date(v).toLocaleDateString('zh-CN') : '-') },
                ]}
              />
            ),
          }}
        />
      </Modal>

      {/* 导出得分 Excel：先选月份（必选） */}
      <Modal
        title="导出个人得分 Excel"
        open={exportOpen}
        onCancel={() => setExportOpen(false)}
        onOk={handleExportConfirm}
        confirmLoading={exporting}
        okText="导出"
        cancelText="取消"
        okButtonProps={{ disabled: !exportMonth }}
      >
        <div style={{ marginBottom: 12, color: '#666', fontSize: 13 }}>
          请选择导出月份。导出结果为：汇总 sheet + 每位员工一个明细 sheet（含全部得分项和底部汇总行）。
          {statsScorerId && ' 当前筛选了得分人，仅导出该员工。'}
        </div>
        <Select
          style={{ width: '100%' }}
          placeholder="选择月份（必选）"
          value={exportMonth}
          onChange={(v) => setExportMonth(v)}
          options={monthOptions()}
        />
      </Modal>
    </div>
  );
};

export default AssessmentManagementPage;
