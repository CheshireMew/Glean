import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Empty, Form, Input, InputNumber, Modal, Space, Switch, Table, Tag } from 'antd';
import {
    getWechatStatus, startWechatLogin, cancelWechatLogin, disconnectWechat,
    searchWechatAccounts, getWechatSources, addWechatSource, updateWechatSource,
} from '../../api/wechat';
import { requestOperation } from '../../api/operations';

const labels = { connected: '已登录', disconnected: '尚未登录', expired: '登录已失效', limited: '暂时限流' };
const activeLoginStates = new Set(['starting', 'waiting', 'scanned']);

export default function WechatSourceManager() {
    const [status, setStatus] = useState(null);
    const [sources, setSources] = useState([]);
    const [runtime, setRuntime] = useState({});
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [busy, setBusy] = useState('');
    const [query, setQuery] = useState('');
    const [search, setSearch] = useState(null);
    const [editing, setEditing] = useState(null);
    const [form] = Form.useForm();
    const mounted = useRef(false);
    const searchSequence = useRef(0);
    const login = status?.login || {};
    const loggingIn = activeLoginStates.has(login.state);

    const refresh = useCallback(async (signal) => {
        const [account, feeds, states] = await Promise.all([
            getWechatStatus({ signal }), getWechatSources({ signal }),
            requestOperation('getSpiderStatus', { signal }),
        ]);
        if (mounted.current && !signal?.aborted) {
            setStatus(account.data);
            setSources(feeds.data.sources);
            setRuntime(states.data);
        }
    }, []);

    useEffect(() => {
        mounted.current = true;
        const controller = new AbortController();
        let timer;
        const poll = async () => {
            try { await refresh(controller.signal); }
            catch (failure) { if (!controller.signal.aborted) setError(failure.message || '状态加载失败'); }
            if (!controller.signal.aborted) timer = setTimeout(poll, 3000);
        };
        void poll();
        return () => { mounted.current = false; controller.abort(); clearTimeout(timer); };
    }, [refresh]);

    const act = async (key, action, success = '') => {
        setBusy(key);
        setError('');
        setNotice('');
        try {
            await action();
            if (mounted.current) {
                setNotice(success);
                await refresh();
            }
            return true;
        } catch (failure) {
            if (mounted.current) setError(failure.message || '操作失败，请重试');
            return false;
        } finally {
            if (mounted.current) setBusy('');
        }
    };

    const findAccounts = async (begin = 0) => {
        const value = query.trim();
        if (!value) return;
        const sequence = ++searchSequence.current;
        setBusy('search');
        setError('');
        try {
            const response = await searchWechatAccounts(value, begin);
            if (mounted.current && searchSequence.current === sequence) setSearch({ ...response.data, query: value });
        } catch (failure) {
            if (mounted.current && searchSequence.current === sequence) { setSearch(null); setError(failure.message); }
        } finally {
            if (mounted.current && searchSequence.current === sequence) setBusy('');
        }
    };

    const settingsFor = (source, enabled = Boolean(source.enabled)) => ({
        enabled, default_limit: source.default_limit, default_interval: source.default_interval,
    });
    const columns = [
        { title: '公众号', dataIndex: 'name', render: (name, row) => <><strong>{name}</strong><div style={{ color: '#64748b', fontSize: 12 }}>{row.alias}</div></> },
        { title: '启用采集', key: 'enabled', render: (_, row) => <Switch checked={Boolean(row.enabled)} disabled={Boolean(busy)} onChange={(enabled) => void act(`toggle-${row.id}`, () => updateWechatSource(row.id, settingsFor(row, enabled)))} /> },
        { title: '频率 / 条数', key: 'schedule', render: (_, row) => `每 ${row.default_interval} 分钟，最多 ${row.default_limit} 篇` },
        { title: '最近采集', key: 'runtime', render: (_, row) => {
            const state = runtime[row.runtime_name] || {};
            if (state.status === 'running' || state.status === 'queued') return <Tag color="processing">{state.status === 'queued' ? '排队中' : '采集中'}</Tag>;
            if (state.last_error) return <span style={{ color: '#dc2626' }}>{state.last_error}</span>;
            return state.last_run ? <><div>{new Date(state.last_run).toLocaleString()}</div><small>最近采集 {state.items_scraped || 0} 篇</small></> : '尚未采集';
        } },
        { title: '操作', key: 'actions', render: (_, row) => <Space>
            <Button size="small" disabled={Boolean(busy) || !row.enabled || status?.state !== 'connected' || ['running', 'queued'].includes(runtime[row.runtime_name]?.status)} onClick={() => void act(`run-${row.id}`, () => requestOperation('runSpider', { path: { name: row.runtime_name }, data: { items: row.default_limit } }), '已加入采集队列，采集完成后可在 AI 资讯页查看')}>立即采集</Button>
            <Button size="small" disabled={Boolean(busy)} onClick={() => { setEditing(row); form.setFieldsValue(settingsFor(row)); }}>设置</Button>
        </Space> },
    ];

    return <div>
        {error && <Alert type="error" showIcon title={error} closable onClose={() => setError('')} style={{ marginBottom: 16 }} />}
        {notice && <Alert type="success" showIcon title={notice} style={{ marginBottom: 16 }} />}
        <Card title="微信公众平台" extra={<Tag color={status?.state === 'connected' ? 'success' : 'default'}>{labels[status?.state] || '加载中'}</Tag>} style={{ marginBottom: 16 }}>
            <p>使用管理公众号的微信扫码登录，然后搜索并添加想看的公众号。需要你有一个可登录后台的公众号，未认证也可以。</p>
            <p style={{ color: '#64748b' }}>文章保存到本项目数据库，并显示在 <a href="/?channel=ai" target="_blank" rel="noreferrer">AI 资讯</a>。展示来源提供的标题和摘要，没有摘要就只显示标题。</p>
            {status?.message && <Alert type="warning" title={status.message} style={{ marginBottom: 12 }} />}
            {status?.automation?.enabled === false && <Alert type="info" title="系统自动采集当前关闭。可先手动采集；要定时更新，请在“系统配置”中开启自动化。" style={{ marginBottom: 12 }} />}
            <Space wrap>
                <Button type="primary" loading={busy === 'login'} disabled={Boolean(busy) || loggingIn} onClick={() => void act('login', startWechatLogin)}>{status?.state === 'connected' ? '重新扫码登录' : '扫码登录'}</Button>
                {loggingIn && <Button loading={busy === 'cancel'} disabled={Boolean(busy)} onClick={() => void act('cancel', cancelWechatLogin)}>取消本次登录</Button>}
                {status?.state === 'connected' && <Button disabled={Boolean(busy)} onClick={() => void act('disconnect', disconnectWechat, '已断开登录，已采集内容仍然保留')}>断开登录</Button>}
            </Space>
            {loggingIn && <div aria-live="polite" style={{ marginTop: 16 }}>
                {login.qr_image && <img src={login.qr_image} alt="微信公众平台登录二维码" style={{ width: 200, height: 200, objectFit: 'contain' }} />}
                <p>{login.message}</p>
            </div>}
            {['expired', 'error'].includes(login.state) && <Alert type="warning" title={login.message} style={{ marginTop: 16 }} />}
            <p style={{ color: '#64748b', marginTop: 16, marginBottom: 0 }}>登录过期后需重新扫码。定时采集遵循“系统配置”的自动化开关和工作时段，需要后台 Worker 运行；电脑关机或休眠时暂停。</p>
        </Card>
        <Card title="添加公众号" style={{ marginBottom: 16 }}>
            <Space.Compact style={{ width: '100%', maxWidth: 620 }}>
                <Input aria-label="公众号名称或微信号" placeholder="输入公众号名称或微信号" value={query} disabled={Boolean(busy) || status?.state !== 'connected'} onChange={(event) => { setQuery(event.target.value); setSearch(null); searchSequence.current += 1; }} onPressEnter={() => { if (!busy) void findAccounts(); }} />
                <Button type="primary" loading={busy === 'search'} disabled={Boolean(busy) || !query.trim() || status?.state !== 'connected'} onClick={() => void findAccounts()}>搜索</Button>
            </Space.Compact>
            {search && <>
                <Table rowKey="fake_id" size="small" pagination={false} style={{ marginTop: 16 }} dataSource={search.accounts} locale={{ emptyText: '没有找到公众号，可换用微信号搜索' }} columns={[
                    { title: '名称', dataIndex: 'name' }, { title: '微信号', dataIndex: 'alias' }, { title: '简介', dataIndex: 'introduction' },
                    { title: '操作', key: 'add', render: (_, account) => {
                        const added = sources.some((source) => source.fake_id === account.fake_id);
                        return <Button size="small" disabled={added || Boolean(busy)} onClick={() => void act(`add-${account.fake_id}`, () => addWechatSource(account), '公众号已添加，将按设置自动采集，也可以点击“立即采集”')}>{added ? '已添加' : '添加'}</Button>;
                    } },
                ]} />
                <Space style={{ marginTop: 12 }}>
                    <Button disabled={Boolean(busy) || search.begin === 0} onClick={() => void findAccounts(Math.max(0, search.begin - 5))}>上一页</Button>
                    <Button disabled={Boolean(busy) || !search.has_more} onClick={() => void findAccounts(search.begin + 5)}>下一页</Button>
                </Space>
            </>}
        </Card>
        <Card title="已添加公众号" extra={<a href="/?channel=ai" target="_blank" rel="noreferrer">查看 AI 资讯</a>}>
            <Table rowKey="id" size="small" scroll={{ x: 800 }} dataSource={sources} columns={columns} pagination={false} locale={{ emptyText: <Empty description="还没有添加公众号，登录后搜索添加" /> }} />
        </Card>
        <Modal title={editing ? `${editing.name} · 采集设置` : '采集设置'} open={Boolean(editing)} confirmLoading={busy === 'settings'} onCancel={() => { if (!busy) setEditing(null); }} onOk={async () => {
            const values = await form.validateFields();
            if (await act('settings', () => updateWechatSource(editing.id, values), '采集设置已保存')) setEditing(null);
        }}>
            <Form form={form} layout="vertical">
                <Form.Item name="enabled" label="启用采集" valuePropName="checked"><Switch /></Form.Item>
                <Form.Item name="default_interval" label="更新间隔（分钟）" rules={[{ required: true }]}><InputNumber min={30} max={10080} style={{ width: '100%' }} /></Form.Item>
                <Form.Item name="default_limit" label="每次最多采集篇数" rules={[{ required: true }]}><InputNumber min={1} max={100} style={{ width: '100%' }} /></Form.Item>
            </Form>
        </Modal>
    </div>;
}
