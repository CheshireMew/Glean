import { useState } from 'react';
import { message } from 'antd';

import { deleteArchiveContent, restoreBlockedEntry } from '../../api/content';
import { applyBlocklist, restoreBlockedContent } from '../../api/pipeline';
import { getRequestErrorMessage, runListAction } from './listStateHelpers';

export function useBlocklistRunner(contentKind) {
    const [filterTimeRange, setFilterTimeRange] = useState(6);
    const [filtering, setFiltering] = useState(false);

    const applyCurrentBlocklist = async () => {
        setFiltering(true);
        try {
            await runListAction({
                action: () => applyBlocklist(filterTimeRange, contentKind),
                successMessage: (res) => {
                    const stats = res.data.stats;
                    return `处理完成：扫描 ${stats.scanned} 条，拦截 ${stats.blocked} 条，送审 ${stats.review || 0} 条`;
                },
                errorMessage: '执行失败',
            });
        } catch (error) {
            message.error(`执行失败: ${getRequestErrorMessage(error, '执行失败')}`);
        } finally {
            setFiltering(false);
        }
    };

    const restoreAll = async () => {
        await runListAction({
            action: () => restoreBlockedContent(contentKind),
            successMessage: (res) => `批量还原成功！还原了 ${res.data.restored_count} 条内容`,
            errorMessage: '批量还原失败',
        });
    };

    const restoreItem = async (id) => {
        await runListAction({
            action: () => restoreBlockedEntry(id),
            successMessage: '还原成功',
            errorMessage: '还原失败',
        });
    };

    const deleteBlockedItem = async (id) => {
        await runListAction({
            action: () => deleteArchiveContent(id),
            successMessage: '删除成功',
            errorMessage: '删除失败',
        });
    };

    return {
        filterTimeRange,
        filtering,
        setFilterTimeRange,
        applyCurrentBlocklist,
        restoreAll,
        restoreItem,
        deleteBlockedItem,
    };
}
