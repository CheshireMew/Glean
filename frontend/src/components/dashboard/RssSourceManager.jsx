import React, { useMemo, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { Alert, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tag } from 'antd';
import { previewRssSource } from '../../api/config';

const parserOptions = [
    { value: 'generic', label: '标准 RSS/Atom' },
    { value: 'summary_source_link', label: '摘要里的来源链接' },
];

const defaultValues = {
    slug: '',
    display_name: '',
    feed_url: '',
    site_url: '',
    content_kind: 'article',
    parser_type: 'generic',
    default_limit: 20,
    default_interval: 240,
    enabled: true,
};

export default function RssSourceManager({ sources, contentKind, onCreate, onUpdate, onDelete }) {
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);
    const [saving, setSaving] = useState(false);
    const [form] = Form.useForm();
    const [preview, setPreview] = useState(null);
    const [previewError, setPreviewError] = useState('');
    const [previewLoading, setPreviewLoading] = useState(false);
    const previewRequest = useRef(0);
    const clearPreview = () => {
        previewRequest.current += 1;
        setPreview(null);
        setPreviewError('');
        setPreviewLoading(false);
    };
    const loadPreview = async () => {
        const requestId = ++previewRequest.current;
        setPreview(null);
        setPreviewError('');
        setPreviewLoading(true);
        try {
            const values = await form.validateFields(['feed_url', 'parser_type']);
            const response = await previewRssSource({ feed_url: values.feed_url, parser_type: values.parser_type, limit: 3 });
            if (requestId === previewRequest.current) setPreview(response.data);
        } catch (error) {
            if (requestId === previewRequest.current && !error?.errorFields) setPreviewError(error.message || '预览失败，请重试');
        } finally {
            if (requestId === previewRequest.current) setPreviewLoading(false);
        }
    };

    const visibleSources = useMemo(
        () => sources.filter((source) => source.content_kind === contentKind),
        [contentKind, sources],
    );

    const openCreate = () => {
        clearPreview();
        setEditing(null);
        form.setFieldsValue({ ...defaultValues, content_kind: contentKind });
        setOpen(true);
    };

    const openEdit = (source) => {
        clearPreview();
        setEditing(source);
        form.setFieldsValue({
            slug: source.slug,
            display_name: source.display_name,
            feed_url: source.feed_url,
            site_url: source.site_url,
            content_kind: source.content_kind,
            parser_type: source.parser_type,
            default_limit: source.default_limit,
            default_interval: source.default_interval,
            enabled: Boolean(source.enabled),
        });
        setOpen(true);
    };

    const closeModal = () => {
        clearPreview();
        setOpen(false);
        setEditing(null);
        form.resetFields();
    };

    const submit = async () => {
        const values = await form.validateFields();
        setSaving(true);
        try {
            if (editing) {
                await onUpdate(editing.id, values);
            } else {
                await onCreate(values);
            }
            closeModal();
        } finally {
            setSaving(false);
        }
    };

    const columns = [
        {
            title: '名称',
            dataIndex: 'display_name',
            key: 'display_name',
        },
        {
            title: '地址',
            dataIndex: 'feed_url',
            key: 'feed_url',
            render: (value) => <a href={value} target="_blank" rel="noreferrer">{value}</a>,
        },
        {
            title: '解析',
            dataIndex: 'parser_type',
            key: 'parser_type',
            render: (value) => parserOptions.find((option) => option.value === value)?.label || value,
        },
        {
            title: '状态',
            dataIndex: 'enabled',
            key: 'enabled',
            render: (enabled) => <Tag color={enabled ? 'success' : 'default'}>{enabled ? '启用' : '停用'}</Tag>,
        },
        {
            title: '操作',
            key: 'actions',
            render: (_, source) => (
                <Space>
                    <Button size="small" onClick={() => openEdit(source)}>编辑</Button>
                    <Popconfirm title="删除这个 RSS 源？" onConfirm={() => onDelete(source.id)}>
                        <Button size="small" danger>删除</Button>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <Card
            title="RSS 源"
            extra={<Button type="primary" onClick={openCreate}>新增 RSS 源</Button>}
            style={{ marginBottom: 16 }}
        >
            <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={visibleSources}
                columns={columns}
                locale={{ emptyText: '当前内容类型还没有 RSS 源' }}
            />

            <Modal
                open={open}
                title={editing ? '编辑 RSS 源' : '新增 RSS 源'}
                onOk={submit}
                onCancel={closeModal}
                confirmLoading={saving}
                width={760}
                destroyOnHidden
            >
                <Form form={form} layout="vertical" initialValues={{ ...defaultValues, content_kind: contentKind }} onValuesChange={(changed) => { if ('feed_url' in changed || 'parser_type' in changed) clearPreview(); }}>
                    <Form.Item name="display_name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
                        <Input />
                    </Form.Item>
                    <Form.Item name="slug" label="标识">
                        <Input placeholder="留空时按名称自动生成" />
                    </Form.Item>
                    <Form.Item name="feed_url" label="RSS 地址" rules={[{ required: true, message: '请输入 RSS 地址' }]}>
                        <Input />
                    </Form.Item>
                    <Form.Item name="site_url" label="站点地址" rules={[{ required: true, message: '请输入站点地址' }]}>
                        <Input />
                    </Form.Item>
                    <Form.Item name="content_kind" label="内容类型" rules={[{ required: true, message: '请选择内容类型' }]}>
                        <Select
                            options={[
                                { value: 'news', label: '快讯' },
                                { value: 'article', label: '文章' },
                            ]}
                        />
                    </Form.Item>
                    <Form.Item name="parser_type" label="解析方式" rules={[{ required: true, message: '请选择解析方式' }]}>
                        <Select options={parserOptions} />
                    </Form.Item>
                    <div style={{ marginBottom: 24 }}>
                        <Button onClick={() => void loadPreview()} loading={previewLoading}>预览内容</Button>
                        <p style={{ color: '#666' }}>先查看最近 3 条订阅内容。预览不会保存来源或触发审核、发布。</p>
                        {previewError && <Alert type="error" showIcon title={previewError} />}
                        {preview && <div aria-live="polite">
                            <Alert type="info" showIcon title={preview.notice} />
                            {preview.items.map((item, index) => <article key={`${item.url}-${index}`} style={{ marginTop: 16 }}>
                                <h4><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a></h4>
                                <p>{item.author} · {item.published_at} · <Tag>订阅源内容 · 全文状态未知</Tag></p>
                                <details>
                                    <summary>查看内容（{item.content.length} 字符）</summary>
                                    <div style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 360, overflowY: 'auto', padding: '12px 0' }}>{item.content || '订阅源未提供正文，请打开原文查看。'}</div>
                                </details>
                            </article>)}
                        </div>}
                    </div>
                    <Form.Item name="default_limit" label="默认条数" rules={[{ required: true, message: '请输入默认条数' }]}>
                        <InputNumber min={1} max={100} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="default_interval" label="默认频率(分钟)" rules={[{ required: true, message: '请输入默认频率' }]}>
                        <InputNumber min={5} max={10080} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="enabled" label="启用" valuePropName="checked">
                        <Switch />
                    </Form.Item>
                </Form>
            </Modal>
        </Card>
    );
}

RssSourceManager.propTypes = {
    sources: PropTypes.arrayOf(PropTypes.object).isRequired,
    contentKind: PropTypes.string.isRequired,
    onCreate: PropTypes.func.isRequired,
    onUpdate: PropTypes.func.isRequired,
    onDelete: PropTypes.func.isRequired,
};
