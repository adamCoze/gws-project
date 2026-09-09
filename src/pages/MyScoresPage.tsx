import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Tag, message, Descriptions, Radio } from 'antd';
import { StarOutlined } from '@ant-design/icons';
import { assessmentScoreApi } from '../services/api';
import type { PendingScore } from '../types';
import { formatUTCDate } from '../utils/date';

const { TextArea } = Input;

const MyScoresPage: React.FC = () => {
  const [scores, setScores] = useState<PendingScore[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [currentScore, setCurrentScore] = useState<PendingScore | null>(null);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await assessmentScoreApi.pendingList();
      setScores(data);
    } catch {
      message.error('获取待评分列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleScore = (record: PendingScore) => {
    setCurrentScore(record);
    form.resetFields();
    setModalVisible(true);
  };

  const handleSubmit = async () => {
    if (!currentScore) return;
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      await assessmentScoreApi.submit(currentScore.id, {
        score: values.score,
        comment: values.comment,
      });
      message.success('评分已提交');
      setModalVisible(false);
      fetchData();
    } catch (err: any) {
      if (err.response?.data?.detail) {
        message.error(err.response.data.detail);
      } else if (!err.errorFields) {
        message.error('提交失败');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const columns = [
    {
      title: '考核标题',
      dataIndex: 'assessment_title',
      key: 'assessment_title',
      width: 200,
    },
    {
      title: '工作项',
      dataIndex: 'work_item_title',
      key: 'work_item_title',
    },
    {
      title: '被考核人',
      dataIndex: 'assignee_name',
      key: 'assignee_name',
      width: 120,
      render: (v: string) => v || '-',
    },
    {
      title: '评分层级',
      dataIndex: 'level',
      key: 'level',
      width: 120,
      render: (level: number) => {
        const labels: Record<number, string> = {
          1: '一级评分',
          2: '二级评分',
          3: '三级评分',
        };
        return labels[level] || `${level}级评分`;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === 'scored' ? 'success' : 'processing'}>
          {status === 'scored' ? '已评分' : '待评分'}
        </Tag>
      ),
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
      width: 100,
      render: (_: any, record: PendingScore) => (
        <Button
          type="primary"
          size="small"
          icon={<StarOutlined />}
          onClick={() => handleScore(record)}
          disabled={record.status === 'scored'}
        >
          评分
        </Button>
      ),
    },
  ];

  const pendingCount = scores.filter((s) => s.status === 'pending').length;

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>
          我的待评分
          <Tag color="processing" style={{ marginLeft: 8 }}>
            {pendingCount} 项待处理
          </Tag>
        </h2>
        <Button onClick={fetchData}>刷新</Button>
      </div>

      <Table
        columns={columns}
        dataSource={scores}
        rowKey="id"
        loading={loading}
        pagination={{ showTotal: (t) => `共 ${t} 条`, showSizeChanger: true, pageSizeOptions: [20, 50, 100], defaultPageSize: 20 }}
      />

      <Modal
        title="评分"
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        confirmLoading={submitting}
        okText="提交评分"
        cancelText="取消"
        width={560}
        destroyOnClose
      >
        {currentScore && (
          <>
            <Descriptions column={1} size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="考核">{currentScore.assessment_title}</Descriptions.Item>
              <Descriptions.Item label="工作项">{currentScore.work_item_title}</Descriptions.Item>
              <Descriptions.Item label="被考核人">{currentScore.assignee_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="评分层级">
                {currentScore.level === 1 ? '一级评分' : currentScore.level === 2 ? '二级评分' : `${currentScore.level}级评分`}
              </Descriptions.Item>
            </Descriptions>

            <Form form={form} layout="vertical">
              <Form.Item
                name="score"
                label="评分"
                rules={[{ required: true, message: '请选择评分' }]}
                initialValue={10}
              >
                <Radio.Group buttonStyle="solid" style={{ width: '100%' }}>
                  <Radio.Button value={1}>1分</Radio.Button>
                  <Radio.Button value={5}>5分</Radio.Button>
                  <Radio.Button value={10}>10分</Radio.Button>
                  <Radio.Button value={20}>20分</Radio.Button>
                  <Radio.Button value={30}>30分</Radio.Button>
                </Radio.Group>
              </Form.Item>

              <Form.Item
                name="comment"
                label="评语"
              >
                <TextArea rows={4} placeholder="请输入评语（可选）" maxLength={500} showCount />
              </Form.Item>
            </Form>
          </>
        )}
      </Modal>
    </div>
  );
};

export default MyScoresPage;
