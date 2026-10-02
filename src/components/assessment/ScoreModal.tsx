import React, { useEffect, useState } from 'react';
import { Modal, Radio, Input, Button, Select, InputNumber, Space, Typography, Divider, message, Spin, Tag } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { SCORE_TIERS, SCORE_LEVEL_LABELS } from '../../types';
import type { AssessmentAttachment, ScoreParticipant, AssessmentDetail, AssessmentScore } from '../../types';
import { assessmentApi, userApi } from '../../services/api';
import AttachmentUpload from './AttachmentUpload';

const { Text } = Typography;
const { TextArea } = Input;

interface Props {
  open: boolean;
  assessmentId: number | null;
  workItemTitle?: string;
  levelLabel?: string;
  onCancel: () => void;
  onSuccess: () => void;
}

interface ParticipantRow {
  key: number;
  user_id?: number;
  score?: number;
}

/**
 * 评分弹窗：总分档位(1/5/10/20/30) + 参与人分配(可选，分配和须等于总分) + 评分理由 + 凭证上传
 */
const ScoreModal: React.FC<Props> = ({ open, assessmentId, workItemTitle, levelLabel, onCancel, onSuccess }) => {
  const [totalScore, setTotalScore] = useState<number | null>(null);
  const [opinion, setOpinion] = useState('');
  const [participants, setParticipants] = useState<ParticipantRow[]>([]);
  const [attachments, setAttachments] = useState<AssessmentAttachment[]>([]);
  const [userOptions, setUserOptions] = useState<Array<{ id: number; real_name: string; username: string }>>([]);
  const [submitting, setSubmitting] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [previousScores, setPreviousScores] = useState<AssessmentScore[]>([]);
  let keySeed = React.useRef(0);

  useEffect(() => {
    if (open && assessmentId) {
      setTotalScore(null);
      setOpinion('');
      setParticipants([]);
      setAttachments([]);
      setPreviousScores([]);
      userApi.listBrief().then(setUserOptions).catch(() => {});
      // 拉取详情获取历史评分记录
      setDetailLoading(true);
      assessmentApi.detail(assessmentId)
        .then((detail: AssessmentDetail) => {
          setPreviousScores(detail.scores || []);
        })
        .catch(() => {})
        .finally(() => setDetailLoading(false));
    }
  }, [open, assessmentId]);

  const allocatedSum = participants.reduce((s, p) => s + (p.score || 0), 0);
  const hasParticipants = participants.length > 0;
  const sumMismatch = hasParticipants && totalScore !== null && Math.abs(allocatedSum - totalScore) > 0.01;

  const addParticipant = () => {
    keySeed.current += 1;
    setParticipants([...participants, { key: keySeed.current }]);
  };

  const updateParticipant = (key: number, patch: Partial<ParticipantRow>) => {
    setParticipants(participants.map((p) => (p.key === key ? { ...p, ...patch } : p)));
  };

  const removeParticipant = (key: number) => {
    setParticipants(participants.filter((p) => p.key !== key));
  };

  const handleSubmit = async () => {
    if (!assessmentId) return;
    if (totalScore === null) {
      message.warning('请选择总分');
      return;
    }
    if (hasParticipants) {
      for (const p of participants) {
        if (!p.user_id) {
          message.warning('请选择参与人');
          return;
        }
        if (p.score === undefined || p.score === null || p.score <= 0) {
          message.warning('请填写参与人分配分数（须大于0）');
          return;
        }
      }
      const ids = participants.map((p) => p.user_id);
      if (new Set(ids).size !== ids.length) {
        message.warning('参与人不能重复');
        return;
      }
      if (Math.abs(allocatedSum - totalScore) > 0.01) {
        message.warning(`参与人分配总和（${allocatedSum}）必须等于总分（${totalScore}）`);
        return;
      }
    }
    setSubmitting(true);
    try {
      const payload: any = {
        total_score: totalScore,
        opinion: opinion.trim() || undefined,
        attachments: attachments.length > 0 ? attachments : undefined,
      };
      if (hasParticipants) {
        payload.participants = participants.map((p): ScoreParticipant => ({
          user_id: p.user_id!,
          score: p.score!,
        }));
      }
      await assessmentApi.submitScore(assessmentId, payload);
      message.success('评分提交成功');
      onSuccess();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '评分提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={`评分${levelLabel ? `（${levelLabel}）` : ''}${workItemTitle ? ` - ${workItemTitle}` : ''}`}
      open={open}
      onCancel={onCancel}
      onOk={handleSubmit}
      confirmLoading={submitting}
      okText="提交评分"
      cancelText="取消"
      width={640}
      destroyOnClose
    >
      <div style={{ marginTop: 8 }}>
        {/* 历史评分记录 */}
        {previousScores.length > 0 && (
          <>
            <Text strong>历史评分</Text>
            <div style={{ marginTop: 8, marginBottom: 8 }}>
              <Spin spinning={detailLoading}>
                {previousScores.map((s) => (
                  <div
                    key={s.id}
                    style={{
                      padding: '8px 12px',
                      marginBottom: 6,
                      background: '#fafafa',
                      borderRadius: 4,
                      border: '1px solid #eee',
                    }}
                  >
                    <Space>
                      <Tag color="blue">{SCORE_LEVEL_LABELS[s.level] || s.level}</Tag>
                      <Text strong>{s.total_score} 分</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        评分人：{s.scorer_name || '-'}
                      </Text>
                      {s.submitted_at && (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {new Date(s.submitted_at).toLocaleString('zh-CN', { hour12: false })}
                        </Text>
                      )}
                    </Space>
                    {s.opinion && (
                      <div style={{ marginTop: 4, fontSize: 12, color: '#666' }}>
                        理由：{s.opinion}
                      </div>
                    )}
                    {s.participants && s.participants.length > 0 && (
                      <div style={{ marginTop: 4, fontSize: 12, color: '#888' }}>
                        参与人分配：{s.participants.map((p) => `${p.user_name || '-'}(${p.score}分)`).join('、')}
                      </div>
                    )}
                  </div>
                ))}
              </Spin>
            </div>
            <Divider style={{ margin: '16px 0' }} />
          </>
        )}

        <Text strong>总分</Text>
        <div style={{ marginTop: 8 }}>
          <Radio.Group
            value={totalScore}
            onChange={(e) => setTotalScore(e.target.value)}
          >
            {SCORE_TIERS.map((t) => (
              <Radio.Button key={t} value={t}>{t} 分</Radio.Button>
            ))}
          </Radio.Group>
        </div>

        <Divider style={{ margin: '16px 0' }} />

        <Space style={{ marginBottom: 8 }}>
          <Text strong>参与人分配</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>（可选；如填写，分配总和须等于总分）</Text>
          <Button size="small" icon={<PlusOutlined />} onClick={addParticipant}>添加参与人</Button>
        </Space>
        {participants.map((p) => (
          <Space key={p.key} style={{ display: 'flex', marginBottom: 8 }} align="center">
            <Select
              style={{ width: 220 }}
              placeholder="选择参与人"
              showSearch
              optionFilterProp="label"
              value={p.user_id}
              onChange={(v) => updateParticipant(p.key, { user_id: v })}
              options={userOptions.map((u) => ({
                value: u.id,
                label: `${u.real_name || u.username}`,
              }))}
            />
            <InputNumber
              style={{ width: 120 }}
              placeholder="分配分数"
              min={0.01}
              step={1}
              value={p.score}
              onChange={(v) => updateParticipant(p.key, { score: v ?? undefined })}
            />
            <Button type="text" danger icon={<DeleteOutlined />} onClick={() => removeParticipant(p.key)} />
          </Space>
        ))}
        {hasParticipants && totalScore !== null && (
          <div style={{ marginTop: 4 }}>
            <Text type={sumMismatch ? 'danger' : 'success'} style={{ fontSize: 12 }}>
              已分配 {allocatedSum} / {totalScore} 分{sumMismatch ? '（须相等）' : ' ✓'}
            </Text>
          </div>
        )}

        <Divider style={{ margin: '16px 0' }} />

        <Text strong>评分理由</Text>
        <TextArea
          style={{ marginTop: 8 }}
          rows={3}
          value={opinion}
          onChange={(e) => setOpinion(e.target.value)}
          placeholder="请填写评分理由或意见（可选）"
          maxLength={1000}
        />

        <Divider style={{ margin: '16px 0' }} />

        <Text strong>评分凭证</Text>
        <div style={{ marginTop: 8 }}>
          {assessmentId && (
            <AttachmentUpload
              assessmentId={assessmentId}
              uploadType="scoring"
              value={attachments}
              onChange={setAttachments}
            />
          )}
        </div>
      </div>
    </Modal>
  );
};

export default ScoreModal;
