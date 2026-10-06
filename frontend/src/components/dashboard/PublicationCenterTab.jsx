import React, { useEffect, useState } from 'react';
import dayjs from 'dayjs';
import SafeReportPreview from './SafeReportPreview';
import {
    Alert, Button, Card, Checkbox, DatePicker, Form, Input, InputNumber, Modal, Select,
    Space, Switch, Table, Tabs, Tag, Typography, message,
} from 'antd';
import { EditOutlined, PlusOutlined, ReloadOutlined, SendOutlined } from '@ant-design/icons';

import {
    createPublicationDraft, createPublicationCorrection, getPublicationDraft,
    listPublicationCorrections, listPublicationDrafts, previewPublicationDraft,
    publishPublicationCorrection, publishPublicationDraft, updatePublicationDraft,
} from '../../api/editorial';
import {
    createAnalystSubscription, createPublicationChannel, deliverAnalystSubscriptions,
    listAnalystSubscriptions, listPublicationChannels, listPublications,
    testPublicationChannel, updateAnalystSubscription, updatePublication, updatePublicationChannel,
} from '../../api/publications';
import { formatLocalDateTime } from '../../utils/time';
import { retryDelivery } from '../../api/pipeline';

const CHANNEL_TYPES = [
    { value: 'telegram', label: 'Telegram' }, { value: 'email', label: '邮件' },
    { value: 'discord', label: 'Discord' }, { value: 'slack', label: 'Slack' },
    { value: 'webhook', label: 'Webhook' },
];
const MODES = [{ value: 'realtime', label: '实时' }, { value: 'digest', label: '摘要' }, { value: 'alert', label: '提醒' }];

function jsonText(value) { return JSON.stringify(value || {}, null, 2); }
function parseJson(value, label) {
    try { return JSON.parse(value || '{}'); } catch { throw new Error(`${label}必须是合法 JSON`); }
}

