import React, { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { Alert, Button, Col, Divider, Form, Input, InputNumber, Modal, Row, Select, Space, Spin, Table, Tabs, Timeline, Typography, message } from 'antd';

import { addEditorialFeedback, getEditorialEntry, restoreEditorialRevision, updateEditorialEntry } from '../../api/editorial';
import { formatLocalDateTime } from '../../utils/time';

function parseArray(value) {
    if (Array.isArray(value)) return value;
    try { return JSON.parse(value || '[]'); } catch { return []; }
}

const DIFF_LABELS = {
    title: '标题', review_summary: '审核摘要', review_reason: '入选依据', review_score: '评分',
    review_category: '栏目', review_tags: '标签', enriched_summary: '综合摘要',
    enriched_impact: '为什么重要', enriched_background: '背景', enrichment_citations: '引用',
};

function comparableValue(value) {
    if (Array.isArray(value) || (value && typeof value === 'object')) return JSON.stringify(value);
    if (typeof value === 'string' && ['[', '{'].includes(value.trim()[0])) {
        try { return JSON.stringify(JSON.parse(value)); } catch { return value; }
    }
    return value == null ? '' : String(value);
}

function diffRows(entry) {
    const original = entry?.revisions?.[entry.revisions.length - 1]?.snapshot;
    if (!original) return [];
    return Object.keys(DIFF_LABELS).filter((field) => comparableValue(original[field]) !== comparableValue(entry[field])).map((field) => ({
        field, label: DIFF_LABELS[field], before: comparableValue(original[field]), after: comparableValue(entry[field]),
    }));
}

export default function EditorialEntryModal({ entryId, open, onClose, onSaved }) {
    const [form] = Form.useForm();
    const [state, setState] = useState({ loading: false, saving: false, error: '', entry: null });

    const load = async () => {
        if (!entryId) return;
        setState((current) => ({ ...current, loading: true, error: '' }));
        try {
            const response = await getEditorialEntry(entryId);
            const entry = response.data;
            form.setFieldsValue({
                title: entry.title,
                review_summary: entry.review_summary,
                review_reason: entry.review_reason,
                review_score: entry.review_score,
                review_category: entry.review_category,
                review_tags: entry.tags || parseArray(entry.review_tags),
                enriched_summary: entry.enriched_summary,
                enriched_impact: entry.enriched_impact,
                enriched_background: entry.enriched_background,
                enrichment_citations_text: JSON.stringify(entry.citations || parseArray(entry.enrichment_citations), null, 2),
                change_note: '',
                quality_score: undefined,
            });
            setState({ loading: false, saving: false, error: '', entry });
        } catch (error) {
            setState({ loading: false, saving: false, error: error.message || '编辑内容加载失败', entry: null });
        }
    };

    useEffect(() => {
        if (open) void load();
        else form.resetFields();
        // load is intentionally keyed by the selected entry.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [entryId, open]);

    const save = async () => {
        try {
            const values = await form.validateFields();
            let citations;
            try {
                citations = JSON.parse(values.enrichment_citations_text || '[]');
                if (!Array.isArray(citations)) throw new Error('引用必须是数组');
            } catch (error) {
                form.setFields([{ name: 'enrichment_citations_text', errors: [error.message || '引用 JSON 格式错误'] }]);
                return;
            }
            setState((current) => ({ ...current, saving: true, error: '' }));
            const payload = { ...values, enrichment_citations: citations };
            delete payload.enrichment_citations_text;
            const response = await updateEditorialEntry(entryId, payload);
            setState({ loading: false, saving: false, error: '', entry: response.data });
            message.success('修订已保存');
            onSaved?.(response.data);
            await load();
        } catch (error) {
            if (error?.errorFields) return;
            setState((current) => ({ ...current, saving: false, error: error.message || '保存失败' }));
        }
    };

    const restore = async (revisionNumber) => {
        setState((current) => ({ ...current, saving: true, error: '' }));
        try {
            await restoreEditorialRevision(entryId, revisionNumber);
            message.success(`已恢复修订 ${revisionNumber}`);
            await load();
            onSaved?.();
        } catch (error) {
            setState((current) => ({ ...current, saving: false, error: error.message || '恢复失败' }));
        }
    };

    const accept = async () => {
        try {
            await addEditorialFeedback(entryId, { outcome: 'accepted', notes: '人工确认可用' });
            message.success('已记录人工确认');
            await load();
        } catch (error) {
            setState((current) => ({ ...current, error: error.message || '反馈保存失败' }));
        }
    };

    const editPanel = (
        <Form form={form} layout="vertical" disabled={state.loading || state.saving}>
            <Form.Item name="title" label="发布标题" rules={[{ required: true, message: '请输入标题' }]}><Input maxLength={500} showCount /></Form.Item>
            <Row gutter={16}>
                <Col xs={24} md={8}><Form.Item name="review_score" label="编辑评分"><InputNumber min={0} max={10} style={{ width: '100%' }} /></Form.Item></Col>
                <Col xs={24} md={8}><Form.Item name="review_category" label="栏目"><Input maxLength={100} /></Form.Item></Col>
                <Col xs={24} md={8}><Form.Item name="quality_score" label="本次 AI 质量"><Select allowClear options={[1, 2, 3, 4, 5].map((value) => ({ value, label: `${value} / 5` }))} /></Form.Item></Col>
            </Row>
            <Form.Item name="review_tags" label="标签"><Select mode="tags" tokenSeparators={[',', '，']} /></Form.Item>
            <Form.Item name="review_summary" label="审核摘要"><Input.TextArea autoSize={{ minRows: 3, maxRows: 8 }} /></Form.Item>
            <Form.Item name="review_reason" label="入选依据"><Input.TextArea autoSize={{ minRows: 2, maxRows: 6 }} /></Form.Item>
            <Divider orientation="left">引用受限补充</Divider>
            <Form.Item name="enriched_summary" label="综合摘要"><Input.TextArea autoSize={{ minRows: 4, maxRows: 12 }} /></Form.Item>
            <Form.Item name="enriched_impact" label="为什么重要"><Input.TextArea autoSize={{ minRows: 3, maxRows: 10 }} /></Form.Item>
            <Form.Item name="enriched_background" label="背景"><Input.TextArea autoSize={{ minRows: 3, maxRows: 12 }} /></Form.Item>
            <Form.Item name="enrichment_citations_text" label="引用 JSON" rules={[{ required: true, message: '引用必须是 JSON 数组' }]}><Input.TextArea rows={8} className="font-mono" /></Form.Item>
            <Form.Item name="change_note" label="修订说明"><Input maxLength={1000} placeholder="说明为什么修改，便于以后复盘" /></Form.Item>
        </Form>
    );

    const historyPanel = state.entry ? (
        <div>
            <Space wrap style={{ marginBottom: 16 }}>
                <Button onClick={accept}>确认当前 AI 结果可用</Button>
                <span style={{ color: '#64748b' }}>当前编辑版本：{state.entry.editorial_version || 0}</span>
            </Space>
            <Divider orientation="left">AI 原稿与当前版本</Divider>
            {diffRows(state.entry).length ? <Table
                rowKey="field"
                size="small"
                pagination={false}
                dataSource={diffRows(state.entry)}
                columns={[
                    { title: '字段', dataIndex: 'label', width: 110 },
                    { title: 'AI 原稿', dataIndex: 'before', render: (value) => <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0 }} ellipsis={{ rows: 5, expandable: true, symbol: '展开' }}>{value || '—'}</Typography.Paragraph> },
                    { title: '当前人工版本', dataIndex: 'after', render: (value) => <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0 }} ellipsis={{ rows: 5, expandable: true, symbol: '展开' }}>{value || '—'}</Typography.Paragraph> },
                ]}
            /> : <Alert type="success" showIcon message="当前内容与 AI 原稿一致" />}
            <Divider orientation="left">完整修订链</Divider>
            <Timeline items={(state.entry.revisions || []).map((revision, index) => ({
                color: index === 0 ? 'blue' : 'gray',
                children: (
                    <div>
                        <strong>修订 {revision.revision_number}</strong> · {revision.actor} · {formatLocalDateTime(revision.created_at)}
                        {revision.change_note && <p style={{ margin: '4px 0', color: '#475569' }}>{revision.change_note}</p>}
                        {revision.changed_fields?.length > 0 && <p style={{ margin: '4px 0', color: '#94a3b8' }}>字段：{revision.changed_fields.join('、')}</p>}
                        {index !== 0 && <Button size="small" onClick={() => restore(revision.revision_number)} disabled={state.saving}>恢复到此版本</Button>}
                    </div>
                ),
            }))} />
            <Divider orientation="left">人工反馈</Divider>
            {(state.entry.feedback || []).map((feedback) => <p key={feedback.id}><strong>{feedback.outcome}</strong> · {feedback.actor} · {formatLocalDateTime(feedback.created_at)}{feedback.notes ? `：${feedback.notes}` : ''}</p>)}
        </div>
    ) : null;

    return (
        <Modal
            title="内容编辑与修订"
            open={open}
            onCancel={onClose}
            width={920}
            destroyOnHidden
            footer={<Space><Button onClick={onClose}>关闭</Button><Button type="primary" loading={state.saving} onClick={save}>保存新修订</Button></Space>}
        >
            {state.error && <Alert type="error" showIcon message={state.error} action={<Button size="small" onClick={load}>重试</Button>} style={{ marginBottom: 16 }} />}
            {state.loading ? <div style={{ padding: 48, textAlign: 'center' }}><Spin /></div> : <Tabs items={[{ key: 'edit', label: '编辑', children: editPanel }, { key: 'history', label: `修订记录 (${state.entry?.revisions?.length || 0})`, children: historyPanel }]} />}
        </Modal>
    );
}

EditorialEntryModal.propTypes = {
    entryId: PropTypes.number,
    open: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    onSaved: PropTypes.func,
};
