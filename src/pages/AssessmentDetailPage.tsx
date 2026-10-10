import React, { useEffect, useState } from 'react';
import { Card, Descriptions, Tag, Timeline, Typography, Space, Button, Image, List, Empty, Spin, message, Modal, Input, Form } from 'antd';
import { ArrowLeftOutlined, MailOutlined, FileTextOutlined, UserOutlined, CommentOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ASSESSMENT_STATUS_LABELS,
  ASSESSMENT_STATUS_COLORS,
  SCORE_LEVEL_LABELS,
  OPERATION_ACTION_LABELS,
  ROLE_LEVELS,
} from '../types';
import type { AssessmentAttachment, AssessmentDetail } from '../types';
import { assessmentApi } from '../services/api';
import { useAuth } from '../components/AuthProvider';
import AiOpinionCard, { AiNotConfiguredCard } from '../components/assessment/AiOpinionCard';
import { parseRulingResult } from '../components/assessment/RulingModal';

const { Title, Text, Paragraph } = Typography;

/** 将操作日志 detail 中的英文状态、层级等替换为中文 */
function translateDetail(detail: string): string {
  let result = detail;
  // 替换状态值
  Object.entries(ASSESSMENT_STATUS_LABELS).forEach(([key, label]) => {
    result = result.replaceAll(key, label);
  });
  // 替换评分层级
  Object.entries(SCORE_LEVEL_LABELS).forEach(([key, label]) => {
    result = result.replaceAll(`${key}层`, `${label}层`);
    result = result.replaceAll(`（${key}层）`, `（${label}层）`);
  });
  return result;
}

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
  const { user } = useAuth();
  const userLevel = user?.role_level || ROLE_LEVELS[user?.role as string] || 0;
  const canViewAi = userLevel >= ROLE_LEVELS.regulator;
  const [detail, setDetail] = useState<AssessmentDetail | null>(null);
  const [loading, setLoading] = useState(true);

  // 补充意见弹窗
  const [commentOpen, setCommentOpen] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [commentSubmitting, setCommentSubmitting] = useState(false);

  // 发起异议弹窗
  const [appealOpen, setAppealOpen] = useState(false);
  const [appealReason, setAppealReason] = useState('');
  const [appealing, setAppealing] = useState(false);
  const [appealForm] = Form.useForm();

  const submitAppeal = async () => {
    if (!id) return;
    if (!appealReason.trim()) {
      message.warning('请填写异议理由');
      return;
    }
    setAppealing(true);
    try {
      await assessmentApi.submitAppeal(Number(id), { reason: appealReason.trim() });
      message.success('异议已提交');
      setAppealOpen(false);
      setAppealReason('');
      fetchDetail();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '提交失败');
    } finally {
      setAppealing(false);
    }
  };

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

  const submitComment = async () => {
    if (!id) return;
    if (!commentText.trim()) {
      message.warning('请填写补充意见');
      return;
    }
    setCommentSubmitting(true);
    try {
      await assessmentApi.submitAppealComment(Number(id), commentText.trim());
      message.success('补充意见已提交');
      setCommentOpen(false);
      setCommentText('');
      fetchDetail();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '提交失败');
    } finally {
      setCommentSubmitting(false);
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
        {detail.status === 'appeal_period' && !detail.appeal && (
          <Button
            type="primary"
            danger
            icon={<ExclamationCircleOutlined />}
            onClick={() => { setAppealOpen(true); setAppealReason(''); appealForm.resetFields(); }}
          >
            发起异议
          </Button>
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

      {detail.appeal && (
        <Card
          title="异议与裁定"
          size="small"
          style={{ marginBottom: 16 }}
          extra={
            canViewAi &&
            (detail.status === 'appealed' ||
              detail.status === 'ai_reviewing' ||
              detail.status === 'pending_ruling') && (
              <Button size="small" icon={<CommentOutlined />} onClick={() => setCommentOpen(true)}>
                提交补充意见
              </Button>
            )
          }
        >
          {(() => {
            const appeal = detail.appeal!;
            const ruling = parseRulingResult(appeal.ruling_result);
            return (
              <div>
                <Space style={{ marginBottom: 8 }} wrap>
                  <Tag color="red">员工异议</Tag>
                  <Text strong>{appeal.appellant_name || `异议人 #${appeal.appellant_id}`}</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>{fmt(appeal.submitted_at)}</Text>
                </Space>
                <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{appeal.reason}</Paragraph>
                {appeal.attachments && appeal.attachments.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>异议凭证：</Text>
                    <AttachmentList attachments={appeal.attachments} />
                  </div>
                )}

                {canViewAi && appeal.ai_status !== 'hidden' && (
                  <div style={{ margin: '12px 0' }}>
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>
                      AI 中立审查意见（仅监察主任及以上可见）：
                    </Text>
                    {appeal.ai_status === 'not_configured' && <AiNotConfiguredCard />}
                    {appeal.ai_opinions &&
                      appeal.ai_opinions.map((op) => <AiOpinionCard key={op.id} opinion={op} />)}
                  </div>
                )}

                {(appeal.regulator_comment || appeal.group_director_comment) && (
                  <div style={{ margin: '12px 0' }}>
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                      补充意见：
                    </Text>
                    {appeal.regulator_comment && (
                      <Paragraph style={{ marginBottom: 4 }}>
                        <Tag color="blue">规管</Tag>
                        {appeal.regulator_comment}
                      </Paragraph>
                    )}
                    {appeal.group_director_comment && (
                      <Paragraph style={{ marginBottom: 4 }}>
                        <Tag color="purple">集团总监</Tag>
                        {appeal.group_director_comment}
                      </Paragraph>
                    )}
                  </div>
                )}

                {ruling && (
                  <div
                    style={{
                      marginTop: 12,
                      padding: '8px 12px',
                      background: '#f6ffed',
                      border: '1px solid #b7eb8f',
                      borderRadius: 6,
                    }}
                  >
                    <Space wrap>
                      <Tag color="success" style={{ fontSize: 14 }}>最终裁定</Tag>
                      {ruling.action === 'maintain' ? (
                        <Text strong>维持原评分（{ruling.original_score ?? '-'} 分）</Text>
                      ) : (
                        <Text strong>
                          调整分数：{ruling.original_score ?? '-'} 分 → {ruling.adjusted_score ?? '-'} 分
                        </Text>
                      )}
                      <Text type="secondary" style={{ fontSize: 12 }}>{fmt(appeal.ruled_at)}</Text>
                    </Space>
                    {ruling.comment && (
                      <Paragraph style={{ marginTop: 6, marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                        裁定意见：{ruling.comment}
                      </Paragraph>
                    )}
                  </div>
                )}
              </div>
            );
          })()}
        </Card>
      )}

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
                    <Text strong>{OPERATION_ACTION_LABELS[log.action] || log.action}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {log.operator_name || ''} · {fmt(log.created_at)}
                    </Text>
                  </Space>
                  {log.detail && (
                    <div><Text type="secondary" style={{ fontSize: 12 }}>{translateDetail(log.detail)}</Text></div>
                  )}
                </div>
              ),
            }))}
          />
        </Card>
      )}
      {/* 发起异议弹窗 */}
      <Modal
        title="发起异议"
        open={appealOpen}
        onCancel={() => setAppealOpen(false)}
        onOk={submitAppeal}
        confirmLoading={appealing}
        okText="提交异议"
        okButtonProps={{ danger: true }}
        cancelText="取消"
        destroyOnClose
      >
        <Paragraph type="secondary" style={{ fontSize: 13 }}>
          对「{detail.work_item_title}」的评分结果提出异议。异议提交后将进入 AI 中立审查与最终裁定流程，请如实说明理由。
        </Paragraph>
        <Form form={appealForm} layout="vertical">
          <Form.Item
            name="reason"
            label="异议理由"
            rules={[{ required: true, message: '请填写异议理由' }]}
          >
            <Input.TextArea
              rows={4}
              value={appealReason}
              onChange={(e) => setAppealReason(e.target.value)}
              placeholder="请详细说明异议理由..."
              maxLength={1000}
              showCount
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 补充意见弹窗 */}
      <Modal
        title="提交补充意见"
        open={commentOpen}
        onCancel={() => setCommentOpen(false)}
        onOk={submitComment}
        confirmLoading={commentSubmitting}
        okText="提交"
        cancelText="取消"
        destroyOnClose
      >
        <Input.TextArea
          rows={4}
          placeholder="填写对本次异议的补充意见（将随 AI 审查意见一并供裁定参考）"
          value={commentText}
          onChange={(e) => setCommentText(e.target.value)}
          maxLength={500}
          showCount
        />
      </Modal>
    </div>
  );
};

export default AssessmentDetailPage;
