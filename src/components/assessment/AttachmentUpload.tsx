import React, { useState } from 'react';
import { Upload, Button, Input, List, Image, Typography, message, Space, Popconfirm } from 'antd';
import { UploadOutlined, DeleteOutlined, FileTextOutlined, PlusOutlined } from '@ant-design/icons';
import type { AssessmentAttachment } from '../../types';
import { assessmentApi } from '../../services/api';

const { Text } = Typography;
const { TextArea } = Input;

interface Props {
  assessmentId: number;
  uploadType: 'scoring' | 'supplement' | 'appeal';
  value: AssessmentAttachment[];
  onChange: (list: AssessmentAttachment[]) => void;
}

/**
 * 凭证上传组件：支持图片上传（≤10MB）+ 文字凭证
 * 图片立即上传到服务器拿到 file_path，文字凭证本地暂存，随表单一起提交
 */
const AttachmentUpload: React.FC<Props> = ({ assessmentId, uploadType, value, onChange }) => {
  const [uploading, setUploading] = useState(false);
  const [textInput, setTextInput] = useState('');
  const [showTextInput, setShowTextInput] = useState(false);

  const handleUpload = async (file: File) => {
    if (!file.type.startsWith('image/')) {
      message.error('仅支持上传图片文件');
      return false;
    }
    if (file.size > 10 * 1024 * 1024) {
      message.error('图片大小不能超过 10MB');
      return false;
    }
    setUploading(true);
    try {
      const res = await assessmentApi.uploadAttachment(assessmentId, uploadType, file);
      onChange([...value, {
        file_type: 'image',
        file_name: res.file_name,
        file_path: res.file_path,
      }]);
      message.success('图片上传成功');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '图片上传失败');
    } finally {
      setUploading(false);
    }
    return false; // 阻止 antd 默认上传
  };

  const handleAddText = () => {
    const content = textInput.trim();
    if (!content) {
      message.warning('请输入文字凭证内容');
      return;
    }
    onChange([...value, { file_type: 'text', content }]);
    setTextInput('');
    setShowTextInput(false);
  };

  const handleRemove = (index: number) => {
    const next = value.slice();
    next.splice(index, 1);
    onChange(next);
  };

  const renderItem = (item: AssessmentAttachment, index: number) => {
    if (item.file_type === 'image' && item.file_path) {
      return (
        <List.Item
          actions={[
            <Popconfirm key="del" title="删除该凭证？" onConfirm={() => handleRemove(index)}>
              <Button type="text" danger size="small" icon={<DeleteOutlined />} />
            </Popconfirm>,
          ]}
        >
          <Space>
            <Image src={item.file_path} width={48} height={48} style={{ objectFit: 'cover', borderRadius: 4 }} />
            <Text style={{ maxWidth: 240 }} ellipsis>{item.file_name || '图片凭证'}</Text>
          </Space>
        </List.Item>
      );
    }
    return (
      <List.Item
        actions={[
          <Popconfirm key="del" title="删除该凭证？" onConfirm={() => handleRemove(index)}>
            <Button type="text" danger size="small" icon={<DeleteOutlined />} />
          </Popconfirm>,
        ]}
      >
        <Space align="start">
          <FileTextOutlined style={{ marginTop: 4 }} />
          <Text style={{ maxWidth: 360, whiteSpace: 'pre-wrap' }}>{item.content}</Text>
        </Space>
      </List.Item>
    );
  };

  return (
    <div>
      <Space style={{ marginBottom: 8 }}>
        <Upload
          accept="image/*"
          showUploadList={false}
          beforeUpload={handleUpload}
          disabled={uploading}
        >
          <Button icon={<UploadOutlined />} loading={uploading} size="small">上传图片</Button>
        </Upload>
        <Button icon={<PlusOutlined />} size="small" onClick={() => setShowTextInput(!showTextInput)}>
          添加文字凭证
        </Button>
      </Space>
      {showTextInput && (
        <div style={{ marginBottom: 8 }}>
          <TextArea
            rows={3}
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="输入文字凭证内容，如链接、说明等"
            maxLength={2000}
          />
          <Space style={{ marginTop: 4 }}>
            <Button type="primary" size="small" onClick={handleAddText}>添加</Button>
            <Button size="small" onClick={() => { setShowTextInput(false); setTextInput(''); }}>取消</Button>
          </Space>
        </div>
      )}
      {value.length > 0 && (
        <List
          size="small"
          bordered
          dataSource={value}
          renderItem={renderItem}
          style={{ background: '#fafafa' }}
        />
      )}
    </div>
  );
};

export default AttachmentUpload;
