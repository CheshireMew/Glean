import React, { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import dayjs from 'dayjs';
import { Alert, Button, Card, DatePicker, Drawer, Form, Input, InputNumber, Modal, Select, Space, Spin, Switch, Tag, Timeline, message } from 'antd';

import { addEventFact, addEventRelation, addEventUpdate, getEditorialEvent, updateEventFact, updateEventSourceEvidence } from '../../api/editorial';
import { attachEventEntity, attachEventNarrative, classifyEvent, listEntities, listNarratives } from '../../api/intelligence';
import { getEventMarket, refreshEventMarket, saveMarketExpectation, saveMarketSnapshot } from '../../api/market';
import { formatLocalDateTime } from '../../utils/time';

const roleOptions = [
    { value: 'primary', label: '一手来源' },
    { value: 'independent', label: '独立报道' },
    { value: 'reporting', label: '媒体报道' },
    { value: 'repost', label: '转载' },
    { value: 'commentary', label: '评论' },
];

export default function EventEvidenceDrawer({ eventId, open, onClose, onSaved }) {
    const [updateForm] = Form.useForm();
    const [entityForm] = Form.useForm();
    const [narrativeForm] = Form.useForm();
    const [factForm] = Form.useForm();
    const [relationForm] = Form.useForm();
    const [snapshotForm] = Form.useForm();
    const [state, setState] = useState({ loading: false, error: '', detail: null, savingId: null });
    const [sourceDrafts, setSourceDrafts] = useState({});
    const [catalogs, setCatalogs] = useState({ entities: [], narratives: [], markets: [] });
    const [marketDrafts, setMarketDrafts] = useState({});
    const [snapshotInstrument, setSnapshotInstrument] = useState(null);
    const [factEditing, setFactEditing] = useState(null);

    const load = async () => {
        if (!eventId) return;
        setState((current) => ({ ...current, loading: true, error: '' }));
        try {
            const [response, entitiesResponse, narrativesResponse, marketResponse] = await Promise.all([
                getEditorialEvent(eventId), listEntities(), listNarratives(), getEventMarket(eventId),
            ]);
            const detail = response.data;
            setSourceDrafts(Object.fromEntries(detail.sources.map((source) => [source.id, {
                source_role: source.source_role,
                evidence_group: source.evidence_group,
                origin_news_id: source.origin_news_id,
                independence_score: source.independence_score,
                verification_status: source.verification_status,
                evidence_notes: source.evidence_notes,
            }])));
            const markets = marketResponse.data?.markets || [];
            setCatalogs({ entities: entitiesResponse.data || [], narratives: narrativesResponse.data || [], markets });
            setMarketDrafts(Object.fromEntries(markets.map((item) => [item.instrument.id, {
                expected_direction: item.assessment?.expected_direction,
                expected_impact: item.assessment?.expected_impact || '',
                confidence: item.assessment?.confidence,
            }])));
            setState({ loading: false, error: '', detail, savingId: null });
        } catch (error) {
            setState({ loading: false, error: error.message || '事件证据加载失败', detail: null, savingId: null });
        }
    };

    useEffect(() => { if (open) void load(); }, [eventId, open]); // eslint-disable-line react-hooks/exhaustive-deps

    const setSourceValue = (sourceId, field, value) => setSourceDrafts((current) => ({
        ...current,
        [sourceId]: { ...current[sourceId], [field]: value },
    }));

    const saveSource = async (sourceId) => {
        setState((current) => ({ ...current, savingId: sourceId, error: '' }));
        try {
            await updateEventSourceEvidence(eventId, sourceId, sourceDrafts[sourceId]);
            message.success('证据关系已保存');
            await load();
            onSaved?.();
        } catch (error) {
            setState((current) => ({ ...current, savingId: null, error: error.message || '证据保存失败' }));
        }
    };

    const submitUpdate = async () => {
        try {
            const values = await updateForm.validateFields();
            await addEventUpdate(eventId, { ...values, occurred_at: values.occurred_at.toISOString() });
            message.success('事件进展已添加');
            updateForm.resetFields();
            await load();
            onSaved?.();
        } catch (error) {
            if (!error?.errorFields) setState((current) => ({ ...current, error: error.message || '进展保存失败' }));
        }
    };

    const attachEntity = async () => {
        try { const values = await entityForm.validateFields(); await attachEventEntity(eventId, values); entityForm.resetFields(); message.success('实体已关联'); await load(); onSaved?.(); }
        catch (error) { if (!error?.errorFields) message.error(error.message || '实体关联失败'); }
    };
    const attachNarrative = async () => {
        try { const values = await narrativeForm.validateFields(); await attachEventNarrative(eventId, values); narrativeForm.resetFields(); message.success('叙事已关联'); await load(); onSaved?.(); }
        catch (error) { if (!error?.errorFields) message.error(error.message || '叙事关联失败'); }
    };
    const runClassification = async () => {
        setState((current) => ({ ...current, savingId: 'classification' }));
        try {
            const response = await classifyEvent(eventId);
            message.success(`识别到 ${response.data.entities.length} 个实体、${response.data.narratives.length} 个叙事`);
            await load(); onSaved?.();
        } catch (error) { message.error(error.message || '自动识别失败'); } finally { setState((current) => ({ ...current, savingId: null })); }
    };
    const openFact = (fact = null) => {
        setFactEditing(fact || { id: null });
        factForm.setFieldsValue(fact ? { ...fact, is_public: Boolean(fact.is_public) } : { fact_text: '', confidence: 1, verification_status: 'unverified', is_public: true });
    };
    const saveFact = async () => {
        try {
            const values = await factForm.validateFields();
            if (factEditing.id) await updateEventFact(factEditing.id, values); else await addEventFact(eventId, values);
            message.success(factEditing.id ? '关键事实已更新' : '关键事实已添加');
            setFactEditing(null); await load(); onSaved?.();
        } catch (error) { if (!error?.errorFields) message.error(error.message || '关键事实保存失败'); }
    };
    const addRelation = async () => {
        try {
            const values = await relationForm.validateFields();
            await addEventRelation(eventId, values);
            message.success('关联事件已保存'); relationForm.resetFields(); await load(); onSaved?.();
        } catch (error) { if (!error?.errorFields) message.error(error.message || '关联事件保存失败'); }
    };
    const refreshMarket = async () => {
        setState((current) => ({ ...current, savingId: 'market-refresh' }));
        try { const response = await refreshEventMarket(eventId); message.success(`已保存 ${response.data.saved} 个行情窗口${response.data.errors?.length ? `，${response.data.errors.length} 个窗口失败` : ''}`); await load(); }
        catch (error) { message.error(error.message || '行情刷新失败'); } finally { setState((current) => ({ ...current, savingId: null })); }
    };
    const saveExpectation = async (instrumentId) => {
        setState((current) => ({ ...current, savingId: `market:${instrumentId}` }));
        try { await saveMarketExpectation(eventId, instrumentId, marketDrafts[instrumentId] || {}); message.success('事前判断已保存'); await load(); }
        catch (error) { message.error(error.message || '判断保存失败'); } finally { setState((current) => ({ ...current, savingId: null })); }
    };
    const saveSnapshot = async () => {
        try { const values = await snapshotForm.validateFields(); await saveMarketSnapshot(eventId, snapshotInstrument.id, { ...values, observed_at: values.observed_at.toISOString() }); message.success('行情快照已保存并重新计算'); setSnapshotInstrument(null); snapshotForm.resetFields(); await load(); }
        catch (error) { if (!error?.errorFields) message.error(error.message || '快照保存失败'); }
    };
    const setMarketValue = (instrumentId, field, value) => setMarketDrafts((current) => ({ ...current, [instrumentId]: { ...current[instrumentId], [field]: value } }));

    return (
        <Drawer title={`事件证据 #${eventId || ''}`} open={open} onClose={onClose} width={760} destroyOnClose>
            {state.error && <Alert type="error" showIcon message={state.error} action={<Button size="small" onClick={load}>重试</Button>} style={{ marginBottom: 16 }} />}
            {state.loading ? <div style={{ padding: 60, textAlign: 'center' }}><Spin /></div> : state.detail && <>
                <Card size="small" title={state.detail.event.title} style={{ marginBottom: 16 }}>
                    <Space wrap><Tag color="blue">{state.detail.sources.length} 条来源</Tag><Tag color="green">{state.detail.independent_source_count} 组独立证据</Tag><span>{formatLocalDateTime(state.detail.event.first_seen_at)} — {formatLocalDateTime(state.detail.event.last_seen_at)}</span></Space>
                </Card>
                <h3>来源关系</h3>
                <div style={{ display: 'grid', gap: 12 }}>
                    {state.detail.sources.map((source) => {
                        const draft = sourceDrafts[source.id] || {};
                        return <Card key={source.id} size="small" title={<a href={source.source_url} target="_blank" rel="noopener noreferrer">{source.source_site}：{source.title}</a>}>
                            <Space direction="vertical" style={{ width: '100%' }} size="middle">
                                <Space wrap>
                                    <Select value={draft.source_role} options={roleOptions} style={{ width: 130 }} onChange={(value) => setSourceValue(source.id, 'source_role', value)} />
                                    <Select value={draft.verification_status} style={{ width: 120 }} options={[{ value: 'unverified', label: '未核验' }, { value: 'verified', label: '已核验' }, { value: 'disputed', label: '有争议' }]} onChange={(value) => setSourceValue(source.id, 'verification_status', value)} />
                                    <Input value={draft.evidence_group} placeholder="证据组，例如 sec:notice-123" style={{ width: 240 }} onChange={(event) => setSourceValue(source.id, 'evidence_group', event.target.value || null)} />
                                </Space>
                                <Space wrap>
                                    <Select allowClear value={draft.origin_news_id} placeholder="转载自哪个来源" style={{ width: 220 }} options={state.detail.sources.filter((item) => item.id !== source.id).map((item) => ({ value: item.id, label: `${item.source_site} #${item.id}` }))} onChange={(value) => setSourceValue(source.id, 'origin_news_id', value)} />
                                    <Select value={draft.independence_score} style={{ width: 180 }} options={[{ value: 1, label: '独立证据 1.0' }, { value: 0.5, label: '部分独立 0.5' }, { value: 0, label: '非独立 0' }]} onChange={(value) => setSourceValue(source.id, 'independence_score', value)} />
                                </Space>
                                <Input.TextArea value={draft.evidence_notes} placeholder="核验说明、引用关系或争议信息" autoSize={{ minRows: 2, maxRows: 5 }} onChange={(event) => setSourceValue(source.id, 'evidence_notes', event.target.value || null)} />
                                <Button type="primary" loading={state.savingId === source.id} onClick={() => saveSource(source.id)}>保存此来源</Button>
                            </Space>
                        </Card>;
                    })}
                </div>
                <Card title="关键事实" size="small" style={{ marginTop: 20 }} extra={<Button type="primary" onClick={() => openFact()}>添加事实</Button>}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                        {state.detail.facts.map((fact) => <Card key={fact.id} size="small" extra={<Button size="small" onClick={() => openFact(fact)}>编辑</Button>}><Space wrap><Tag color={fact.verification_status === 'verified' ? 'green' : fact.verification_status === 'disputed' ? 'red' : 'default'}>{fact.verification_status}</Tag><Tag>{Math.round(Number(fact.confidence) * 100)}%</Tag>{!fact.is_public && <Tag>内部</Tag>}</Space><p style={{ margin: '8px 0 0' }}>{fact.fact_text}</p>{fact.source_title && <a href={fact.source_url} target="_blank" rel="noopener noreferrer">依据：{fact.source_site} · {fact.source_title}</a>}</Card>)}
                        {state.detail.facts.length === 0 && <Alert type="info" showIcon message="尚未整理结构化关键事实" />}
                    </Space>
                </Card>
                <Card title="关联事件" size="small" style={{ marginTop: 20 }}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Space wrap>{state.detail.relations.map((relation) => <Tag key={relation.id} color="cyan">#{relation.related_id} {relation.relation_type} · {relation.related_title}</Tag>)}{state.detail.relations.length === 0 && <span>暂无</span>}</Space>
                        <Form form={relationForm} layout="inline" initialValues={{ relation_type: 'related', is_public: true }}><Form.Item name="related_event_id" rules={[{ required: true }]}><InputNumber min={1} placeholder="关联事件 ID" /></Form.Item><Form.Item name="relation_type"><Select style={{ width: 140 }} options={[['related', '相关'], ['cause', '原因'], ['effect', '结果'], ['follow_up', '后续'], ['contradiction', '矛盾'], ['same_story', '同一故事']].map(([value, label]) => ({ value, label }))} /></Form.Item><Form.Item name="notes"><Input placeholder="关系说明" style={{ width: 240 }} /></Form.Item><Button type="primary" onClick={addRelation}>保存关系</Button></Form>
                    </Space>
                </Card>
                <Card title="实体与叙事" size="small" style={{ marginTop: 20 }} extra={<Button loading={state.savingId === 'classification'} onClick={runClassification}>自动识别</Button>}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <div><strong>已关联实体：</strong><Space wrap>{state.detail.entities.map((item) => <Tag key={`${item.id}:${item.role}`} color="blue">{item.symbol || item.name} / {item.role}</Tag>)}{state.detail.entities.length === 0 && <span>暂无</span>}</Space></div>
                        <Form form={entityForm} layout="inline" initialValues={{ role: 'mentioned', confidence: 1, source: 'manual' }}><Form.Item name="entity_id" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" placeholder="选择实体" style={{ width: 260 }} options={catalogs.entities.map((item) => ({ value: item.id, label: `${item.name}${item.symbol ? ` (${item.symbol})` : ''}` }))} /></Form.Item><Form.Item name="role"><Select style={{ width: 130 }} options={['subject', 'actor', 'affected', 'location', 'mentioned'].map((value) => ({ value, label: value }))} /></Form.Item><Button type="primary" onClick={attachEntity}>关联实体</Button></Form>
                        <div><strong>已关联叙事：</strong><Space wrap>{state.detail.narratives.map((item) => <Tag key={item.id} color="purple">{item.name}</Tag>)}{state.detail.narratives.length === 0 && <span>暂无</span>}</Space></div>
                        <Form form={narrativeForm} layout="inline" initialValues={{ confidence: 1, source: 'manual' }}><Form.Item name="narrative_id" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" placeholder="选择叙事" style={{ width: 260 }} options={catalogs.narratives.filter((item) => item.enabled).map((item) => ({ value: item.id, label: item.name }))} /></Form.Item><Button type="primary" onClick={attachNarrative}>关联叙事</Button></Form>
                    </Space>
                </Card>
                <Card title="市场影响" size="small" style={{ marginTop: 20 }} extra={<Button loading={state.savingId === 'market-refresh'} onClick={refreshMarket}>刷新行情窗口</Button>}>
                    {catalogs.markets.length === 0 ? <Alert type="info" showIcon message="先在“情报目录 → 行情映射”中为事件实体配置行情品种。" /> : <Space direction="vertical" style={{ width: '100%' }}>{catalogs.markets.map(({ instrument, snapshots, assessment }) => { const draft = marketDrafts[instrument.id] || {}; return <Card key={instrument.id} size="small" title={`${instrument.entity_name} · ${instrument.provider}:${instrument.symbol}/${instrument.quote_symbol}`} extra={<Button onClick={() => { setSnapshotInstrument(instrument); snapshotForm.setFieldsValue({ observation_window: 't0', observed_at: dayjs() }); }}>录入快照</Button>}><Space direction="vertical" style={{ width: '100%' }}><Space wrap><Select allowClear placeholder="事前方向" value={draft.expected_direction} style={{ width: 140 }} options={['positive', 'negative', 'neutral', 'uncertain'].map((value) => ({ value, label: value }))} onChange={(value) => setMarketValue(instrument.id, 'expected_direction', value)} /><InputNumber min={0} max={1} step={0.1} placeholder="置信度" value={draft.confidence} onChange={(value) => setMarketValue(instrument.id, 'confidence', value)} /><Button type="primary" loading={state.savingId === `market:${instrument.id}`} onClick={() => saveExpectation(instrument.id)}>保存判断</Button></Space><Input.TextArea value={draft.expected_impact} placeholder="记录发布前的预期影响，避免事后解释" autoSize={{ minRows: 2, maxRows: 5 }} onChange={(event) => setMarketValue(instrument.id, 'expected_impact', event.target.value)} /><Space wrap>{snapshots.map((item) => <Tag key={item.observation_window}>{item.observation_window}: {item.price ?? '—'}</Tag>)}</Space>{assessment && <div>实际方向：<strong>{assessment.realized_direction || '待观察'}</strong> · 15m {assessment.return_15m == null ? '—' : `${(assessment.return_15m * 100).toFixed(2)}%`} · 1h {assessment.return_1h == null ? '—' : `${(assessment.return_1h * 100).toFixed(2)}%`} · 24h {assessment.return_24h == null ? '—' : `${(assessment.return_24h * 100).toFixed(2)}%`}</div>}</Space></Card>; })}</Space>}
                </Card>
                <Card title="添加事件进展" size="small" style={{ marginTop: 20 }}>
                    <Form form={updateForm} layout="vertical" initialValues={{ update_type: 'development', is_public: true, occurred_at: dayjs() }}>
                        <Space wrap align="start">
                            <Form.Item name="update_type" label="类型"><Select style={{ width: 130 }} options={[{ value: 'development', label: '新进展' }, { value: 'correction', label: '更正' }, { value: 'retraction', label: '撤回' }, { value: 'context', label: '背景' }, { value: 'market', label: '市场变化' }]} /></Form.Item>
                            <Form.Item name="occurred_at" label="发生时间" rules={[{ required: true }]}><DatePicker showTime /></Form.Item>
                            <Form.Item name="source_news_id" label="依据来源"><Select allowClear style={{ width: 220 }} options={state.detail.sources.map((source) => ({ value: source.id, label: `${source.source_site} #${source.id}` }))} /></Form.Item>
                        </Space>
                        <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入进展标题' }]}><Input /></Form.Item>
                        <Form.Item name="summary" label="说明"><Input.TextArea autoSize={{ minRows: 2, maxRows: 6 }} /></Form.Item>
                        <Button type="primary" onClick={submitUpdate}>添加进展</Button>
                    </Form>
                </Card>
                {state.detail.updates.length > 0 && <Card title="事件时间线" size="small" style={{ marginTop: 20 }}><Timeline items={state.detail.updates.map((item) => ({ children: <><strong>{item.title}</strong><div>{formatLocalDateTime(item.occurred_at)}</div><p>{item.summary}</p></> }))} /></Card>}
            </>}
            <Modal title={`录入行情快照：${snapshotInstrument?.symbol || ''}`} open={Boolean(snapshotInstrument)} onCancel={() => setSnapshotInstrument(null)} onOk={saveSnapshot} destroyOnClose><Form form={snapshotForm} layout="vertical"><Form.Item name="observation_window" label="观察窗口" rules={[{ required: true }]}><Select options={['t-1h', 't0', 't+15m', 't+1h', 't+24h', 't+7d'].map((value) => ({ value, label: value }))} /></Form.Item><Form.Item name="observed_at" label="观察时间" rules={[{ required: true }]}><DatePicker showTime style={{ width: '100%' }} /></Form.Item><Form.Item name="price" label="价格" rules={[{ required: true }]}><InputNumber min={0} precision={8} style={{ width: '100%' }} /></Form.Item><Form.Item name="volume" label="成交量"><InputNumber min={0} precision={8} style={{ width: '100%' }} /></Form.Item></Form></Modal>
            <Modal title={factEditing?.id ? '编辑关键事实' : '添加关键事实'} open={Boolean(factEditing)} onCancel={() => setFactEditing(null)} onOk={saveFact} destroyOnClose><Form form={factForm} layout="vertical"><Form.Item name="fact_text" label="事实" rules={[{ required: true }]}><Input.TextArea rows={5} /></Form.Item><Space wrap><Form.Item name="source_news_id" label="依据来源"><Select allowClear style={{ width: 220 }} options={(state.detail?.sources || []).map((source) => ({ value: source.id, label: `${source.source_site} #${source.id}` }))} /></Form.Item><Form.Item name="verification_status" label="核验状态"><Select style={{ width: 120 }} options={[{ value: 'unverified', label: '未核验' }, { value: 'verified', label: '已核验' }, { value: 'disputed', label: '有争议' }]} /></Form.Item><Form.Item name="confidence" label="置信度"><InputNumber min={0} max={1} step={0.05} /></Form.Item><Form.Item name="is_public" label="公开" valuePropName="checked"><Switch /></Form.Item></Space></Form></Modal>
        </Drawer>
    );
}

EventEvidenceDrawer.propTypes = {
    eventId: PropTypes.number,
    open: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    onSaved: PropTypes.func,
};
