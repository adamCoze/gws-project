import React, { useState, useEffect } from 'react';
import { Table, Button, Select, Space, Card, Row, Col, Input, DatePicker, Tag, message, Modal } from 'antd';
import { ExportOutlined, SearchOutlined, BarChartOutlined } from '@ant-design/icons';
import { assessmentApi, districtApi, departmentApi } from '../../services/api';
import { ASSESSMENT_STATUS_LABELS, ASSESSMENT_STATUS_COLORS } from '../../types';
import type { District, Department } from '../../types';
import dayjs from 'dayjs';

const { RangePicker } = DatePicker;

const AssessmentManagementPage: React.FC = () => {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [districts, setDistricts] = useState<District[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);

  // 筛选条件
  const [month, setMonth] = useState<string | undefined>(undefined);
  const [status, setStatus] = useState<string | undefined>(undefined);
  const [districtId, setDistrictId] = useState<number | undefined>(undefined);
  const [departmentId, setDepartmentId] = useState<number | undefined>(undefined);
  const [keyword, setKeyword] = useState<string>('');

  // 按得分人统计
  const [statsOpen, setStatsOpen] = useState(false);
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsItems, setStatsItems] = useState<any[]>([]);

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

  // 按得分人统计
  const openStats = async () => {
    setStatsOpen(true);
    setStatsLoading(true);
    try {
      const res = await assessmentApi.personalScores({
        month,
        district_id: districtId,
        department_id: departmentId,
      });
      setStatsItems(res.items || []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '加载统计失败');
    } finally {
      setStatsLoading(false);
    }
  };

  const handleStatsExport = () => {
    const url = assessmentApi.personalScoreExportUrl({
      month,
      district_id: districtId,
      department_id: departmentId,
    });
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
        a.download = `个人得分统计_${month || '全部'}_${dayjs().format('YYYYMMDD')}.xlsx`;
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
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>考核管理</h2>
        <Space>
          <Button icon={<BarChartOutlined />} onClick={openStats}>
            按得分人统计
          </Button>
          <Button type="primary" icon={<ExportOutlined />} onClick={handleExport}>
            导出 Excel
          </Button>
        </Space>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={6}>
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
          <Col span={6}>
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
          <Col span={6}>
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
          <Col span={6}>
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
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={12}>
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
          <Col span={12} style={{ textAlign: 'right' }}>
            <Space>
              <Button onClick={handleReset}>重置</Button>
              <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
                查询
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

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

      <Modal
        title={`按得分人统计${month ? `（${month}）` : '（全部月份）'}`}
        open={statsOpen}
        onCancel={() => setStatsOpen(false)}
        width={860}
        footer={[
          <Button key="close" onClick={() => setStatsOpen(false)}>关闭</Button>,
          <Button key="export" type="primary" icon={<ExportOutlined />} onClick={handleStatsExport}>
            导出 Excel
          </Button>,
        ]}
      >
        <div style={{ marginBottom: 8 }}>
          <Tag color="blue">统计口径：{month ? `${month} 发起` : '全部月份发起'}的已完结（已裁定）考核</Tag>
          <span style={{ color: '#999', fontSize: 12 }}>得分 = 集团层参与人分摊（无分配时归主办人）</span>
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
                  { title: '部门', dataIndex: 'department_name', key: 'department_name', width: 120, render: (v: any) => v || '-' },
                  { title: '得分', dataIndex: 'score', key: 'score', width: 80, align: 'center' as const },
                  { title: '发起时间', dataIndex: 'initiated_at', key: 'initiated_at', width: 150, render: (v: any) => (v ? new Date(v).toLocaleDateString('zh-CN') : '-') },
                ]}
              />
            ),
          }}
        />
      </Modal>
    </div>
  );
};

export default AssessmentManagementPage;
