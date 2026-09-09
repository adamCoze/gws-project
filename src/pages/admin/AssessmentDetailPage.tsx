import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Descriptions, Tag, Space, Tabs, Table, message, Popconfirm, Spin } from 'antd';
import { ArrowLeftOutlined, PlayCircleOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { assessmentApi } from '../../services/api';
import type { Assessment, AssessmentScore, AssessmentOperationLog } from '../../types';
import { ASSESSMENT_STATUS_LABELS, ASSESSMENT_STATUS_COLORS, ROLE_LEVEL_LABELS } from '../../types';
import { formatUTCDate } from '../../utils/date';

const AssessmentDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [scores, setScores] = useState<AssessmentScore[]>([]);
  const [logs, setLogs] = useState<AssessmentOperationLog[]>([]);
  const [scoresLoading, setScoresLoading] = useState(false);
  const [logsLoading, setLogsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const fetchDetail = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await assessmentApi.get(parseInt(id));
      setAssessment(data);
    } catch {
      message.error('获取考核详情失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchScores = async () => {
    if (!id) return;
    setScoresLoading(true);
    try {
      const data = await assessmentApi.getScores(parseInt(id));
      setScores(data);
    } catch {
      // silently ignore for now
    } finally {
      setScoresLoading(false);
    }
  };

  const fetchLogs = async () => {
    if (!id) return;
    setLogsLoading(true);
    try {
      const data = await assessmentApi.getOperationLogs(parseInt(id));
      setLogs(data);
    } catch {
      // silently ignore for now
    } finally {
      setLogsLoading(false);
    }
  };

  useEffect(() => {
    fetchDetail();
    fetchScores();
  }, [id]);

  const handleStart = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      await assessmentApi.start(parseInt(id));
      message.success('已启动评分');
      fetchDetail();
      fetchScores();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '启动失败');
    } finally {
      setActionLoading(false);
    }
  };

  const handleComplete = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      await assessmentApi.complete(parseInt(id));
      message.success('考核已完成');
      fetchDetail();
      fetchScores();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '操作失败');
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      await assessmentApi.cancel(parseInt(id));
      message.success('考核已取消');
      fetchDetail();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '操作失败');
    } finally {
      setActionLoading(false);
    }
  };

  // 将评分按工作项分组，显示多级评分状态
  const groupScoresByWorkItem = () => {
    const map = new Map<number, {
      work_item_id: number;
      work_item_title: string;
      assignee_name: string;
      scores: Record<number, AssessmentScore>; // level -> score
    }>();

    scores.forEach((s) => {
      const wiId = s.work_item_id;
      if (!map.has(wiId)) {
        map.set(wiId, {
          work_item_id: wiId,
          work_item_title: s.work_item?.title || '-',
          assignee_name: s.work_item?.assignee_names || s.work_item?.assignee?.real_name || '-',
          scores: {},
        });
      }
      map.get(wiId)!.scores[s.level] = s;
    });

    return Array.from(map.values());
  };

  const renderScoreCell = (level: number, scoreRecord?: AssessmentScore) => {
    if (!scoreRecord) {
      return <Tag color="default">未分配</Tag>;
    }
    if (scoreRecord.score !== undefined && scoreRecord.score !== null) {
      return (
        <div>
          <Tag color="success">已评分</Tag>
          <div style={{ marginTop: 4 }}>
            <span style={{ fontWeight: 600 }}>{scoreRecord.score}分</span>
          </div>
          <div style={{ fontSize: 12, color: '#888' }}>
            {scoreRecord.scorer?.real_name || scoreRecord.scorer?.username || '-'}
          </div>
          {scoreRecord.comment && (
            <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>{scoreRecord.comment}</div>
          )}
        </div>
      );
    }
    return (
      <div>
        <Tag color="processing">待评分</Tag>
        <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>
          {scoreRecord.scorer?.real_name || scoreRecord.scorer?.username || (scoreRecord.scorer_role_level ? ROLE_LEVEL_LABELS[scoreRecord.scorer_role_level] : '-')}
        </div>
      </div>
    );
  };

  const scoreColumns = [
    {
      title: '工作项',
      dataIndex: 'work_item_title',
      key: 'work_item_title',
      width: 240,
    },
    {
      title: '负责人',
      dataIndex: 'assignee_name',
      key: 'assignee_name',
      width: 120,
    },
    {
      title: '一级评分',
      key: 'level1',
      width: 180,
      render: (_: any, record: ReturnType<typeof groupScoresByWorkItem>[number]) =>
        renderScoreCell(1, record.scores[1]),
    },
    {
      title: '二级评分',
      key: 'level2',
      width: 180,
      render: (_: any, record: ReturnType<typeof groupScoresByWorkItem>[number]) =>
        renderScoreCell(2, record.scores[2]),
    },
  ];

  const logColumns = [
    {
      title: '操作时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (v: string) => formatUTCDate(v, 'YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      width: 120,
    },
    {
      title: '操作人',
      key: 'operator',
      width: 120,
      render: (_: any, record: AssessmentOperationLog) =>
        record.operator?.real_name || record.operator?.username || '-',
    },
    {
      title: '备注',
      dataIndex: 'remark',
      key: 'remark',
      render: (v: string) => v || '-',
    },
  ];

  if (loading && !assessment) {
    return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>;
  }

  if (!assessment) {
    return <div>考核不存在</div>;
  }

  const tabItems = [
    {
      key: 'scores',
      label: '评分列表',
      children: (
        <Table
          columns={scoreColumns}
          dataSource={groupScoresByWorkItem()}
          rowKey="work_item_id"
          loading={scoresLoading}
          pagination={{ showTotal: (t) => `共 ${t} 条`, pageSize: 20 }}
        />
      ),
    },
    {
      key: 'logs',
      label: '操作日志',
      children: (
        <Table
          columns={logColumns}
          dataSource={logs}
          rowKey="id"
          loading={logsLoading}
          pagination={{ showTotal: (t) => `共 ${t} 条`, pageSize: 20 }}
          onRow={() => ({ onClick: fetchLogs })}
        />
      ),
    },
  ];

  const handleTabChange = (key: string) => {
    if (key === 'logs' && logs.length === 0) {
      fetchLogs();
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/admin/assessments')}
          style={{ marginBottom: 12 }}
        >
          返回列表
        </Button>
        <h2 style={{ margin: '8px 0 16px 0' }}>考核详情</h2>
      </div>

      <Descriptions
        bordered
        column={3}
        style={{ marginBottom: 24 }}
        extra={
          <Space>
            {assessment.status === 'draft' && (
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={handleStart}
                loading={actionLoading}
              >
                启动评分
              </Button>
            )}
            {(assessment.status === 'scoring' || assessment.status === 'reviewing') && (
              <>
                <Button
                  type="primary"
                  icon={<CheckCircleOutlined />}
                  onClick={handleComplete}
                  loading={actionLoading}
                >
                  确认完成
                </Button>
                <Popconfirm title="确认取消考核？" onConfirm={handleCancel}>
                  <Button danger icon={<CloseCircleOutlined />} loading={actionLoading}>
                    取消考核
                  </Button>
                </Popconfirm>
              </>
            )}
          </Space>
        }
      >
        <Descriptions.Item label="标题" span={3}>{assessment.title}</Descriptions.Item>
        <Descriptions.Item label="考核周期">
          {assessment.year}年{assessment.month}月
        </Descriptions.Item>
        <Descriptions.Item label="状态">
          <Tag color={ASSESSMENT_STATUS_COLORS[assessment.status]}>
            {ASSESSMENT_STATUS_LABELS[assessment.status]}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="创建人">
          {assessment.creator?.real_name || assessment.creator?.username || '-'}
        </Descriptions.Item>
        <Descriptions.Item label="创建时间">
          {formatUTCDate(assessment.created_at, 'YYYY-MM-DD HH:mm')}
        </Descriptions.Item>
        <Descriptions.Item label="更新时间">
          {formatUTCDate(assessment.updated_at, 'YYYY-MM-DD HH:mm')}
        </Descriptions.Item>
        <Descriptions.Item label="发起角色等级">
          {assessment.initiator_role_level ? ROLE_LEVEL_LABELS[assessment.initiator_role_level] : '-'}
        </Descriptions.Item>
        {assessment.description && (
          <Descriptions.Item label="描述" span={3}>{assessment.description}</Descriptions.Item>
        )}
      </Descriptions>

      <Tabs
        defaultActiveKey="scores"
        items={tabItems}
        onChange={handleTabChange}
      />
    </div>
  );
};

export default AssessmentDetailPage;
