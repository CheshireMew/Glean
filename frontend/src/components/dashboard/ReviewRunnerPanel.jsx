import React from 'react';
import PropTypes from 'prop-types';
import { Alert, Button, Card, Space, Typography } from 'antd';

import { useReviewRunner } from '../../hooks/dashboard/useReviewRunner';
import { useReviewSettings } from '../../hooks/dashboard/useReviewSettings';
import TimeRangeSelect from './TimeRangeSelect';

export default function ReviewRunnerPanel({ contentKind }) {
    const {
        reviewPrompt,
        reviewHours,
        loadState,
        setReviewHours,
        reload,
        saveSettings,
    } = useReviewSettings(contentKind);
    const { running, logs, runReviewFlow } = useReviewRunner(
        contentKind,
        reviewPrompt,
        reviewHours,
        saveSettings,
    );

    return (
        <Card title="审核执行" loading={loadState.loading} style={{ marginBottom: 16 }}>
            {loadState.error && (
                <Alert
                    type="error"
                    showIcon
                    title="当前审核配置读取失败"
                    description={loadState.error}
                    action={<Button onClick={reload}>重新读取</Button>}
                    style={{ marginBottom: 16 }}
                />
            )}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24 }}>
                <div style={{ flex: '1 1 360px', minWidth: 0 }}>
                    <Space orientation="vertical" style={{ width: '100%' }}>
                        <Alert type="info" showIcon title="审核标准统一在“系统配置 → 内容档案”中维护" />
                        <Typography.Paragraph ellipsis={{ rows: 4, expandable: true }} style={{ whiteSpace: 'pre-wrap' }}>
                            {reviewPrompt || '当前默认内容档案尚未配置审核标准'}
                        </Typography.Paragraph>
                        <Space wrap>
                            <span>本次手动扫描范围：</span>
                            <TimeRangeSelect disabled={!loadState.loaded || running} value={reviewHours} onChange={setReviewHours} />
                            <Button type="primary" disabled={!loadState.loaded} onClick={runReviewFlow} loading={running}>开始审核</Button>
                            <Button disabled={!loadState.loaded || running} onClick={saveSettings}>保存手动扫描范围</Button>
                        </Space>
                    </Space>
                </div>
                <div style={{ flex: '1 1 360px', minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                    <div style={{ marginBottom: 8 }}>运行日志：</div>
                    <div role="log" aria-live="polite" style={{ background: '#111827', color: '#86efac', padding: 12, borderRadius: 8, fontSize: 12, height: 240, overflowY: 'auto', fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace', width: '100%' }}>
                        <div style={{ color: '#9ca3af', marginBottom: 8, borderBottom: '1px solid #374151', paddingBottom: 4 }}>&gt; REVIEW LOG</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            {logs.length === 0 && !running ? <div style={{ color: '#6b7280' }}>&gt; 等待运行</div> : logs.map((log, index) => <div key={`${index}-${log}`} style={{ wordBreak: 'break-all' }}>&gt; {log}</div>)}
                            {running && <div style={{ color: '#d1d5db', fontStyle: 'italic' }}>正在运行…</div>}
                        </div>
                    </div>
                </div>
            </div>
        </Card>
    );
}

ReviewRunnerPanel.propTypes = {
    contentKind: PropTypes.string.isRequired,
};
