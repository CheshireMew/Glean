import React, { useEffect, useState } from 'react';
import { Alert, Button, Card, Form, Input, Modal, Select, Space, Switch, Table, Tag, Typography, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';

import { listSourceCatalog, listSourceIncidents, snapshotSourceHealth, updateSourceCatalog, updateSourceIncident } from '../../api/sourceOperations';
import { formatLocalDateTime } from '../../utils/time';

const percent = (value) => value == null ? '—' : `${(Number(value) * 100).toFixed(1)}%`;

export default function SourceOperationsTab() {
    const [state, setState] = useState({ loading: true, error: '', sources: [], incidents: [] });
    const [editing, setEditing] = useState(null);
    const [busy, setBusy] = useState('');
    const [form] = Form.useForm();
    const load = async () => {
        setState((current) => ({ ...current, loading: true, error: '' }));
        try {
            const [sources, incidents] = await Promise.all([listSourceCatalog(), listSourceIncidents()]);
            setState({ loading: false, error: '', sources: sources.data || [], incidents: incidents.data || [] });
        } catch (error) { setState((current) => ({ ...current, loading: false, error: error.message || '来源运营数据加载失败' })); }
    };
    useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, []);
    const snapshot = async () => {
        setBusy('snapshot');
        try { const response = await snapshotSourceHealth({ hours: 24 }); message.success(`已生成 ${response.data.snapshots.length} 份快照，新增 ${response.data.new_incidents} 个异常`); await load(); }
        catch (error) { message.error(error.message || '健康检查失败'); } finally { setBusy(''); }
    };
    const open = (record) => { setEditing(record); form.setFieldsValue({ ...record, metadata_json: JSON.stringify(record.metadata || {}, null, 2) }); };
    const save = async () => {
        try { const values = await form.validateFields(); let metadata; try { metadata = JSON.parse(values.metadata_json || '{}'); } catch { throw new Error('元数据必须是合法 JSON'); } delete values.metadata_json; await updateSourceCatalog(editing.source_key, { ...values, metadata }); message.success('来源档案已保存'); setEditing(null); await load(); }
        catch (error) { if (!error?.errorFields) message.error(error.message || '保存失败'); }
    };
    const updateIncident = async (id, status) => {
        setBusy(`incident:${id}`);
        try { await updateSourceIncident(id, { status }); message.success('异常状态已更新'); await load(); }
        catch (error) { message.error(error.message || '更新失败'); } finally { setBusy(''); }
    };
    const sourceColumns = [
        { title: '来源', render: (_, row) => <><strong>{row.display_name}</strong>{row.is_official && <Tag color="blue" style={{ marginLeft: 8 }}>官方</Tag>}<div><Typography.Text type="secondary">{row.source_key} · {row.source_type}/{row.metadata?.transport_kind}</Typography.Text></div></> },
        { title: '权威级别', dataIndex: 'authority_type', render: (value) => <Tag color={value === 'primary' ? 'green' : value === 'aggregator' ? 'orange' : 'default'}>{value}</Tag> },
        { title: '运行', render: (_, row) => <><Tag color={row.runtime_status === 'error' ? 'red' : row.runtime_status === 'running' ? 'blue' : 'green'}>{row.runtime_status || '未运行'}</Tag><div><Typography.Text type="secondary">{row.last_run ? formatLocalDateTime(row.last_run) : '无运行记录'} · {row.items_scraped || 0} 条</Typography.Text></div></> },
        { title: '24h 质量', render: (_, row) => { const health = row.latest_health; return health ? <Space direction="vertical" size={0}><span>完整 {percent(health.content_completeness)} · 入簇 {percent(health.cluster_join_rate)}</span><Typography.Text type="secondary">入选 {percent(health.selection_rate)} · {health.item_count} 条</Typography.Text></Space> : '尚未生成快照'; } },
        { title: '异常', dataIndex: 'open_incident_count', render: (value) => <Tag color={value ? 'red' : 'green'}>{value || 0}</Tag> },
        { title: '操作', render: (_, row) => <Button onClick={() => open(row)}>维护</Button> },
    ];
    const incidentColumns = [
        { title: '发现时间', dataIndex: 'detected_at', render: formatLocalDateTime }, { title: '来源', dataIndex: 'display_name' },
        { title: '类型', dataIndex: 'incident_type', render: (value) => <Tag color="red">{value}</Tag> }, { title: '说明', dataIndex: 'summary' },
        { title: '状态', dataIndex: 'status', render: (value) => <Tag color={value === 'resolved' ? 'green' : value === 'acknowledged' ? 'blue' : 'red'}>{value}</Tag> },
        { title: '操作', render: (_, row) => <Space>{row.status === 'open' && <Button size="small" loading={busy === `incident:${row.id}`} onClick={() => updateIncident(row.id, 'acknowledged')}>确认</Button>}{row.status !== 'resolved' && <Button size="small" type="primary" loading={busy === `incident:${row.id}`} onClick={() => updateIncident(row.id, 'resolved')}>解决</Button>}</Space> },
    ];
    return <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {state.error && <Alert type="error" showIcon message={state.error} action={<Button onClick={load}>重试</Button>} />}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}><div><Typography.Title level={3} style={{ margin: 0 }}>来源运营</Typography.Title><Typography.Text type="secondary">区分一手、媒体和聚合来源，跟踪正文完整率、入簇率、入选率与采集异常。</Typography.Text></div><Space><Button icon={<ReloadOutlined />} loading={state.loading} onClick={load}>刷新</Button><Button type="primary" loading={busy === 'snapshot'} onClick={snapshot}>生成 24h 快照</Button></Space></div>
        <Card title="来源目录"><Table rowKey="source_key" loading={state.loading} dataSource={state.sources} columns={sourceColumns} pagination={{ pageSize: 20 }} scroll={{ x: 1050 }} /></Card>
        <Card title="异常记录"><Table rowKey="id" dataSource={state.incidents} columns={incidentColumns} pagination={{ pageSize: 20 }} /></Card>
        <Modal title={`维护来源：${editing?.display_name || ''}`} open={Boolean(editing)} onCancel={() => setEditing(null)} onOk={save} width={680} destroyOnClose><Form form={form} layout="vertical"><Space wrap><Form.Item name="display_name" label="显示名称" rules={[{ required: true }]}><Input style={{ width: 230 }} /></Form.Item><Form.Item name="authority_type" label="权威级别"><Select style={{ width: 150 }} options={[{ value: 'primary', label: '一手来源' }, { value: 'media', label: '媒体' }, { value: 'aggregator', label: '聚合器' }, { value: 'commentary', label: '评论' }]} /></Form.Item><Form.Item name="is_official" label="官方来源" valuePropName="checked"><Switch /></Form.Item><Form.Item name="enabled" label="参与自动采集" valuePropName="checked"><Switch /></Form.Item></Space><Form.Item name="homepage_url" label="主页"><Input /></Form.Item><Form.Item name="metadata_json" label="元数据（JSON）"><Input.TextArea rows={8} className="font-mono" /></Form.Item></Form></Modal>
    </Space>;
}
