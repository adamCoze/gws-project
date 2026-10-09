import { useEffect, useState } from 'react';
import {
  Modal,
  Button,
  Space,
  Tag,
  Typography,
  message,
  Select,
  Input,
  Divider,
  Alert,
} from 'antd';
import { AuditOutlined } from '@ant-design/icons';
import { assessmentApi } from '../../services/api';
import type { AssessmentListItem, AssessmentDetail, RulingResult } from '../../types';
import { SCORE_LEVEL_LABELS, SCORE_TIERS } from '../../types';
import AiOpinionCard, { AiNotConfiguredCard } from './AiOpinionCard';

const { Text, Paragraph } = Typography;

interface Props {
  open: boolean;
  target: AssessmentListItem | null;
  onCancel: () => void;
  onSuccess: () => void;
}

/**
 * 最终裁定弹窗（集团总监及以上，代录总裁线下裁定结果）
 * 材料区：AI意见卡片（有异议时）+ 异议理由 + 补充意见 + 各层评分
 * 操作区：维持原评分 / 调整分数（档位 + 意见必填）
 */
const RulingModal: React.FC<Props> = ({ open, target, onCancel, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<AssessmentDetail | null>(null);
  const [rulingAction, setRulingAction] = useState<'maintain' | 'adjust'>('maintain');
  const [adjustedScore, setAdjustedScore] = useState<number | undefined>(undefined);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open && target) {
      setLoading(true);
      setRulingAction('maintain');
      setAdjustedScore(undefined);
      setComment('');
      setDetail(null);
      assessmentApi
        .detail(target.id)
        .then((d) => setDetail(d))
        .catch(() => message.error('加载考核详情失败'))
        .finally(() => setLoading(false));
    }
  }, [open, target]);

  const appeal = detail?.appeal || null;
  const hasAppeal = !!appeal;
  const finalScore = detail?.final_score ?? null;

  const handleSubmit = async () => {
    if (!target) return;
    if (rulingAction === 'adjust') {
      if (adjustedScore === undefined || adjustedScore === null) {
        message.warning('请选择调整后的分数');
        return;
      }
      if (!comment.trim()) {
        message.warning('调整分数时必须填写裁定意见');
        return;
      }
    }
    setSubmitting(true);
    try {
      await assessmentApi.submitRuling(target.id, {
        ruling_action: rulingAction,
        adjusted_score: rulingAction === 'adjust' ? adjustedScore : undefined,
        comment: comment.trim() || undefined,
      });
      message.success('裁定完成，考核已完结');
      onSuccess();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '裁定提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={
        <Space>
          <AuditOutlined />
          <span>最终裁定{hasAppeal ? '（有异议）' : '（异议期满，确认完结）'}</span>
        </Space>
      }
      onCancel={onCancel}
      width={720}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          取消
        </Button>,
        <Button
          key="submit"
          type="primary"
          loading={submitting}
          onClick={handleSubmit}
        >
          确认裁定
        </Button>,
      ]}
    >
      {loading && <Text type="secondary">加载裁定材料中…</Text>}

      {detail && (
        <>
          {/* 基本信息 */}
          <Paragraph style={{ marginBottom: 8 }}>
            <Text strong>{detail.work_item_title}</Text>
            <br />
            <Text type="secondary">
              主办人：{detail.sponsor_name || '-'} ｜ 部门：
              {detail.department_name || '-'} ｜ 当前考核分：
              <Text strong>{finalScore ?? '-'}</Text>
            </Text>
          </Paragraph>

          <Divider titlePlacement="left" plain style={{ fontSize: 13 }}>
            各层评分
          </Divider>
          {(detail.scores || []).map((s) => (
            <Paragraph key={s.id} style={{ marginBottom: 4, fontSize: 13 }}>
              <Tag>{SCORE_LEVEL_LABELS[s.level] || s.level}</Tag>
              <Text strong>{s.total_score} 分</Text>
              {s.opinion && <Text type="secondary">（{s.opinion}）</Text>}
            </Paragraph>
          ))}

          {hasAppeal && appeal && (
            <>
              <Divider titlePlacement="left" plain style={{ fontSize: 13 }}>
                员工异议
              </Divider>
              <Paragraph style={{ marginBottom: 8, fontSize: 13 }}>
                <Text type="secondary">异议人：{appeal.appellant_name || '-'}</Text>
                <br />
                <Text>{appeal.reason}</Text>
              </Paragraph>

              <Divider titlePlacement="left" plain style={{ fontSize: 13 }}>
                AI 中立审查意见
              </Divider>
              {appeal.ai_status === 'not_configured' && <AiNotConfiguredCard />}
              {appeal.ai_status === 'hidden' && (
                <Alert type="info" message="AI审查意见仅监察主任及以上可见" />
              )}
              {(appeal.ai_opinions || []).length === 0 &&
                appeal.ai_status !== 'not_configured' &&
                appeal.ai_status !== 'hidden' && (
                  <Alert
                    type="info"
                    message="AI 审查进行中或暂无意见，可稍后刷新查看；不影响裁定操作。"
                  />
                )}
              {(appeal.ai_opinions || []).map((op) => (
                <AiOpinionCard key={op.id} opinion={op} />
              ))}

              {(appeal.regulator_comment || appeal.group_director_comment) && (
                <>
                  <Divider titlePlacement="left" plain style={{ fontSize: 13 }}>
                    补充意见
                  </Divider>
                  {appeal.regulator_comment && (
                    <Paragraph style={{ fontSize: 13, marginBottom: 4 }}>
                      <Tag color="blue">规管</Tag>
                      {appeal.regulator_comment}
                    </Paragraph>
                  )}
                  {appeal.group_director_comment && (
                    <Paragraph style={{ fontSize: 13, marginBottom: 4 }}>
                      <Tag color="purple">集团总监</Tag>
                      {appeal.group_director_comment}
                    </Paragraph>
                  )}
                </>
              )}
            </>
          )}

          <Divider titlePlacement="left" plain style={{ fontSize: 13 }}>
            裁定操作（代录总裁线下裁定结果）
          </Divider>
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Space>
              <Button
                type={rulingAction === 'maintain' ? 'primary' : 'default'}
                onClick={() => setRulingAction('maintain')}
              >
                维持原评分（{finalScore ?? '-'} 分）
              </Button>
              <Button
                type={rulingAction === 'adjust' ? 'primary' : 'default'}
                danger={rulingAction === 'adjust'}
                onClick={() => setRulingAction('adjust')}
              >
                调整分数
              </Button>
            </Space>

            {rulingAction === 'adjust' && (
              <Space wrap>
                <Text>调整后分数：</Text>
                <Select
                  style={{ width: 120 }}
                  placeholder="选择档位"
                  value={adjustedScore}
                  onChange={setAdjustedScore}
                  options={SCORE_TIERS.map((t) => ({ value: t, label: `${t} 分` }))}
                />
              </Space>
            )}

            <Input.TextArea
              rows={3}
              placeholder={
                rulingAction === 'adjust'
                  ? '裁定意见（必填）：请填写总裁裁定说明'
                  : '裁定意见（选填）：如总裁有批示可在此记录'
              }
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              maxLength={500}
              showCount
            />
          </Space>
        </>
      )}
    </Modal>
  );
};

export default RulingModal;

/** 解析 ruling_result JSON（详情页显示用） */
export function parseRulingResult(raw?: string | null): RulingResult | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as RulingResult;
  } catch {
    return null;
  }
}
