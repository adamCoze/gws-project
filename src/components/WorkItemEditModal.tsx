import React, { useEffect, useState } from 'react';
import { Modal, Form, Input, Select, message } from 'antd';
import { workItemApi, departmentApi, userApi } from '../services/api';
import type { Department, WorkItem, WorkItemStatus as WorkItemStatusType } from '../types';
import { STATUS_LABELS } from '../types';

const { TextArea } = Input;

interface UserBrief {
  id: number;
  real_name: string;
  username: string;
  email_prefix: string;
}

interface Props {
  open: boolean;
  item: WorkItem | null;          // null = 新建
  onCancel: () => void;
  onSaved: () => void;            // 保存成功后回调（父页面刷新列表）
}

/**
 * 工作项编辑弹窗（全局复用：工作项管理页、待考核项目页等）
 * - 显示并允许修改主办人（sponsor_id）、负责人（assignee_id）
 * - 权限：所有登录用户均可更新（后端 update_work_item 无角色限制）
 */
const WorkItemEditModal: React.FC<Props> = ({ open, item, onCancel, onSaved }) => {
  const [form] = Form.useForm();
  const [departments, setDepartments] = useState<Department[]>([]);
  const [users, setUsers] = useState<UserBrief[]>([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    (async () => {
      try { setDepartments(await departmentApi.list()); } catch { /* 忽略 */ }
      try { setUsers(await userApi.listBrief()); } catch { /* 忽略 */ }
    })();
  }, [open]);

  useEffect(() => {
    if (open) {
      if (item) {
        form.setFieldsValue({
          ...item,
          department_id: item.department?.id ?? undefined,
          sponsor_id: item.sponsor?.id ?? undefined,
          assignee_id: item.assignee?.id ?? undefined,
        });
      } else {
        form.resetFields();
      }
    }
  }, [open, item, form]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      if (item) {
        await workItemApi.update(item.id, values);
        message.success('工作项已更新');
      } else {
        await workItemApi.create(values);
        message.success('工作项已创建');
      }
      onSaved();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (detail) message.error(typeof detail === 'string' ? detail : '操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  const statusOptions = (Object.entries(STATUS_LABELS) as [WorkItemStatusType, string][])
    .filter(([k]) => k !== 'overdue')
    .map(([k, v]) => ({ value: k, label: v }));

  return (
    <Modal
      title={item ? `编辑工作项 #${item.id}` : '新建工作项'}
      open={open}
      onOk={handleSubmit}
      onCancel={onCancel}
      confirmLoading={submitting}
      width={620}
      destroyOnClose
    >
      <Form form={form} layout="vertical">
        <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="content" label="内容"><TextArea rows={4} /></Form.Item>
        <Form.Item name="item_type" label="类型" initialValue="task">
          <Select options={[{ value: 'task', label: '任务' }, { value: 'cosign', label: '会签' }, { value: 'report', label: '汇报' }]} />
        </Form.Item>
        <Form.Item name="status" label="状态" initialValue="pending">
          <Select options={statusOptions} />
        </Form.Item>
        <Form.Item name="department_id" label="部门">
          <Select allowClear options={departments.map((d) => ({ value: d.id, label: d.name }))} />
        </Form.Item>
        <Form.Item name="sponsor_id" label="主办人">
          <Select allowClear showSearch optionFilterProp="label"
            options={users.map((u) => ({ value: u.id, label: u.real_name || u.username }))} />
        </Form.Item>
        <Form.Item name="assignee_id" label="负责人">
          <Select allowClear showSearch optionFilterProp="label"
            options={users.map((u) => ({ value: u.id, label: u.real_name || u.username }))} />
        </Form.Item>
        <Form.Item name="latest_progress" label="最新进展"><TextArea rows={2} /></Form.Item>
        <Form.Item name="is_confidential" label="是否机密" initialValue={false}>
          <Select options={[{ value: false, label: '否' }, { value: true, label: '是' }]} />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default WorkItemEditModal;
