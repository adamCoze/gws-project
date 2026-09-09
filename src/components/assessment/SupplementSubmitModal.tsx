import React, { useEffect, useState } from 'react';
import { Modal, Input, Typography, message, Alert } from 'antd';
import type { AssessmentAttachment, SupplementRequest } from '../../types';
import { assessmentApi } from '../../services/api';
import AttachmentUpload from './AttachmentUpload';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

interface Props {
  open: boolean;
  assessmentId: number | null;
  request: SupplementRequest | null;
  onCancel: () => void;
  onSuccess: () => void;
}

/**
 * 补充凭证提交弹窗：责任人针对评分人发起的补充凭证请求提交说明与凭证
 */
const SupplementSubmitModal: React.FC<Props> = ({ open, assessmentId, request, onCancel, onSuccess }) => {
  const [response, setResponse] = useState('');
  const [attachments, setAttachments] = useState<AssessmentAttachment[]>([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setResponse('');
      setAttachments([]);
    }
  }, [open, request?.id]);

  const handleSubmit = async () => {
    if (!assessmentId || !request) return;
    if (!response.trim() && attachments.length === 0) {
      message.warning('请填写补充说明或上传凭证');
      return;
    }
    setSubmitting(true);
    try {
      await assessmentApi.submitSupplement(assessmentId, {
        supplement_request_id: request.id,
        response: response.trim() || undefined,
        attachments: attachments.length > 0 ? attachments : undefined,
      });
      message.success('补充凭证提交成功');
      onSuccess();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="提交补充凭证"
      open={open}
      onCancel={onCancel}
      onOk={handleSubmit}
      confirmLoading={submitting}
      okText="提交"
      cancelText="取消"
      width={600}
      destroyOnClose
    >
      {request && (
        <Alert
          style={{ marginBottom: 16 }}
          type="info"
          showIcon
          message={`${request.requester_name || '评分人'} 要求补充凭证`}
          description={request.note ? <Paragraph style={{ marginBottom: 0 }}>{request.note}</Paragraph> : undefined}
        />
      )}
      <Text strong>补充说明</Text>
      <TextArea
        style={{ marginTop: 8, marginBottom: 16 }}
        rows={4}
        value={response}
        onChange={(e) => setResponse(e.target.value)}
        placeholder="请填写补充说明"
        maxLength={2000}
      />
      <Text strong>补充凭证</Text>
      <div style={{ marginTop: 8 }}>
        {assessmentId && (
          <AttachmentUpload
            assessmentId={assessmentId}
            uploadType="supplement"
            value={attachments}
            onChange={setAttachments}
          />
        )}
      </div>
    </Modal>
  );
};

export default SupplementSubmitModal;
