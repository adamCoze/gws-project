import React, { useState, useEffect } from 'react';
import { Table, Button, Select, Space, Card, Row, Col, Input, DatePicker, Tag, message } from 'antd';
import { ExportOutlined, SearchOutlined } from '@ant-design/icons';
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

  const getScoreByLevel = (record: any, level: string) => {
    const score = (record.scores || []).find((s: any) => s.level === level);
    return score?.total_score ?? '-';
  };

  const getFinalScore = (record: any) => {
    const scores = record.scores || [];
    // 按优先级取：group > regulator > district
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
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>考核管理</h2>
        <Space>
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
    </div>
  );
};

export default AssessmentManagementPage;
