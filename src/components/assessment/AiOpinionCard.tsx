import { Card, Tag, Spin, Typography, Space } from 'antd';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  QuestionCircleOutlined,
  CloseCircleOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import type { AiOpinion } from '../../types';
import { AI_CONCLUSION_LABELS } from '../../types';

const { Text, Paragraph } = Typography;

/**
 * AI 中立审查意见卡片
 * - conclusion: maintain 建议维持（绿）/ review 建议复核（橙）/ undetermined 无法判断（灰）
 * - status: processing 审查中 / failed 生成失败
 */
export const AiOpinionCard: React.FC<{ opinion: AiOpinion }> = ({ opinion }) => {
  const conclusionMeta: Record<string, { color: string; icon: React.ReactNode }> = {
    maintain: { color: 'green', icon: <CheckCircleOutlined /> },
    review: { color: 'orange', icon: <ExclamationCircleOutlined /> },
    undetermined: { color: 'default', icon: <QuestionCircleOutlined /> },
  };

  const meta = opinion.conclusion ? conclusionMeta[opinion.conclusion] : null;

  return (
    <Card
      size="small"
      style={{ marginBottom: 12 }}
      styles={{
        header: { background: '#f0f5ff', fontSize: 13 },
        body: { padding: '8px 12px' },
      }}
      title={
        <Space>
          <RobotOutlined style={{ color: '#5b8ff9' }} />
          <Text strong>{opinion.bot_name || `模型${opinion.bot_index}`}</Text>
          {opinion.status === 'processing' && <Tag color="processing">审查中</Tag>}
          {opinion.status === 'pending' && <Tag>排队中</Tag>}
          {opinion.status === 'failed' && <Tag color="error">生成失败</Tag>}
          {opinion.conclusion && (
            <Tag color={meta?.color} icon={meta?.icon}>
              {AI_CONCLUSION_LABELS[opinion.conclusion]}
            </Tag>
          )}
        </Space>
      }
    >
      {opinion.status === 'completed' && opinion.opinion && (
        <Paragraph
          style={{ marginBottom: 0, whiteSpace: 'pre-wrap', fontSize: 13 }}
        >
          {opinion.opinion}
        </Paragraph>
      )}
      {opinion.status === 'processing' && (
        <Space>
          <Spin size="small" />
          <Text type="secondary">模型正在分析材料，通常数分钟内完成…</Text>
        </Space>
      )}
      {opinion.status === 'pending' && (
        <Text type="secondary">等待模型开始分析…</Text>
      )}
      {opinion.status === 'failed' && (
        <Space>
          <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
          <Text type="secondary">
            {opinion.error_message || '模型未返回有效内容'}
          </Text>
        </Space>
      )}
    </Card>
  );
};

/**
 * 未接入模型占位卡片（bot 未配置时）
 */
export const AiNotConfiguredCard: React.FC = () => (
  <Card
    size="small"
    style={{ marginBottom: 12 }}
    styles={{ header: { background: '#f5f5f5', fontSize: 13 }, body: { padding: '8px 12px' } }}
    title={
      <Space>
        <RobotOutlined style={{ color: '#999' }} />
        <Text strong type="secondary">AI 中立审查</Text>
        <Tag>暂未接入模型</Tag>
      </Space>
    }
  >
    <Text type="secondary">
      审查模型尚未配置，本异议跳过 AI 审查，直接进入待裁定环节。
    </Text>
  </Card>
);

export default AiOpinionCard;
