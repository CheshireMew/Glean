import { useState } from 'react';
import { message } from 'antd';

import { runReview } from '../../api/pipeline';
import { getRequestErrorMessage } from './listStateHelpers';

export function useReviewRunner(contentKind, reviewPrompt, reviewHours, saveSettings) {
    const [running, setRunning] = useState(false);
    const [logs, setLogs] = useState([]);

    const addLog = (text) => {
        setLogs((previous) => [...previous, `${new Date().toLocaleTimeString()} ${text}`]);
    };

    const runReviewFlow = async () => {
        if (!reviewPrompt.trim()) {
            message.warning('请输入审核提示词');
            return;
        }
        const saved = await saveSettings();
        if (!saved) {
            return;
        }
        setRunning(true);
        setLogs([]);
        let totalFailed = 0;
        try {
            while (true) {
                const res = await runReview({ hours: reviewHours, kind: contentKind });
                const { attempted = 0, processed, failed = 0, discarded, selected, remaining = 0, enrichment_remaining: enrichmentRemaining = 0 } = res.data;
                const remainingWork = Math.max(remaining, enrichmentRemaining);
                totalFailed += failed;
                addLog(`本轮尝试 ${attempted} 条，成功 ${processed} 条，失败 ${failed} 条，舍弃 ${discarded} 条，选入 ${selected} 条，待审核 ${remaining} 条，待补充 ${enrichmentRemaining} 条`);
                if (remainingWork === 0) {
                    break;
                }
            }
            if (totalFailed > 0) {
                message.warning(`审核流程结束，累计 ${totalFailed} 次处理失败；失败原因已保留，可在待审核列表中重试`);
            } else {
                message.success('审核完成');
            }
        } catch (error) {
            message.error(`审核失败: ${getRequestErrorMessage(error, '审核失败')}`);
        } finally {
            setRunning(false);
        }
    };

    return {
        running,
        logs,
        runReviewFlow,
    };
}