export default function PublicationCenterTab() {
    const [state, setState] = useState({ loading: true, error: '', publications: [], channels: [], drafts: [], corrections: [], subscriptions: [] });
    const [publicationForm] = Form.useForm();
    const [channelForm] = Form.useForm();
    const [draftForm] = Form.useForm();
    const [correctionForm] = Form.useForm();
    const [subscriptionForm] = Form.useForm();
    const [publicationEditing, setPublicationEditing] = useState(null);
    const [channelEditing, setChannelEditing] = useState(null);
    const [draftEditing, setDraftEditing] = useState(null);
    const [draftItems, setDraftItems] = useState([]);
    const [draftPreview, setDraftPreview] = useState(null);
    const [subscriptionEditing, setSubscriptionEditing] = useState(null);
    const [busy, setBusy] = useState('');
    const [correctionDeliveries, setCorrectionDeliveries] = useState({});

    const load = async () => {
        setState((current) => ({ ...current, loading: true, error: '' }));
        try {
            const [publications, channels, drafts, corrections, subscriptions] = await Promise.all([
                listPublications(), listPublicationChannels(), listPublicationDrafts(), listPublicationCorrections(), listAnalystSubscriptions(),
            ]);
            setState({ loading: false, error: '', publications: publications.data || [], channels: channels.data || [], drafts: drafts.data || [], corrections: corrections.data || [], subscriptions: subscriptions.data || [] });
            setCorrectionDeliveries((current) => {
                const next = { ...current };
                for (const correction of corrections.data || []) {
                    if (correction.delivery) next[correction.id] = correction.delivery;
                    else if (correction.published_at) delete next[correction.id];
                }
                return next;
            });
        } catch (error) {
            setState((current) => ({ ...current, loading: false, error: error.message || '发布中心加载失败' }));
        }
    };
    useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, []);

    const editPublication = (record) => {
        setPublicationEditing(record);
        publicationForm.setFieldsValue({
            ...record,
            target_keys: (record.targets || []).filter((item) => item.enabled).map((item) => `${item.channel_id}:${item.delivery_mode}`),
            template_json: jsonText(record.template),
        });
    };
    const savePublication = async () => {
        try {
            const values = await publicationForm.validateFields();
            const targets = (values.target_keys || []).map((key) => {
                const [channelId, deliveryMode] = key.split(':');
                return { channel_id: Number(channelId), delivery_mode: deliveryMode, enabled: true };
            });
            await updatePublication(publicationEditing.id, { ...values, template: parseJson(values.template_json, '模板'), targets, target_keys: undefined, template_json: undefined });
            message.success('发布频道已保存'); setPublicationEditing(null); await load();
        } catch (error) { if (!error?.errorFields) message.error(error.message || '保存失败'); }
    };

    const editChannel = (record = null) => {
        setChannelEditing(record || { id: null });
        channelForm.setFieldsValue(record ? { ...record, config_json: jsonText(record.config) } : { slug: '', name: '', channel_type: 'webhook', enabled: true, config_json: '{}' });
    };
    const saveChannel = async () => {
        try {
            const values = await channelForm.validateFields();
            const payload = { ...values, config: parseJson(values.config_json, '渠道配置') }; delete payload.config_json;
            if (channelEditing.id) await updatePublicationChannel(channelEditing.id, payload); else await createPublicationChannel(payload);
            message.success('投递渠道已保存'); setChannelEditing(null); await load();
        } catch (error) { if (!error?.errorFields) message.error(error.message || '保存失败'); }
    };
    const testChannel = async (id) => {
        setBusy(`channel:${id}`);
        try { const response = await testPublicationChannel(id); if (response.data.status !== 'sent') throw new Error(response.data.error || '测试消息未送达'); message.success('测试消息已送达'); }
        catch (error) { message.error(error.message || '渠道测试失败'); } finally { setBusy(''); }
    };

    const createDraft = () => {
        setDraftEditing({ id: null }); setDraftItems([]);
        draftForm.setFieldsValue({ publication_id: state.publications[0]?.id, title: '', content_type: state.publications[0]?.content_type || 'news', item_lines: '' });
    };
    const openDraft = async (record) => {
        setBusy(`draft-load:${record.id}`);
        try {
            const response = await getPublicationDraft(record.id); const detail = response.data;
            setDraftEditing(detail); setDraftItems(detail.items || []);
            draftForm.setFieldsValue({ title: detail.title, status: detail.status, scheduled_at: detail.scheduled_at ? dayjs(detail.scheduled_at) : null });
        } catch (error) { message.error(error.message || '草稿加载失败'); } finally { setBusy(''); }
    };
    const saveDraft = async () => {
        try {
            const values = await draftForm.validateFields();
            if (!draftEditing.id) {
                const publication = state.publications.find((item) => item.id === values.publication_id);
                const items = String(values.item_lines || '').split(/\r?\n/).filter(Boolean).map((line, position) => {
                    const [id, section = '其他'] = line.split('|');
                    if (!/^\d+$/.test(id.trim())) throw new Error(`第 ${position + 1} 行不是有效内容 ID`);
                    return { review_entry_id: Number(id.trim()), position, section: section.trim() || '其他', included: true, overrides: {} };
                });
                if (!items.length) throw new Error('至少填写一条内容 ID');
                await createPublicationDraft({ publication_id: values.publication_id, content_type: publication.content_type, title: values.title, items });
            } else {
                await updatePublicationDraft(draftEditing.id, {
                    title: values.title,
                    status: values.status === 'publishing' || values.status === 'published' ? undefined : values.status,
                    scheduled_at: values.scheduled_at?.toISOString(),
                    items: draftItems.map((item, position) => ({ review_entry_id: item.review_entry_id, position, section: item.section || '其他', included: item.included, overrides: item.overrides || {} })),
                });
            }
            message.success('草稿已保存'); setDraftEditing(null); await load();
        } catch (error) { if (!error?.errorFields) message.error(error.message || '草稿保存失败'); }
    };
    const publishDraft = async (id, websiteOnly = false) => {
        setBusy(`publish:${id}`);
        try { const response = await publishPublicationDraft(id, { website_only: websiteOnly }); message.success(response.data.status === 'published' ? (websiteOnly ? '已发布到网站' : '草稿已发布') : '已提交，仍有渠道待确认'); setDraftEditing(null); await load(); }
        catch (error) { message.error(error.message || '发布失败'); } finally { setBusy(''); }
    };
    const previewDraft = async (id) => {
        setBusy(`preview:${id}`);
        try {
            const response = await previewPublicationDraft(id);
            setDraftPreview(response.data);
        } catch (error) { message.error(error.message || '预览生成失败'); } finally { setBusy(''); }
    };
    const moveDraftItem = (index, delta) => setDraftItems((current) => {
        const next = [...current]; const target = index + delta; if (target < 0 || target >= next.length) return current;
        [next[index], next[target]] = [next[target], next[index]]; return next;
    });

    const createCorrection = async () => {
        try {
            const values = await correctionForm.validateFields();
            const targetValue = Number(values.target_id);
            await createPublicationCorrection({ correction_type: values.correction_type, message: values.message, [`${values.target_type}_id`]: targetValue });
            correctionForm.resetFields(); message.success('更正已创建'); await load();
        } catch (error) { if (!error?.errorFields) message.error(error.message || '更正创建失败'); }
    };
    const publishCorrection = async (id) => {
        setBusy(`correction:${id}`);
        try {
            const response = await publishPublicationCorrection(id);
            setCorrectionDeliveries((current) => ({ ...current, [id]: response.data }));
            if (response.data.status === 'published') message.success('更正已发布');
            else message.warning('更正仍有渠道未完成，请查看投递结果');
            await load();
        }
        catch (error) { message.error(error.message || '更正发送失败'); } finally { setBusy(''); }
    };
    const retryCorrection = (id, operation) => {
        const performRetry = async () => {
            setBusy(`correction:${id}`);
            try {
                await retryDelivery(operation.operation_key);
                const response = await publishPublicationCorrection(id);
                setCorrectionDeliveries((current) => ({ ...current, [id]: response.data }));
                if (response.data.status === 'published') message.success('更正已发布');
                else message.warning('仍有渠道未完成，请继续核对投递结果');
                await load();
            } catch (error) { message.error(error.message || '更正重试失败'); }
            finally { setBusy(''); }
        };
        if (operation.status === 'needs_attention') {
            Modal.confirm({
                title: '确认补发结果不确定的更正？',
                content: `请先检查 ${operation.channel_slug}：部分消息可能已经送达。确认需要补发后，只重试未完成的分段。`,
                okText: '确认补发', cancelText: '取消', onOk: performRetry,
            });
        } else void performRetry();
    };
    const editSubscription = (record = null) => {
        setSubscriptionEditing(record || { id: null });
        subscriptionForm.setFieldsValue(record ? { ...record } : { name: '', enabled: true, object_types: ['event', 'correction', 'entity', 'narrative', 'tag'], content_types: [], profile_slugs: [], batch_size: 50, start_from: 'now' });
    };
    const saveSubscription = async () => {
        try {
            const values = await subscriptionForm.validateFields();
            if (subscriptionEditing.id) {
                const payload = { ...values }; delete payload.start_from;
                await updateAnalystSubscription(subscriptionEditing.id, payload);
            } else await createAnalystSubscription(values);
            message.success('分析师变更订阅已保存'); setSubscriptionEditing(null); await load();
        } catch (error) { if (!error?.errorFields) message.error(error.message || '订阅保存失败'); }
    };
    const deliverSubscriptions = async () => {
        setBusy('subscription-deliver');
        try {
            const response = await deliverAnalystSubscriptions();
            const sent = (response.data.results || []).filter((item) => item.status === 'sent').length;
            message.success(`订阅检查完成，${sent} 个批次已送达`); await load();
        } catch (error) { message.error(error.message || '订阅投递失败'); } finally { setBusy(''); }
    };

    const publicationColumns = [
        { title: '发布频道', dataIndex: 'display_name', render: (_, row) => <><strong>{row.display_name}</strong><div><Typography.Text type="secondary">{row.profile_slug} · /{row.public_slug}</Typography.Text></div></> },
        { title: '类型', dataIndex: 'content_type', render: (value) => <Tag>{value === 'news' ? '快讯' : '文章'}</Tag> },
        { title: '公开', render: (_, row) => <Space><Tag color={row.is_public ? 'green' : 'default'}>{row.is_public ? '公开' : '内部'}</Tag>{row.rss_enabled && <Tag color="blue">RSS</Tag>}</Space> },
        { title: '频率', render: (_, row) => `${row.digest_frequency} · ${row.digest_time}` },
        { title: '目标', render: (_, row) => <Space wrap>{(row.targets || []).filter((item) => item.enabled).map((item) => <Tag key={`${item.channel_id}:${item.delivery_mode}`}>{item.channel_name}/{item.delivery_mode}</Tag>)}</Space> },
        { title: '操作', render: (_, row) => <Button icon={<EditOutlined />} onClick={() => editPublication(row)}>配置</Button> },
    ];
    const channelColumns = [
        { title: '渠道', render: (_, row) => <><strong>{row.name}</strong><div><Typography.Text type="secondary">{row.slug}</Typography.Text></div></> },
        { title: '类型', dataIndex: 'channel_type', render: (value) => <Tag color="blue">{value}</Tag> },
        { title: '状态', dataIndex: 'enabled', render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '停用'}</Tag> },
        { title: '操作', render: (_, row) => <Space><Button onClick={() => editChannel(row)}>编辑</Button><Button loading={busy === `channel:${row.id}`} onClick={() => testChannel(row.id)}>测试</Button></Space> },
    ];
    const draftColumns = [
        { title: '标题', render: (_, row) => <><strong>{row.title}</strong><div><Typography.Text type="secondary">{row.publication_name} · {row.item_count} 条</Typography.Text></div></> },
        { title: '状态', dataIndex: 'status', render: (value) => <Tag color={value === 'published' ? 'green' : value === 'publishing' ? 'orange' : value === 'scheduled' ? 'blue' : 'default'}>{value}</Tag> },
        { title: '计划时间', dataIndex: 'scheduled_at', render: (value) => value ? formatLocalDateTime(value) : '—' },
        { title: '操作', render: (_, row) => <Space wrap><Button loading={busy === `draft-load:${row.id}`} onClick={() => openDraft(row)}>查看</Button><Button loading={busy === `preview:${row.id}`} onClick={() => previewDraft(row.id)}>成稿预览</Button>{['draft', 'scheduled'].includes(row.status) && <Button loading={busy === `publish:${row.id}`} onClick={() => publishDraft(row.id, true)}>仅发布到网站</Button>}{row.status !== 'published' && row.status !== 'cancelled' && <Button type="primary" icon={<SendOutlined />} loading={busy === `publish:${row.id}`} onClick={() => publishDraft(row.id)}>发布/重试</Button>}</Space> },
    ];
    const correctionColumns = [
        { title: '类型', dataIndex: 'correction_type', render: (value) => <Tag color="red">{value}</Tag> },
        { title: '对象', render: (_, row) => row.report_title || row.entry_title || row.event_title || '—' },
        { title: '内容', dataIndex: 'message' },
        { title: '状态', render: (_, row) => {
            const delivery = correctionDeliveries[row.id];
            if (row.published_at || delivery?.status === 'published') return <Tag color="green">已发布</Tag>;
            if (!delivery) return <Tag>待发布</Tag>;
            return <Alert type="warning" showIcon title="更正尚未完整送达" description={<Space orientation="vertical">
                {(delivery.operations || []).map((operation) => <Space key={operation.operation_key} wrap>
                    <Typography.Text>{operation.channel_slug}</Typography.Text>
                    <Tag color={operation.status === 'sent' ? 'green' : operation.status === 'failed' ? 'red' : 'orange'}>
                        {operation.status === 'sent' ? '已送达' : operation.status === 'failed' ? '发送失败' : operation.status === 'needs_attention' ? '结果待确认' : '发送中'}
                        {` ${operation.sent_parts}/${operation.parts}`}
                    </Tag>
                    {operation.last_error && <Typography.Text type="secondary">{operation.last_error}</Typography.Text>}
                    {['failed', 'needs_attention'].includes(operation.status) && <Button size="small" loading={busy === `correction:${row.id}`} onClick={() => retryCorrection(row.id, operation)}>
                        {operation.status === 'needs_attention' ? '核对后确认补发' : '重试未完成部分'}
                    </Button>}
                </Space>)}
            </Space>} />;
        } },
        { title: '操作', render: (_, row) => !row.published_at && <Button loading={busy === `correction:${row.id}`} onClick={() => publishCorrection(row.id)}>发送更正</Button> },
    ];
    const subscriptionColumns = [
        { title: '订阅', render: (_, row) => <><strong>{row.name}</strong><div><Typography.Text type="secondary">{row.channel_name}</Typography.Text></div></> },
        { title: '对象', render: (_, row) => <Space wrap>{row.object_types.map((item) => <Tag key={item}>{item}</Tag>)}</Space> },
        { title: '过滤', render: (_, row) => <Typography.Text type="secondary">{row.content_types.length ? row.content_types.join('、') : '全部类型'}{row.profile_slugs.length ? ` · ${row.profile_slugs.join('、')}` : ''}</Typography.Text> },
        { title: '游标', dataIndex: 'cursor' },
        { title: '状态', dataIndex: 'enabled', render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '停用'}</Tag> },
        { title: '操作', render: (_, row) => <Button onClick={() => editSubscription(row)}>编辑</Button> },
    ];

    return <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {state.error && <Alert type="error" showIcon message={state.error} action={<Button onClick={load}>重试</Button>} />}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><div><Typography.Title level={3} style={{ margin: 0 }}>发布中心</Typography.Title><Typography.Text type="secondary">每个内容档案拥有独立公开流、RSS、排期和投递目标。</Typography.Text></div><Button icon={<ReloadOutlined />} loading={state.loading} onClick={load}>刷新</Button></div>
        <Tabs items={[
            { key: 'publications', label: '发布频道', children: <Table rowKey="id" loading={state.loading} dataSource={state.publications} columns={publicationColumns} pagination={false} scroll={{ x: 900 }} /> },
            { key: 'channels', label: '投递渠道', children: <Card extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => editChannel()}>新建渠道</Button>}><Table rowKey="id" dataSource={state.channels} columns={channelColumns} pagination={false} /></Card> },
            { key: 'drafts', label: '草稿与排期', children: <Card extra={<Button type="primary" icon={<PlusOutlined />} onClick={createDraft}>新建草稿</Button>}><Table rowKey="id" dataSource={state.drafts} columns={draftColumns} pagination={{ pageSize: 20 }} scroll={{ x: 850 }} /></Card> },
            { key: 'corrections', label: '更正', children: <Space direction="vertical" style={{ width: '100%' }}><Card title="创建更正"><Form form={correctionForm} layout="inline" initialValues={{ correction_type: 'correction', target_type: 'event' }}><Form.Item name="correction_type" rules={[{ required: true }]}><Select style={{ width: 120 }} options={[{ value: 'correction', label: '更正' }, { value: 'clarification', label: '澄清' }, { value: 'retraction', label: '撤回' }]} /></Form.Item><Form.Item name="target_type" rules={[{ required: true }]}><Select style={{ width: 120 }} options={[{ value: 'event', label: '事件 ID' }, { value: 'review_entry', label: '内容 ID' }, { value: 'report', label: '日报 ID' }]} /></Form.Item><Form.Item name="target_id" rules={[{ required: true }]}><InputNumber min={1} placeholder="对象 ID" /></Form.Item><Form.Item name="message" style={{ minWidth: 320, flex: 1 }} rules={[{ required: true }]}><Input placeholder="说明错误内容、正确事实和影响范围" /></Form.Item><Button type="primary" onClick={createCorrection}>创建</Button></Form></Card><Table rowKey="id" dataSource={state.corrections} columns={correctionColumns} pagination={{ pageSize: 20 }} /></Space> },
            { key: 'subscriptions', label: '分析师变更订阅', children: <Card extra={<Space><Button loading={busy === 'subscription-deliver'} onClick={deliverSubscriptions}>立即检查并投递</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => editSubscription()}>新建订阅</Button></Space>}><Alert type="info" showIcon message="以结构化 JSON 向 Webhook 推送事件、更正、实体、叙事和标签变更；只有确认送达后才推进游标。" style={{ marginBottom: 16 }} /><Table rowKey="id" dataSource={state.subscriptions} columns={subscriptionColumns} pagination={false} scroll={{ x: 900 }} /></Card> },
        ]} />

        <Modal title="配置发布频道" open={Boolean(publicationEditing)} onCancel={() => setPublicationEditing(null)} onOk={savePublication} width={760} destroyOnClose>
            <Form form={publicationForm} layout="vertical"><Space wrap style={{ width: '100%' }} align="start"><Form.Item name="display_name" label="显示名称" rules={[{ required: true }]}><Input style={{ width: 220 }} /></Form.Item><Form.Item name="public_slug" label="公开路径" rules={[{ required: true }]}><Input addonBefore="/" style={{ width: 220 }} /></Form.Item><Form.Item name="digest_frequency" label="摘要频率"><Select style={{ width: 140 }} options={[{ value: 'realtime', label: '只实时' }, { value: 'daily', label: '每日' }, { value: 'weekly', label: '每周' }, { value: 'manual', label: '手工' }]} /></Form.Item><Form.Item name="digest_time" label="发送时间"><Input style={{ width: 100 }} placeholder="09:00" /></Form.Item></Space><Form.Item name="description" label="频道说明"><Input.TextArea rows={2} /></Form.Item><Space><Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item><Form.Item name="is_public" label="公开前台" valuePropName="checked"><Switch /></Form.Item><Form.Item name="rss_enabled" label="开放 RSS" valuePropName="checked"><Switch /></Form.Item></Space><Form.Item name="timezone" label="时区"><Input placeholder="留空则使用系统时区，例如 Asia/Shanghai" /></Form.Item><Form.Item name="target_keys" label="投递目标"><Checkbox.Group options={state.channels.flatMap((channel) => MODES.map((mode) => ({ value: `${channel.id}:${mode.value}`, label: `${channel.name} / ${mode.label}` })))} /></Form.Item><Form.Item name="template_json" label="模板参数（JSON）" extra="支持 title_prefix、title_suffix、intro、footer；每周摘要可用 weekday（0 表示周一）。"><Input.TextArea rows={5} className="font-mono" /></Form.Item></Form>
        </Modal>
        <Modal title={channelEditing?.id ? '编辑投递渠道' : '新建投递渠道'} open={Boolean(channelEditing)} onCancel={() => setChannelEditing(null)} onOk={saveChannel} width={680} destroyOnClose><Alert type="info" showIcon message="Telegram 配置 bot_token/chat_id；Webhook、Discord、Slack 配置 url；邮件配置 host、port、from_address、to_addresses、username、password、use_tls/use_ssl。" style={{ marginBottom: 16 }} /><Form form={channelForm} layout="vertical"><Space wrap><Form.Item name="slug" label="渠道标识" rules={[{ required: true }]}><Input style={{ width: 190 }} /></Form.Item><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input style={{ width: 220 }} /></Form.Item><Form.Item name="channel_type" label="类型" rules={[{ required: true }]}><Select style={{ width: 140 }} options={CHANNEL_TYPES} /></Form.Item><Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item></Space><Form.Item name="config_json" label="渠道配置（JSON）" rules={[{ required: true }]}><Input.TextArea rows={10} className="font-mono" /></Form.Item></Form></Modal>
        <Modal title={draftEditing?.id ? `编辑草稿 #${draftEditing.id}` : '新建发布草稿'} open={Boolean(draftEditing)} onCancel={() => setDraftEditing(null)} onOk={saveDraft} width={900} destroyOnClose footer={draftEditing?.status === 'published' ? [<Button key="close" onClick={() => setDraftEditing(null)}>关闭</Button>] : undefined}><Form form={draftForm} layout="vertical"><Form.Item name="publication_id" label="发布频道" hidden={Boolean(draftEditing?.id)} rules={[{ required: !draftEditing?.id }]}><Select options={state.publications.filter((item) => item.enabled).map((item) => ({ value: item.id, label: `${item.display_name}（${item.content_type}）` }))} /></Form.Item><Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item>{!draftEditing?.id ? <Form.Item name="item_lines" label="内容清单" extra="每行一条：审核内容 ID|栏目，例如 123|监管"><Input.TextArea rows={9} className="font-mono" /></Form.Item> : <><Space wrap><Form.Item name="status" label="状态"><Select style={{ width: 140 }} options={[{ value: 'draft', label: '草稿' }, { value: 'scheduled', label: '定时' }, { value: 'cancelled', label: '取消' }, { value: 'publishing', label: '发布中', disabled: true }, { value: 'published', label: '已发布', disabled: true }]} /></Form.Item><Form.Item name="scheduled_at" label="计划时间"><DatePicker showTime /></Form.Item></Space><Table rowKey="review_entry_id" size="small" pagination={false} dataSource={draftItems} columns={[{ title: '顺序', width: 110, render: (_, row, index) => <Space><Button size="small" disabled={!index} onClick={() => moveDraftItem(index, -1)}>↑</Button><Button size="small" disabled={index === draftItems.length - 1} onClick={() => moveDraftItem(index, 1)}>↓</Button></Space> }, { title: '内容', render: (_, row) => <><strong>#{row.review_entry_id} {row.title}</strong><div><Typography.Text type="secondary">{row.source_site}</Typography.Text></div></> }, { title: '栏目', width: 150, render: (_, row, index) => <Input value={row.section} onChange={(event) => setDraftItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, section: event.target.value } : item))} /> }, { title: '包含', width: 80, render: (_, row, index) => <Switch checked={Boolean(row.included)} onChange={(checked) => setDraftItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, included: checked } : item))} /> }]} /></>}</Form>{draftEditing?.id && !['published', 'cancelled'].includes(draftEditing.status) && <Button type="primary" icon={<SendOutlined />} loading={busy === `publish:${draftEditing.id}`} onClick={() => publishDraft(draftEditing.id)}>立即发布/重试</Button>}</Modal>
        <Modal title={draftPreview?.title || '成稿预览'} open={Boolean(draftPreview)} onCancel={() => setDraftPreview(null)} footer={<Button onClick={() => setDraftPreview(null)}>关闭</Button>} width={760} destroyOnClose>
            {draftPreview && <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Typography.Text type="secondary">{draftPreview.items.length} 条内容 · {draftPreview.parts.length} 个发送分片 · {draftPreview.target_count} 个摘要目标</Typography.Text>
                <Card><SafeReportPreview content={draftPreview.content} /></Card>
            </Space>}
        </Modal>
        <Modal title={subscriptionEditing?.id ? '编辑分析师变更订阅' : '新建分析师变更订阅'} open={Boolean(subscriptionEditing)} onCancel={() => setSubscriptionEditing(null)} onOk={saveSubscription} width={720} destroyOnClose><Form form={subscriptionForm} layout="vertical"><Space wrap><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input style={{ width: 220 }} /></Form.Item><Form.Item name="channel_id" label="Webhook 渠道" rules={[{ required: true }]}><Select style={{ width: 240 }} options={state.channels.filter((item) => item.channel_type === 'webhook').map((item) => ({ value: item.id, label: item.name }))} /></Form.Item><Form.Item name="batch_size" label="每批上限"><InputNumber min={1} max={100} /></Form.Item><Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item></Space><Form.Item name="object_types" label="变更对象" rules={[{ required: true }]}><Checkbox.Group options={[['event', '事件'], ['correction', '更正'], ['entity', '实体'], ['narrative', '叙事'], ['tag', '标签']].map(([value, label]) => ({ value, label }))} /></Form.Item><Form.Item name="content_types" label="内容类型（留空表示全部）"><Checkbox.Group options={[{ value: 'news', label: '快讯' }, { value: 'article', label: '文章' }]} /></Form.Item><Form.Item name="profile_slugs" label="内容档案（留空表示全部）"><Select mode="multiple" options={state.publications.map((item) => ({ value: item.profile_slug, label: item.display_name }))} /></Form.Item>{!subscriptionEditing?.id && <Form.Item name="start_from" label="起始位置"><Select options={[{ value: 'now', label: '从现在开始' }, { value: 'beginning', label: '补发现有变更' }]} /></Form.Item>}</Form></Modal>
    </Space>;
}
