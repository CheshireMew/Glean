import { useCallback, useEffect, useState } from 'react';
import { Modal, message } from 'antd';

import { listDeliveryOperations, retryDelivery, sendSelectedContent, triggerDailyPush } from '../../api/pipeline';
import { API_RESOURCE, subscribeResource } from '../../api/resources';
import { getRequestErrorMessage } from './listStateHelpers';

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function createOperationKey(prefix) {
    const randomPart = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return `${prefix}:${randomPart}`;
}

function localDateSignature() {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${now.getFullYear()}-${month}-${day}`;
}

export function useExportDelivery(contentKind, visibleItems, selectedIds) {
    const [sendingToTg, setSendingToTg] = useState(false);
    const [triggeringDaily, setTriggeringDaily] = useState(false);
    const [pendingOperations, setPendingOperations] = useState([]);

    const getSelectedItems = () => visibleItems.filter((item) => selectedIds.includes(item.outputKey));
    // Preserve recovery keys so a rename cannot trigger a duplicate delivery.
    const sendStorageKey = `ainews.delivery.manual.${contentKind}`;
    const dailyStorageKey = `ainews.delivery.daily.${contentKind}`;

    const refreshPendingOperations = useCallback(async () => {
        try {
            const response = await listDeliveryOperations();
            setPendingOperations((response.data || []).filter((item) => item.status !== 'sent').slice(0, 10));
        } catch (error) {
            console.error('Failed to load delivery operations:', error);
        }
    }, []);

    useEffect(() => {
        const timer = setTimeout(() => void refreshPendingOperations(), 0);
        const unsubscribe = subscribeResource(
            API_RESOURCE.DELIVERY_OPERATIONS,
            () => void refreshPendingOperations(),
        );
        return () => { clearTimeout(timer); unsubscribe(); };
    }, [refreshPendingOperations]);

    const getOrCreateStoredOperation = (storageKey, prefix, signature) => {
        try {
            const stored = JSON.parse(localStorage.getItem(storageKey) || 'null');
            if (stored?.operationKey && stored.signature === signature) {
                return stored.operationKey;
            }
        } catch {
            // Invalid local state is replaced below.
        }
        const operationKey = createOperationKey(prefix);
        localStorage.setItem(storageKey, JSON.stringify({ operationKey, signature }));
        return operationKey;
    };

    const clearStoredOperation = (storageKey) => localStorage.removeItem(storageKey);

    const copyPlainText = async () => {
        const selected = getSelectedItems();
        if (selected.length === 0) {
            message.warning('请先选择要复制的内容');
            return;
        }
        const text = selected
            .map((item) => `${item.title}\n\n${item.content || item.review_summary || ''}`.trim())
            .join('\n\n---\n\n');
        try {
            await navigator.clipboard.writeText(text);
            message.success(`已复制 ${selected.length} 条内容`);
        } catch {
            message.error('复制失败，请检查浏览器剪贴板权限');
        }
    };

    const copyMarkdown = async () => {
        const selected = getSelectedItems();
        if (selected.length === 0) {
            message.warning('请先选择要复制的内容');
            return;
        }
        const text = selected
            .map((item) => {
                const content = (item.content || item.review_summary || '暂无内容').replace(/\n/g, '\n>\n> ');
                return `### [${item.title}](${item.source_url})\n\n> ${content}\n\n---`;
            })
            .join('\n\n');
        try {
            await navigator.clipboard.writeText(text);
            message.success(`已复制 ${selected.length} 条内容`);
        } catch {
            message.error('复制失败，请检查浏览器剪贴板权限');
        }
    };

    const copyTelegramHtml = async () => {
        const selected = getSelectedItems();
        if (selected.length === 0) {
            message.warning('请先选择要复制的内容');
            return;
        }
        const htmlContent = selected
            .map((item) => `⚡ <b><a href="${escapeHtml(item.source_url || '')}">${escapeHtml(item.title)}</a></b>`)
            .join('<br><br>\n');
        const plainText = selected.map((item) => `${item.title}\n${item.source_url}`).join('\n\n');
        try {
            const htmlBlob = new Blob([htmlContent], { type: 'text/html' });
            const textBlob = new Blob([plainText], { type: 'text/plain' });
            await navigator.clipboard.write([
                new ClipboardItem({
                    'text/html': htmlBlob,
                    'text/plain': textBlob,
                }),
            ]);
            message.success(`已复制 ${selected.length} 条内容`);
        } catch (error) {
            console.error('Copy failed:', error);
            message.error('复制失败，请重试');
        }
    };

    const performTelegramSend = async (selected) => {
        try {
            setSendingToTg(true);
            const entryRefs = selected.map((item) => item.outputRef);
            const signature = JSON.stringify(entryRefs);
            const operationKey = getOrCreateStoredOperation(sendStorageKey, 'manual-entry', signature);
            const res = await sendSelectedContent(entryRefs, operationKey);
            if (res.data.status === 'sent') {
                message.success(`成功发送 ${res.data.sent_count || selected.length} 条内容到 Telegram`);
                clearStoredOperation(sendStorageKey);
            } else {
                showDeliveryRecovery(res.data, operationKey, () => clearStoredOperation(sendStorageKey));
            }
        } catch (error) {
            message.error(getRequestErrorMessage(error, '发送失败，请检查 Telegram 配置'));
        } finally {
            setSendingToTg(false);
        }
    };

    const sendToTelegram = () => {
        const selected = getSelectedItems();
        if (selected.length === 0) {
            message.warning('请先选择要发送的内容');
            return;
        }
        const preview = selected.slice(0, 3).map((item) => `“${item.title}”`).join('、');
        const remaining = selected.length > 3 ? `等 ${selected.length} 条内容` : `${selected.length} 条内容`;
        Modal.confirm({
            title: `确认发送 ${selected.length} 条内容到 Telegram？`,
            content: `发送目标为当前配置的 Telegram 会话，将发送${remaining}。内容预览：${preview}`,
            okText: '确认发送',
            cancelText: '取消',
            onOk: () => performTelegramSend(selected),
        });
    };

    const performDailyDelivery = async () => {
        try {
            setTriggeringDaily(true);
            message.loading('正在触发日报推送...', 1);
            const signature = `daily:${contentKind}:${localDateSignature()}`;
            const operationKey = getOrCreateStoredOperation(dailyStorageKey, `manual-daily-${contentKind}`, signature);
            const res = await triggerDailyPush(contentKind, operationKey);
            if (res.data?.status === 'success') {
                message.success(`推送成功: 已发送 ${res.data.count} 条内容`);
                clearStoredOperation(dailyStorageKey);
            } else if (res.data?.status === 'skipped') {
                message.warning(`推送跳过: ${res.data.message}`);
                clearStoredOperation(dailyStorageKey);
            } else {
                showDeliveryRecovery(res.data, operationKey, () => clearStoredOperation(dailyStorageKey));
            }
        } catch (error) {
            message.error(`触发失败: ${getRequestErrorMessage(error, '触发失败')}`);
        } finally {
            setTriggeringDaily(false);
        }
    };

    const triggerDailyDelivery = () => {
        const kindLabel = contentKind === 'article' ? '文章' : '快讯';
        Modal.confirm({
            title: `确认触发今天的${kindLabel}日报？`,
            content: `系统会按当前${kindLabel}日报规则筛选内容，并发送到当前配置的 Telegram 会话。`,
            okText: '确认触发',
            cancelText: '取消',
            onOk: performDailyDelivery,
        });
    };

    const retryPendingOperation = async (operationKey) => {
        try {
            const result = await retryDelivery(operationKey);
            if (result.data?.status === 'sent') {
                message.success('交付已恢复完成');
            } else {
                message.warning(result.data?.last_error || '交付仍未完成');
            }
        } catch (error) {
            message.error(getRequestErrorMessage(error, '恢复交付失败'));
        }
    };

    const showDeliveryRecovery = (result, operationKey, onRecovered) => {
        Modal.confirm({
            title: result.needs_attention ? '发送结果不确定' : '发送未完成',
            content: `${result.last_error || '部分消息尚未送达'}。已确认成功的分段不会重复发送。是否重新尝试未完成分段？`,
            okText: '确认重试',
            cancelText: '暂不处理',
            async onOk() {
                const retryResult = await retryDelivery(operationKey);
                if (retryResult.data?.status === 'sent') {
                    message.success('未完成分段已补发，交付现已完成');
                    onRecovered();
                    return;
                }
                throw new Error(retryResult.data?.last_error || '交付仍未完成');
            },
        });
    };

    return {
        sendingToTg,
        triggeringDaily,
        copyPlainText,
        copyMarkdown,
        copyTelegramHtml,
        sendToTelegram,
        triggerDailyDelivery,
        pendingOperations,
        refreshPendingOperations,
        retryPendingOperation,
    };
}
