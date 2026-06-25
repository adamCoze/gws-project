import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, InputNumber, Switch, Space, Typography, message, Popconfirm, Tag, Divider } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { emailConfigApi } from '../../services/api';
import type { EmailConfig } from '../../types';
import { formatUTCDate } from '../../utils/date';
import dayjs from 'dayjs';

const { Title } = Typography;

const EmailConfigPage: React.FC = () => {
  const [configs, setConfigs] = useState<EmailConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<EmailConfig | null>(null);
  const [form] = Form.useForm();

  useEffect(() => { loadConfigs(); }, []);

  const loadConfigs = async () => {
    setLoading(true);
    try {
      const data = await emailConfigApi.list();
      setConfigs(data);
    } catch { message.error('加载配置失败'); }
    finally { setLoading(false); }
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      if (editing) { await emailConfigApi.update(editing.id, values); message.success('更新成功'); }
      else { await emailConfigApi.create(values); message.success('创建成功'); }
      setModalOpen(false); form.resetFields(); setEditing(null); loadConfigs();
    } catch { /* validation */ }
  };

  const handleDelete = async (id: number) => {
    try { await emailConfigApi.delete(id); message.success('删除成功'); loadConfigs(); } catch { message.error('删除失败'); }
  };

  const columns: ColumnsType<EmailConfig> = [
    { title: '邮箱地址', dataIndex: 'email_address', key: 'email_address', width: 200 },
    { title: 'IMAP', key: 'imap', width: 200, render: (_: unknown, r: EmailConfig) => `${r.imap_host}:${r.imap_port}` },
    { title: '用户名', dataIndex: 'username', key: 'username', width: 150 },
    { title: '状态', dataIndex: 'is_active', key: 'is_active', width: 70, render: (v: boolean) => v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag> },
    { title: '上次检查', dataIndex: 'last_check_at', key: 'last_check_at', width: 160, render: (v: string) => v ? formatUTCDate(v, 'YYYY-MM-DD HH:mm') : '-' },
    {
      title: '操作', key: 'action', width: 150,
      render: (_: unknown, record: EmailConfig) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => { setEditing(record); form.setFieldsValue(record); setModalOpen(true); }}>编辑</Button>
          <Popconfirm title="确认删除?" onConfirm={() => handleDelete(record.id)}><Button size="small" danger icon={<DeleteOutlined />}>删除</Button></Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={4} style={{ margin: 0 }}>邮箱配置</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true); }}>新增配置</Button>
      </div>
      <Table columns={columns} dataSource={configs} rowKey="id" loading={loading} pagination={{ pageSize: 10 }} />
      <Modal title={editing ? '编辑邮箱配置' : '新增邮箱配置'} open={modalOpen} onOk={handleSave} onCancel={() => setModalOpen(false)} destroyOnClose width={500}>
        <Form form={form} layout="vertical">
          <Form.Item name="email_address" label="邮箱地址" rules={[{ required: true, type: 'email' }]}><Input /></Form.Item>
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}><Input /></Form.Item>
          {!editing && <Form.Item name="password" label="密码" rules={[{ required: true }]}><Input.Password /></Form.Item>}
          <Divider>IMAP 配置</Divider>
          <Space size="large" style={{ width: '100%' }}>
            <Form.Item name="imap_host" label="IMAP主机" rules={[{ required: true }]} initialValue="imap.qiye.aliyun.com"><Input style={{ width: 220 }} /></Form.Item>
            <Form.Item name="imap_port" label="IMAP端口" rules={[{ required: true }]} initialValue={993}><InputNumber min={1} max={65535} style={{ width: 100 }} /></Form.Item>
          </Space>
          <Form.Item name="is_active" label="启用" valuePropName="checked" initialValue={true}><Switch /></Form.Item>
        </Form>
      </Modal>
    </Space>
  );
};

export default EmailConfigPage;
