import React, { useEffect, useState } from 'react';
import { Card, Descriptions, Tag, Timeline, Typography, Space, Button, Image, List, Empty, Spin, message } from 'antd';
import { ArrowLeftOutlined, MailOutlined, FileTextOutlined, UserOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ASSESSMENT_STATUS_LABELS,
  ASSESSMENT_STATUS_COLORS,
  SCORE_LEVEL_LABELS,
} from '../types';
import type { AssessmentAttachment, AssessmentDetail } from '../types';
import { assessmentApi } from '../services/api';

const { Title, Text, Paragraph } = Typography;

/** 凭证展示：图片缩略图 + 文字凭证 */
const AttachmentList: React.FC<{ attachments?: AssessmentAttachment[] }> = ({ attachments }) => {
  if (!attachments || attachments.length === 0) {
    return <Text type="secondary" style={{ fontSize: 12 }}>无凭证</Text>;
  }
  return (
    <List
      size="small"
      dataSource={attachments}
      renderItem={(item) => (
        <List.Item style={{ padding: '6px 0', border: 'none' }}>
          {item.file_type === 'image' && item.file_path ? (
            <Space>
              <Image src={item.file_path} width={64} height={64} style={{ objectFit: 'cover', borderRadius: 4 }} />
              <div>
                <div>{item.file_name || '图片凭证'}</div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {item.uploader_name || ''} {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN', { hour12: false }) : ''}
                </Text>
              </div>
            </Space>
          ) : (
            <Space align="start">
              <FileTextOutlined style={{ marginTop: 4 }} />
              <div>
                <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>{item.content}</Paragraph>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {item.uploader_name || ''} {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN', { hour12: false }) : ''}
                </Text>
              </div>
            </Space>
          )}
        </List.Item>
      )}
    />
  );
};

/**
 * 考核详情：基本信息 + 评分时间线（各层评分、参与人分配、凭证）
 * + 补充凭证记录 + 操作日志 + 关联邮件
 */
const AssessmentDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<AssessmentDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchDetail = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const res = await assessmentApi.detail(Number(id));
      setDetail(res);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '加载考核详情失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>;
  }
  if (!detail) {
    return <Empty description="考核记录不存在" />;
  }

  const fmt = (v?: string | null) => (v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '-');

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>返回</Button>
        <Title level={4} style={{ margin: 0 }}>{detail.work_item_title || `考核 #${detail.id}`}</Title>
        <Tag color={ASSESSMENT_STATUS_COLORS[detail.status]} style={{ fontSize: 14 }}>
          {ASSESSMENT_STATUS_LABELS[detail.status] || detail.status}
        </Tag>
        {detail.final_score !== null && detail.final_score !== undefined && (
          <Tag color="blue" style={{ fontSize: 14 }}>最终得分：{detail.final_score}</Tag>
        )}
      </Space>

      <Card title="基本信息" size="small" style={{ marginBottom: 16 }}>
        <Descriptions column={3} size="small">
          <Descriptions.Item label="部门">{detail.department_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="区域">{detail.district_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="责任人">{detail.sponsor_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="发起人">{detail.initiator_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="发起时间">{fmt(detail.initiated_at)}</Descriptions.Item>
          <Descriptions.Item label="完结时间">{fmt(detail.completed_at)}</Descriptions.Item>
          {detail.appeal_deadline && (
            <Descriptions.Item label="异议截止">{fmt(detail.appeal_deadline)}</Descriptions.Item>
          )}
          {detail.has_email && (
            <Descriptions.Item label="关联邮件">
              {detail.email_url ? (
                <a href={detail.email_url} target="_blank" rel="noreferrer">
                  <MailOutlined /> 查看邮件
                </a>
              ) : (
                <Tag icon={<MailOutlined />} color="blue">有关联邮件</Tag>
              )}
            </Descriptions.Item>
          )}
        </Descriptions>
        {detail.work_item_content && (
          <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0, whiteSpace: 'pre-wrap' }}>
            {detail.work_item_content}
          </Paragraph>
        )}
      </Card>

      <Card title="评分记录" size="small" style={{ marginBottom: 16 }}>
        {!detail.scores || detail.scores.length === 0 ? (
          <Empty description="暂无评分记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Timeline
            items={detail.scores.map((score) => ({
              color: 'blue',
              children: (
                <div>
                  <Space style={{ marginBottom: 4 }}>
                    <Tag color="processing">{SCORE_LEVEL_LABELS[score.level] || score.level}</Tag>
                    <Text strong>{score.scorer_name || `评分人 #${score.scorer_id}`}</Text>
                    <Text strong style={{ color: '#f5222d', fontSize: 16 }}>{score.total_score} 分</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>{fmt(score.submitted_at)}</Text>
                  </Space>
                  {score.opinion && (
                    <Paragraph style={{ marginBottom: 4, whiteSpace: 'pre-wrap' }}>{score.opinion}</Paragraph>
                  )}
                  {score.participants && score.participants.length > 0 && (
                    <div style={{ marginBottom: 4 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>参与人分配：</Text>
                      <Space wrap>
                        {score.participants.map((p) => (
                          <Tag key={p.user_id} icon={<UserOutlined />}>
                            {p.user_name || `用户#${p.user_id}`}：{p.score} 分
                          </Tag>
                        ))}
                      </Space>
                    </div>
                  )}
                  <AttachmentList attachments={score.attachments} />
                </div>
              ),
            }))}
          />
        )}
      </Card>

      {detail.supplement_requests && detail.supplement_requests.length > 0 && (
        <Card title="补充凭证记录" size="small" style={{ marginBottom: 16 }}>
          <List
            size="small"
            dataSource={detail.supplement_requests}
            renderItem={(req) => (
              <List.Item style={{ display: 'block' }}>
                <Space style={{ marginBottom: 4 }}>
                  <Tag color={req.status === 'completed' ? 'success' : 'warning'}>
                    {req.status === 'completed' ? '已提交' : '待提交'}
                  </Tag>
                  <Text strong>{req.requester_name || '评分人'}</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>{fmt(req.created_at)}</Text>
                </Space>
                {req.note && <Paragraph style={{ marginBottom: 4 }}>要求：{req.note}</Paragraph>}
                {req.response && (
                  <Paragraph style={{ marginBottom: 4, whiteSpace: 'pre-wrap' }}>
                    补充说明：{req.response}
                  </Paragraph>
                )}
                <AttachmentList attachments={req.attachments} />
              </List.Item>
            )}
          />
        </Card>
      )}

      {detail.attachments && detail.attachments.length > 0 && (
        <Card title="凭证汇总" size="small" style={{ marginBottom: 16 }}>
          <AttachmentList attachments={detail.attachments} />
        </Card>
      )}

      {detail.operation_logs && detail.operation_logs.length > 0 && (
        <Card title="操作日志" size="small">
          <Timeline
            items={detail.operation_logs.map((log) => ({
              color: 'gray',
              children: (
                <div>
                  <Space>
                    <Text>{log.action}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {log.operator_name || ''} · {fmt(log.created_at)}
                    </Text>
                  </Space>
                  {log.detail && (
                    <div><Text type="secondary" style={{ fontSize: 12 }}>{log.detail}</Text></div>
                  )}
                </div>
              ),
            }))}
          />
        </Card>
      )}
    </div>
  );
};

export default AssessmentDetailPage;
