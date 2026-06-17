import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, DatePicker, Select, Space, Typography, message, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { holidayApi } from '../../services/api';
import type { Holiday } from '../../types';
import dayjs from 'dayjs';

const { Title } = Typography;

const HolidayConfigPage: React.FC = () => {
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Holiday | null>(null);
  const [selectedYear, setSelectedYear] = useState<number>(dayjs().year());
  const [form] = Form.useForm();

  useEffect(() => { loadHolidays(); }, [selectedYear]);

  const loadHolidays = async () => {
    setLoading(true);
    try {
      const data = await holidayApi.list(selectedYear);
      setHolidays(data);
    } catch { message.error('加载节假日失败'); }
    finally { setLoading(false); }
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      const data = { ...values, date: values.date.format('YYYY-MM-DD'), year: values.date.year() };
      if (editing) { await holidayApi.update(editing.id, data); message.success('更新成功'); }
      else { await holidayApi.create(data); message.success('创建成功'); }
      setModalOpen(false); form.resetFields(); setEditing(null); loadHolidays();
    } catch { /* validation */ }
  };

  const handleDelete = async (id: number) => {
    try { await holidayApi.delete(id); message.success('删除成功'); loadHolidays(); } catch { message.error('删除失败'); }
  };

  const yearOptions = Array.from({ length: 5 }, (_, i) => dayjs().year() - 2 + i).map((y) => ({ value: y, label: `${y}年` }));

  const columns: ColumnsType<Holiday> = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 200 },
    { title: '日期', dataIndex: 'date', key: 'date', width: 150, render: (v: string) => dayjs(v).format('YYYY-MM-DD') },
    { title: '年份', dataIndex: 'year', key: 'year', width: 100 },
    {
      title: '操作', key: 'action', width: 150,
      render: (_: unknown, record: Holiday) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => { setEditing(record); form.setFieldsValue({ ...record, date: dayjs(record.date) }); setModalOpen(true); }}>编辑</Button>
          <Popconfirm title="确认删除?" onConfirm={() => handleDelete(record.id)}><Button size="small" danger icon={<DeleteOutlined />}>删除</Button></Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={4} style={{ margin: 0 }}>节假日配置</Title>
        <Space>
          <Select value={selectedYear} onChange={setSelectedYear} options={yearOptions} style={{ width: 120 }} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true); }}>新增节假日</Button>
        </Space>
      </div>
      <Table columns={columns} dataSource={holidays} rowKey="id" loading={loading} pagination={{ pageSize: 20 }} />
      <Modal title={editing ? '编辑节假日' : '新增节假日'} open={modalOpen} onOk={handleSave} onCancel={() => setModalOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input placeholder="如：国庆节" /></Form.Item>
          <Form.Item name="date" label="日期" rules={[{ required: true }]}><DatePicker style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>
    </Space>
  );
};

export default HolidayConfigPage;
