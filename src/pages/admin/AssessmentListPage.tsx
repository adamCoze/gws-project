import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm, Row, Col } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined, CloseCircleOutlined, EyeOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { assessmentApi, departmentApi, districtApi } from '../../services/api';
import type { Assessment, Department, District } from '../../types';
import { ASSESSMENT_STATUS_LABELS, ASSESSMENT_STATUS_COLORS, ASSESSMENT_STATUS_OPTIONS, ROLE_LEVEL_OPTIONS } from '../../types';
import { formatUTCDate } from '../../utils/date';

const { TextArea } = Input;

const AssessmentListPage: React.FC = () => {
  const navigate = useNavigate();
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [districts, setDistricts] = useState<District[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // 筛选条件
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [yearFilter, setYearFilter] = useState<number | undefined>();
  const [monthFilter, setMonthFilter] = useState<number | undefined>();
  const [keyword, setKeyword] = useState<string>('');

  // 新建/编辑弹窗
  const [modalVisible, setModalVisible] = useState(false);
  const [editingAssessment, setEditingAssessment] = useState<Assessment | null>(null);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await assessmentApi.list({
        status: statusFilter,
        year: yearFilter,
        month: monthFilter,
        keyword: keyword || undefined,
        page,
        page_size: pageSize,
      });
      setAssessments(res.items || []);
      setTotal(res.total || 0);
    } catch {
      message.error('获取考核列表失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchDepartments = async () => {
    try {
      const data = await departmentApi.list();
      setDepartments(data);
    } catch {
      // ignore
    }
  };

  const fetchDistricts = async () => {
    try {
      const data = await districtApi.list();
      setDistricts(data);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    fetchData();
  }, [page, pageSize, statusFilter, yearFilter, monthFilter, keyword]);

  useEffect(() => {
    fetchDepartments();
    fetchDistricts();
  }, []);

  const handleSearch = () => {
    setPage(1);
    fetchData();
  };

  const handleReset = () => {
    setStatusFilter(undefined);
    setYearFilter(undefined);
    setMonthFilter(undefined);
    setKeyword('');
    setPage(1);
  };

  const openModal = (assessment?: Assessment) => {
    if (assessment) {
      setEditingAssessment(assessment);
      form.setFieldsValue({
        title: assessment.title,
        year: assessment.year,
        month: assessment.month,
        description: assessment.description,
        initiator_role_level: assessment.initiator_role_level,
        initiator_department_id: assessment.initiator_department_id,
        initiator_district_id: assessment.initiator_district_id,
      });
    } else {
      setEditingAssessment(null);
      form.resetFields();
      const now = new Date();
      form.setFieldsValue({
        year: now.getFullYear(),
        month: now.getMonth() + 1,
      });
    }
    setModalVisible(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      if (editingAssessment) {
        await assessmentApi.update(editingAssessment.id, values);
        message.success('考核已更新');
      } else {
        await assessmentApi.create(values);
        message.success('考核已创建');
      }

      setModalVisible(false);
      fetchData();
    } catch (err: any) {
      if (err.response?.data?.detail) {
        message.error(err.response.data.detail);
      } else if (!err.errorFields) {
        message.error('操作失败');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await assessmentApi.delete(id);
      message.success('考核已删除');
      fetchData();
    } catch {
      message.error('删除失败');
    }
  };

  const handleStart = async (id: number) => {
    try {
      await assessmentApi.start(id);
      message.success('已启动评分');
      fetchData();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '启动失败');
    }
  };

  const handleCancel = async (id: number) => {
    try {
      await assessmentApi.cancel(id);
      message.success('已取消考核');
      fetchData();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '取消失败');
    }
  };

  const yearOptions = Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - 2 + i).map((y) => ({
    value: y,
    label: `${y}年`,
  }));

  const monthOptions = Array.from({ length: 12 }, (_, i) => i + 1).map((m) => ({
    value: m,
    label: `${m}月`,
  }));

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (v: string, record: Assessment) => (
        <a onClick={() => navigate(`/admin/assessments/${record.id}`)}>{v}</a>
      ),
    },
    {
      title: '考核周期',
      key: 'period',
      width: 140,
      render: (_: any, record: Assessment) => `${record.year}年${record.month}月`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={ASSESSMENT_STATUS_COLORS[status as keyof typeof ASSESSMENT_STATUS_COLORS]}>
          {ASSESSMENT_STATUS_LABELS[status as keyof typeof ASSESSMENT_STATUS_LABELS]}
        </Tag>
      ),
    },
    {
      title: '创建人',
      key: 'creator',
      width: 120,
      render: (_: any, record: Assessment) => record.creator?.real_name || record.creator?.username || '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (v: string) => formatUTCDate(v, 'YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'action',
      width: 280,
      render: (_: any, record: Assessment) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => navigate(`/admin/assessments/${record.id}`)}>
            查看
          </Button>
          {record.status === 'draft' && (
            <>
              <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => handleStart(record.id)}>
                启动
              </Button>
              <Button size="small" icon={<EditOutlined />} onClick={() => openModal(record)}>
                编辑
              </Button>
              <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
                <Button size="small" danger icon={<DeleteOutlined />}>
                  删除
                </Button>
              </Popconfirm>
            </>
          )}
          {(record.status === 'scoring' || record.status === 'reviewing') && (
            <Popconfirm title="确认取消考核？" onConfirm={() => handleCancel(record.id)}>
              <Button size="small" danger icon={<CloseCircleOutlined />}>
                取消
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>考核管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>
          新建考核
        </Button>
      </div>

      {/* 筛选区 */}
      <div style={{ marginBottom: 16, padding: 16, background: '#fafafa', borderRadius: 6 }}>
        <Row gutter={[16, 12]} align="middle">
          <Col span={6}>
            <Select
              placeholder="状态"
              allowClear
              style={{ width: '100%' }}
              value={statusFilter}
              onChange={(v) => { setStatusFilter(v); setPage(1); }}
              options={ASSESSMENT_STATUS_OPTIONS}
            />
          </Col>
          <Col span={5}>
            <Select
              placeholder="年份"
              allowClear
              style={{ width: '100%' }}
              value={yearFilter}
              onChange={(v) => { setYearFilter(v); setPage(1); }}
              options={yearOptions}
            />
          </Col>
          <Col span={5}>
            <Select
              placeholder="月份"
              allowClear
              style={{ width: '100%' }}
              value={monthFilter}
              onChange={(v) => { setMonthFilter(v); setPage(1); }}
              options={monthOptions}
            />
          </Col>
          <Col span={5}>
            <Input.Search
              placeholder="搜索标题"
              allowClear
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={handleSearch}
            />
          </Col>
          <Col span={3}>
            <Space>
              <Button onClick={handleReset}>重置</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <Table
        columns={columns}
        dataSource={assessments}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showTotal: (t) => `共 ${t} 条`,
          showSizeChanger: true,
          pageSizeOptions: [10, 20, 50, 100],
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />

      <Modal
        title={editingAssessment ? '编辑考核' : '新建考核'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        confirmLoading={submitting}
        width={600}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item
            name="title"
            label="考核标题"
            rules={[{ required: true, message: '请输入考核标题' }]}
          >
            <Input placeholder="请输入考核标题" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="year"
                label="年份"
                rules={[{ required: true, message: '请选择年份' }]}
              >
                <Select options={yearOptions} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="month"
                label="月份"
                rules={[{ required: true, message: '请选择月份' }]}
              >
                <Select options={monthOptions} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="initiator_department_id" label="考核范围-部门">
                <Select
                  allowClear
                  placeholder="全部部门"
                  options={departments.map((d) => ({ value: d.id, label: d.name }))}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="initiator_district_id" label="考核范围-区域">
                <Select
                  allowClear
                  placeholder="全部区域"
                  options={districts.map((d) => ({ value: d.id, label: d.name }))}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="initiator_role_level" label="发起身份（角色等级）">
            <Select
              allowClear
              placeholder="选择发起角色等级"
              options={ROLE_LEVEL_OPTIONS}
            />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={3} placeholder="考核说明（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default AssessmentListPage;
