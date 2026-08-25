import React, { useEffect, useState } from 'react';
import {
    Alert, Button, Card, Form, Input, InputNumber, Modal, Select, Space, Switch,
    Table, Tabs, Tag, Typography, message,
} from 'antd';
import { BellOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';

import {
    createAlertPolicy, createEntity, createNarrative, createWatchlist, evaluateAlertPolicies,
    listAlertMatches, listAlertPolicies, listEntities, listNarratives, listWatchlists,
    updateAlertPolicy, updateEntity, updateNarrative, updateWatchlist,
} from '../../api/intelligence';
import { createMarketInstrument, listMarketInstruments, updateMarketInstrument } from '../../api/market';
import { listPublicationChannels, listPublications } from '../../api/publications';
import { formatLocalDateTime } from '../../utils/time';

const ENTITY_TYPES = ['asset', 'protocol', 'company', 'person', 'regulator', 'exchange', 'organization', 'jurisdiction'].map((value) => ({ value, label: value }));
function jsonText(value) { return JSON.stringify(value || {}, null, 2); }
function parseJson(value, label) { try { return JSON.parse(value || '{}'); } catch { throw new Error(`${label}必须是合法 JSON`); } }

export default function IntelligenceCenterTab() {
    const [state, setState] = useState({ loading: true, error: '', entities: [], narratives: [], watchlists: [], alerts: [], matches: [], channels: [], publications: [], instruments: [] });
    const [editor, setEditor] = useState(null);
    const [busy, setBusy] = useState('');
    const [form] = Form.useForm();

    const load = async () => {
        setState((current) => ({ ...current, loading: true, error: '' }));
        try {
            const [entities, narratives, watchlists, alerts, matches, channels, publications, instruments] = await Promise.all([
                listEntities(), listNarratives(), listWatchlists(), listAlertPolicies(), listAlertMatches(), listPublicationChannels(), listPublications(), listMarketInstruments(),
            ]);
            setState({ loading: false, error: '', entities: entities.data || [], narratives: narratives.data || [], watchlists: watchlists.data || [], alerts: alerts.data || [], matches: matches.data || [], channels: channels.data || [], publications: publications.data || [], instruments: instruments.data || [] });
        } catch (error) { setState((current) => ({ ...current, loading: false, error: error.message || '情报目录加载失败' })); }
    };
    useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, []);

    const open = (type, record = null) => {
        setEditor({ type, record });
        if (type === 'entity') form.setFieldsValue(record ? { ...record, aliases_text: (record.aliases || []).join('\n'), metadata_json: jsonText(record.metadata) } : { entity_type: 'asset', slug: '', name: '', aliases_text: '', description: '', metadata_json: '{}' });
        if (type === 'narrative') form.setFieldsValue(record ? { ...record, keywords_text: (record.keywords || []).join('\n') } : { slug: '', name: '', description: '', keywords_text: '', enabled: true });
        if (type === 'watchlist') form.setFieldsValue(record || { name: '', description: '', enabled: true, visibility: 'private', entity_ids: [], narrative_ids: [] });
        if (type === 'alert') form.setFieldsValue(record ? { ...record, conditions_json: jsonText(record.conditions), quiet_hours_json: jsonText(record.quiet_hours) } : { name: '', description: '', enabled: true, schedule_type: 'instant', conditions_json: '{\n  "min_score": 7,\n  "min_independent_sources": 2\n}', quiet_hours_json: '{}', channel_id: state.channels[0]?.id });
        if (type === 'instrument') form.setFieldsValue(record ? { ...record, metadata_json: jsonText(record.metadata) } : { entity_id: state.entities.find((item) => item.entity_type === 'asset')?.id, provider: 'binance', symbol: '', quote_symbol: 'USDT', enabled: true, metadata_json: '{}' });
    };
    const save = async () => {
        try {
            const values = await form.validateFields(); const record = editor.record;
            if (editor.type === 'entity') {
                const data = { ...values, aliases: String(values.aliases_text || '').split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean), metadata: parseJson(values.metadata_json, '元数据') }; delete data.aliases_text; delete data.metadata_json;
                if (record) await updateEntity(record.id, data); else await createEntity(data);
            } else if (editor.type === 'narrative') {
                const data = { ...values, keywords: String(values.keywords_text || '').split(/[,，\n]/).map((item) => item.trim()).filter(Boolean) };
                delete data.keywords_text;
                if (record) await updateNarrative(record.id, data); else await createNarrative(data);
            } else if (editor.type === 'watchlist') {
                if (record) await updateWatchlist(record.id, values); else await createWatchlist(values);
            } else if (editor.type === 'alert') {
                const data = { ...values, conditions: parseJson(values.conditions_json, '提醒条件'), quiet_hours: parseJson(values.quiet_hours_json, '静默时段') }; delete data.conditions_json; delete data.quiet_hours_json;
                if (record) await updateAlertPolicy(record.id, data); else await createAlertPolicy(data);
            } else {
                const data = { ...values, metadata: parseJson(values.metadata_json, '行情元数据') }; delete data.metadata_json;
                if (record) await updateMarketInstrument(record.id, data); else await createMarketInstrument(data);
            }
            message.success('已保存'); setEditor(null); await load();
        } catch (error) { if (!error?.errorFields) message.error(error.message || '保存失败'); }
    };
    const evaluate = async () => {
        setBusy('evaluate');
        try { const response = await evaluateAlertPolicies({ hours: 168 }); message.success(`扫描完成，新增 ${response.data.new_matches} 条匹配`); await load(); }
        catch (error) { message.error(error.message || '提醒评估失败'); } finally { setBusy(''); }
    };

    const entityColumns = [
        { title: '实体', render: (_, row) => <><strong>{row.name}</strong>{row.symbol && <Tag style={{ marginLeft: 8 }}>{row.symbol}</Tag>}<div><Typography.Text type="secondary">/{row.slug}</Typography.Text></div></> },
        { title: '类型', dataIndex: 'entity_type', render: (value) => <Tag color="blue">{value}</Tag> },
        { title: '别名', dataIndex: 'aliases', render: (values) => (values || []).join('、') || '—' },
        { title: '事件数', dataIndex: 'event_count' }, { title: '操作', render: (_, row) => <Button onClick={() => open('entity', row)}>编辑</Button> },
    ];
    const narrativeColumns = [
        { title: '叙事', render: (_, row) => <><strong>{row.name}</strong><div><Typography.Text type="secondary">/{row.slug}</Typography.Text></div></> },
        { title: '说明', dataIndex: 'description', ellipsis: true }, { title: '事件数', dataIndex: 'event_count' },
        { title: '状态', dataIndex: 'enabled', render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '停用'}</Tag> },
        { title: '操作', render: (_, row) => <Button onClick={() => open('narrative', row)}>编辑</Button> },
    ];
    const watchlistColumns = [
        { title: '关注列表', render: (_, row) => <><strong>{row.name}</strong><div><Typography.Text type="secondary">{row.description || '无说明'}</Typography.Text></div></> },
        { title: '范围', render: (_, row) => `${row.entity_ids.length} 个实体 / ${row.narrative_ids.length} 个叙事` },
        { title: '可见性', dataIndex: 'visibility', render: (value) => <Tag>{value}</Tag> },
        { title: '操作', render: (_, row) => <Button onClick={() => open('watchlist', row)}>编辑</Button> },
    ];
    const alertColumns = [
        { title: '规则', render: (_, row) => <><strong>{row.name}</strong><div><Typography.Text type="secondary">{row.watchlist_name || '直接条件'} → {row.channel_name}</Typography.Text></div></> },
        { title: '频率', dataIndex: 'schedule_type', render: (value) => <Tag color="purple">{value}</Tag> },
        { title: '条件', dataIndex: 'conditions', render: (value) => <code>{JSON.stringify(value)}</code> },
        { title: '上次评估', dataIndex: 'last_evaluated_at', render: (value) => value ? formatLocalDateTime(value) : '—' },
        { title: '操作', render: (_, row) => <Button onClick={() => open('alert', row)}>编辑</Button> },
    ];
    const matchColumns = [
        { title: '匹配时间', dataIndex: 'matched_at', render: formatLocalDateTime }, { title: '规则', dataIndex: 'policy_name' },
        { title: '事件', render: (_, row) => `#${row.event_id} ${row.event_title}` }, { title: '渠道', dataIndex: 'channel_slug' },
        { title: '状态', dataIndex: 'status', render: (value) => <Tag color={value === 'sent' ? 'green' : value === 'failed' ? 'red' : 'orange'}>{value}</Tag> },
    ];
    const marketColumns = [
        { title: '实体', render: (_, row) => <><strong>{row.entity_name}</strong><div><Typography.Text type="secondary">{row.entity_slug}</Typography.Text></div></> },
        { title: '行情', render: (_, row) => <Tag color="gold">{row.provider}:{row.symbol}/{row.quote_symbol}</Tag> },
        { title: '状态', dataIndex: 'enabled', render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '停用'}</Tag> },
        { title: '操作', render: (_, row) => <Button onClick={() => open('instrument', row)}>编辑</Button> },
    ];

    return <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {state.error && <Alert type="error" showIcon message={state.error} action={<Button onClick={load}>重试</Button>} />}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><div><Typography.Title level={3} style={{ margin: 0 }}>情报目录</Typography.Title><Typography.Text type="secondary">统一维护实体、叙事、关注范围、提醒条件和行情映射。</Typography.Text></div><Button icon={<ReloadOutlined />} loading={state.loading} onClick={load}>刷新</Button></div>
        <Tabs items={[
            { key: 'entities', label: `实体 (${state.entities.length})`, children: <Card extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => open('entity')}>新建实体</Button>}><Table rowKey="id" dataSource={state.entities} columns={entityColumns} pagination={{ pageSize: 20 }} /></Card> },
            { key: 'narratives', label: `叙事 (${state.narratives.length})`, children: <Card extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => open('narrative')}>新建叙事</Button>}><Table rowKey="id" dataSource={state.narratives} columns={narrativeColumns} pagination={{ pageSize: 20 }} /></Card> },
            { key: 'watchlists', label: '关注列表', children: <Card extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => open('watchlist')}>新建关注列表</Button>}><Table rowKey="id" dataSource={state.watchlists} columns={watchlistColumns} pagination={false} /></Card> },
            { key: 'alerts', label: '提醒', children: <Space direction="vertical" style={{ width: '100%' }}><Card extra={<Space><Button icon={<BellOutlined />} loading={busy === 'evaluate'} onClick={evaluate}>立即评估</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => open('alert')}>新建规则</Button></Space>}><Table rowKey="id" dataSource={state.alerts} columns={alertColumns} pagination={false} scroll={{ x: 900 }} /></Card><Card title="匹配与投递记录"><Table rowKey={(row) => `${row.policy_id}:${row.event_id}`} dataSource={state.matches} columns={matchColumns} pagination={{ pageSize: 20 }} /></Card></Space> },
            { key: 'market', label: '行情映射', children: <Card extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => open('instrument')}>新建品种</Button>}><Alert type="info" showIcon message="Binance 品种可自动抓取事件前后窗口；manual 品种通过事件证据抽屉录入快照。" style={{ marginBottom: 16 }} /><Table rowKey="id" dataSource={state.instruments} columns={marketColumns} pagination={false} /></Card> },
        ]} />
        <Modal title={editor?.record ? '编辑' : '新建'} open={Boolean(editor)} onCancel={() => setEditor(null)} onOk={save} width={720} destroyOnClose><Form form={form} layout="vertical">
            {editor?.type === 'entity' && <><Space wrap><Form.Item name="entity_type" label="类型" rules={[{ required: true }]}><Select style={{ width: 170 }} options={ENTITY_TYPES} /></Form.Item><Form.Item name="slug" label="标识" rules={[{ required: true }]}><Input style={{ width: 190 }} /></Form.Item><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input style={{ width: 220 }} /></Form.Item><Form.Item name="symbol" label="符号"><Input style={{ width: 120 }} /></Form.Item></Space><Form.Item name="description" label="说明"><Input.TextArea rows={3} /></Form.Item><Form.Item name="aliases_text" label="别名（每行一个）"><Input.TextArea rows={4} /></Form.Item><Form.Item name="metadata_json" label="元数据（JSON）"><Input.TextArea rows={5} className="font-mono" /></Form.Item></>}
            {editor?.type === 'narrative' && <><Space wrap><Form.Item name="slug" label="标识" rules={[{ required: true }]}><Input style={{ width: 220 }} /></Form.Item><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input style={{ width: 280 }} /></Form.Item><Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item></Space><Form.Item name="description" label="叙事定义"><Input.TextArea rows={5} /></Form.Item><Form.Item name="keywords_text" label="自动识别关键词" extra="每行一个，也可用逗号分隔；事件标题或正文命中后自动关联。"><Input.TextArea rows={5} /></Form.Item></>}
            {editor?.type === 'watchlist' && <><Space wrap><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input style={{ width: 260 }} /></Form.Item><Form.Item name="visibility" label="可见性"><Select style={{ width: 130 }} options={[{ value: 'private', label: '私有' }, { value: 'public', label: '公开' }]} /></Form.Item><Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item></Space><Form.Item name="description" label="说明"><Input.TextArea rows={2} /></Form.Item><Form.Item name="entity_ids" label="实体"><Select mode="multiple" optionFilterProp="label" options={state.entities.map((item) => ({ value: item.id, label: `${item.name}${item.symbol ? ` (${item.symbol})` : ''}` }))} /></Form.Item><Form.Item name="narrative_ids" label="叙事"><Select mode="multiple" optionFilterProp="label" options={state.narratives.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item></>}
            {editor?.type === 'alert' && <><Space wrap><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input style={{ width: 240 }} /></Form.Item><Form.Item name="watchlist_id" label="关注列表"><Select allowClear style={{ width: 200 }} options={state.watchlists.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item><Form.Item name="profile_slug" label="内容档案"><Select allowClear style={{ width: 180 }} options={state.publications.map((item) => ({ value: item.profile_slug, label: item.display_name }))} /></Form.Item><Form.Item name="channel_id" label="投递渠道" rules={[{ required: true }]}><Select style={{ width: 180 }} options={state.channels.filter((item) => item.enabled).map((item) => ({ value: item.id, label: item.name }))} /></Form.Item></Space><Space wrap><Form.Item name="schedule_type" label="频率"><Select style={{ width: 130 }} options={[{ value: 'instant', label: '即时' }, { value: 'daily', label: '每日汇总' }, { value: 'weekly', label: '每周汇总' }]} /></Form.Item><Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item></Space><Form.Item name="description" label="说明"><Input.TextArea rows={2} /></Form.Item><Form.Item name="conditions_json" label="匹配条件（JSON）" extra="支持 min_score、categories、content_types、min_independent_sources、verified_only、source_sites、keywords、entity_ids、narrative_ids"><Input.TextArea rows={8} className="font-mono" /></Form.Item><Form.Item name="quiet_hours_json" label="静默与汇总设置（JSON）"><Input.TextArea rows={4} className="font-mono" /></Form.Item></>}
            {editor?.type === 'instrument' && <><Space wrap><Form.Item name="entity_id" label="资产实体" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" style={{ width: 230 }} options={state.entities.filter((item) => item.entity_type === 'asset').map((item) => ({ value: item.id, label: `${item.name}${item.symbol ? ` (${item.symbol})` : ''}` }))} /></Form.Item><Form.Item name="provider" label="提供方"><Select style={{ width: 130 }} options={[{ value: 'binance', label: 'Binance' }, { value: 'manual', label: '手工' }]} /></Form.Item><Form.Item name="symbol" label="基础资产" rules={[{ required: true }]}><Input style={{ width: 110 }} placeholder="BTC" /></Form.Item><Form.Item name="quote_symbol" label="计价资产"><Input style={{ width: 100 }} /></Form.Item><Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item></Space><Form.Item name="metadata_json" label="元数据（JSON）"><Input.TextArea rows={6} className="font-mono" /></Form.Item></>}
        </Form></Modal>
    </Space>;
}
