import React, { useEffect, useState } from 'react';
import { Alert, Button, Card, Col, Form, Input, Modal, Row, Select, Space, Statistic, Table, Tabs, Tag, message } from 'antd';
import { ExperimentOutlined, ReloadOutlined } from '@ant-design/icons';

import {
    createAiEvaluationCase,
    getAiQualitySummary,
    listAiEvaluationCases,
    listAiEvaluationRuns,
    listAiInvocations,
    runAiEvaluation,
} from '../../api/aiQuality';
import { formatLocalDateTime } from '../../utils/time';

const EMPTY_STATE = { loading: true, error: '', summary: null, invocations: [], invocationTotal: 0, cases: [], runs: [] };

function JsonEditor({ value = '{}', onChange, rows = 8 }) {
    return <Input.TextArea className="font-mono" rows={rows} value={value} onChange={(event) => onChange(event.target.value)} />;
}

export default function AiQualityTab() {
    const [state, setState] = useState(EMPTY_STATE);
    const [caseModalOpen, setCaseModalOpen] = useState(false);
    const [running, setRunning] = useState(false);
    const [form] = Form.useForm();

    const load = async () => {
        setState((current) => ({ ...current, loading: true, error: '' }));
        try {
            const [summary, invocations, cases, runs] = await Promise.all([
                getAiQualitySummary(30),
                listAiInvocations({ page: 1, limit: 100, days: 30 }),
                listAiEvaluationCases(),
                listAiEvaluationRuns({ limit: 100 }),
            ]);
            setState({
                loading: false,
                error: '',
                summary: summary.data,
                invocations: invocations.data?.data || [],
                invocationTotal: invocations.data?.total || 0,
                cases: cases.data || [],
                runs: runs.data || [],
            });
        } catch (error) {
            setState((current) => ({ ...current, loading: false, error: error.message || 'AI 质量数据加载失败' }));
        }
    };

    useEffect(() => {
        const timer = window.setTimeout(() => { void load(); }, 0);
        return () => window.clearTimeout(timer);
    }, []);

    const createCase = async () => {
        try {
            const values = await form.validateFields();
            let input;
            let expected;
            try {
                input = JSON.parse(values.input_json);
                expected = JSON.parse(values.expected_json);
            } catch {
                message.error('输入和期望都必须是合法 JSON');
                return;
            }
            await createAiEvaluationCase({ ...values, input, expected, enabled: true });
            setCaseModalOpen(false);
            form.resetFields();
            message.success('评测样例已保存');
            await load();
        } catch (error) {
            if (!error?.errorFields) message.error(error.message || '保存失败');
        }
    };

    const run = async () => {
        setRunning(true);
        try {
            const response = await runAiEvaluation({});
            message.success(`评测完成：${response.data.passed}/${response.data.total} 通过`);
            await load();
        } catch (error) {
            message.error(error.message || '评测执行失败');
        } finally {
            setRunning(false);
        }
    };

    const overall = state.summary?.overall || {};
    const feedbackSummary = state.summary?.feedback_summary || {};
    const overview = (
        <>
            <Row gutter={[16, 16]}>
                <Col xs={12} lg={4}><Card><Statistic title="调用次数" value={overall.calls || 0} /></Card></Col>
                <Col xs={12} lg={4}><Card><Statistic title="成功率" value={(overall.success_rate || 0) * 100} precision={1} suffix="%" /></Card></Col>
                <Col xs={12} lg={4}><Card><Statistic title="平均耗时" value={overall.average_duration_ms || 0} precision={0} suffix="ms" /></Card></Col>
                <Col xs={12} lg={4}><Card><Statistic title="输入 Token" value={overall.input_tokens || 0} /></Card></Col>
                <Col xs={12} lg={4}><Card><Statistic title="输出 Token" value={overall.output_tokens || 0} /></Card></Col>
                <Col xs={12} lg={4}><Card><Statistic title="估算费用" value={overall.estimated_cost || 0} precision={4} prefix="$" /></Card></Col>
            </Row>
            <Table
                style={{ marginTop: 16 }}
                rowKey={(row) => `${row.provider_name}:${row.model}:${row.stage}`}
                dataSource={state.summary?.groups || []}
                pagination={false}
                columns={[
                    { title: '端点', dataIndex: 'provider_name' },
                    { title: '模型', dataIndex: 'model' },
                    { title: '阶段', dataIndex: 'stage' },
                    { title: '调用', dataIndex: 'calls' },
                    { title: '成功', dataIndex: 'successes' },
                    { title: '平均耗时', dataIndex: 'average_duration_ms', render: (value) => `${Math.round(value || 0)} ms` },
                    { title: 'Token', dataIndex: 'total_tokens' },
                    { title: '费用', dataIndex: 'estimated_cost', render: (value) => `$${Number(value || 0).toFixed(4)}` },
                ]}
                scroll={{ x: 'max-content' }}
            />
            <h3 style={{ marginTop: 24 }}>人工采纳与纠错</h3>
            <Row gutter={[16, 16]}>
                <Col xs={12} lg={4}><Card><Statistic title="反馈数" value={feedbackSummary.total || 0} /></Card></Col>
                <Col xs={12} lg={4}><Card><Statistic title="采纳率" value={(feedbackSummary.adoption_rate || 0) * 100} precision={1} suffix="%" /></Card></Col>
                <Col xs={12} lg={4}><Card><Statistic title="修改率" value={(feedbackSummary.edit_rate || 0) * 100} precision={1} suffix="%" /></Card></Col>
                <Col xs={12} lg={4}><Card><Statistic title="拒绝率" value={(feedbackSummary.rejection_rate || 0) * 100} precision={1} suffix="%" /></Card></Col>
                <Col xs={12} lg={4}><Card><Statistic title="错误率" value={(feedbackSummary.incorrect_rate || 0) * 100} precision={1} suffix="%" /></Card></Col>
                <Col xs={12} lg={4}><Card><Statistic title="平均质量分" value={feedbackSummary.average_quality_score || 0} precision={2} suffix="/ 5" /></Card></Col>
            </Row>
            <Table
                style={{ marginTop: 16 }}
                rowKey="outcome"
                dataSource={state.summary?.feedback || []}
                pagination={false}
                columns={[
                    { title: '反馈结果', dataIndex: 'outcome', render: (value) => ({ accepted: '直接采纳', edited: '修改后采纳', rejected: '拒绝', incorrect: '事实错误' }[value] || value) },
                    { title: '数量', dataIndex: 'count' },
                    { title: '平均质量分', dataIndex: 'average_quality_score', render: (value) => value == null ? '—' : Number(value).toFixed(2) },
                ]}
            />
        </>
    );

    const invocationTable = <Table rowKey="id" dataSource={state.invocations} pagination={{ pageSize: 20, total: state.invocationTotal }} columns={[
        { title: '时间', dataIndex: 'started_at', render: formatLocalDateTime, width: 170 },
        { title: '阶段', dataIndex: 'stage' },
        { title: '端点', dataIndex: 'provider_name' },
        { title: '模型', dataIndex: 'model' },
        { title: '提示词版本', dataIndex: 'prompt_version' },
        { title: '尝试', dataIndex: 'attempt' },
        { title: '耗时', dataIndex: 'duration_ms', render: (value) => `${value || 0} ms` },
        { title: 'Token', render: (_, row) => `${row.input_tokens || 0} + ${row.output_tokens || 0}` },
        { title: '结果', dataIndex: 'success', render: (value) => <Tag color={value ? 'green' : 'red'}>{value ? '成功' : '失败'}</Tag> },
        { title: '错误', dataIndex: 'error_message', ellipsis: true },
    ]} scroll={{ x: 'max-content' }} />;

    const evaluationPanel = <>
        <Space wrap style={{ marginBottom: 16 }}><Button type="primary" icon={<ExperimentOutlined />} loading={running} onClick={run} disabled={state.cases.length === 0}>运行全部评测</Button><Button onClick={() => setCaseModalOpen(true)}>添加评测样例</Button></Space>
        <Table rowKey="id" dataSource={state.cases} pagination={false} columns={[
            { title: '名称', dataIndex: 'name' },
            { title: '类型', dataIndex: 'content_type' },
            { title: '阶段', dataIndex: 'stage' },
            { title: '状态', dataIndex: 'enabled', render: (value) => <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '停用'}</Tag> },
            { title: '期望', dataIndex: 'expected', render: (value) => <code>{JSON.stringify(value)}</code> },
        ]} />
        <h3 style={{ marginTop: 24 }}>最近评测结果</h3>
        <Table rowKey="id" dataSource={state.runs} pagination={{ pageSize: 20 }} columns={[
            { title: '时间', dataIndex: 'created_at', render: formatLocalDateTime },
            { title: '运行', dataIndex: 'run_key', ellipsis: true },
            { title: '样例', dataIndex: 'case_name' },
            { title: '端点 / 模型', render: (_, row) => `${row.provider_name} / ${row.model}` },
            { title: '结果', dataIndex: 'passed', render: (value) => <Tag color={value ? 'green' : 'red'}>{value ? '通过' : '未通过'}</Tag> },
        ]} />
    </>;

    return (
        <div>
            {state.error && <Alert type="error" showIcon message={state.error} action={<Button onClick={load}>重试</Button>} style={{ marginBottom: 16 }} />}
            <Space style={{ marginBottom: 16 }}><Button icon={<ReloadOutlined />} onClick={load} loading={state.loading}>刷新</Button><span style={{ color: '#64748b' }}>最近 30 天，人工修改反馈不会自动改写提示词</span></Space>
            <Tabs items={[{ key: 'overview', label: '质量概览', children: overview }, { key: 'calls', label: '调用记录', children: invocationTable }, { key: 'evaluation', label: `固定评测 (${state.cases.length})`, children: evaluationPanel }]} />
            <Modal title="添加固定评测样例" open={caseModalOpen} onCancel={() => setCaseModalOpen(false)} onOk={createCase} width={760}>
                <Form form={form} layout="vertical" initialValues={{ content_type: 'news', stage: 'review', input_json: '{\n  "title": "",\n  "content": "",\n  "review_prompt": ""\n}', expected_json: '{\n  "passed": true,\n  "score_min": 7\n}' }}>
                    <Form.Item name="name" label="样例名称" rules={[{ required: true }]}><Input /></Form.Item>
                    <Space align="start"><Form.Item name="content_type" label="类型"><Select style={{ width: 120 }} options={[{ value: 'news', label: '快讯' }, { value: 'article', label: '文章' }]} /></Form.Item><Form.Item name="stage" label="阶段"><Select style={{ width: 140 }} options={[{ value: 'review', label: '审核' }, { value: 'enrichment', label: '内容补充' }]} /></Form.Item></Space>
                    <Form.Item name="input_json" label="输入 JSON" rules={[{ required: true }]}><JsonEditor /></Form.Item>
                    <Form.Item name="expected_json" label="期望 JSON" rules={[{ required: true }]}><JsonEditor /></Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
