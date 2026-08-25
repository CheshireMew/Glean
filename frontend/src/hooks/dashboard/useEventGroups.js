import { useCallback, useMemo, useState } from 'react';

import { deleteSourceContent, listContentEvents } from '../../api/content';
import { runListAction } from './listStateHelpers';
import { usePaginatedContentList } from './usePaginatedContentList';

export function useEventGroups(contentKind) {
    const [expandedGroups, setExpandedGroups] = useState(new Set());
    const initialMeta = useMemo(() => ({ summary: { multi_source: 0, single_source: 0 } }), []);
    const normalizeResponse = useCallback((payload, page, pageSize) => ({
        items: payload.results || [],
        pagination: {
            current: payload.page || page,
            pageSize: payload.limit || pageSize,
            total: payload.total || 0,
        },
        meta: {
            summary: payload.summary || { multi_source: 0, single_source: 0 },
        },
    }), []);
    const listState = usePaginatedContentList({
        contentKind,
        loadPage: listContentEvents,
        initialPageSize: 20,
        errorMessage: '加载事件聚合失败',
        initialMeta,
        normalizeResponse,
    });

    const toggleGroup = (groupKey) => {
        setExpandedGroups((previous) => {
            const next = new Set(previous);
            if (next.has(groupKey)) {
                next.delete(groupKey);
            } else {
                next.add(groupKey);
            }
            return next;
        });
    };

    const deleteGroupItem = async (id) => {
        await runListAction({
            action: () => deleteSourceContent(id),
            successMessage: '删除成功',
            errorMessage: '删除失败',
        });
    };

    const visibleExpandedGroups = useMemo(() => {
        const validIds = new Set(listState.items.map((group) => group.event.id));
        return new Set([...expandedGroups].filter((groupId) => validIds.has(groupId)));
    }, [expandedGroups, listState.items]);

    return {
        groups: listState.items,
        loading: listState.loading,
        loaded: listState.loaded,
        error: listState.error,
        stale: listState.stale,
        pagination: listState.pagination,
        summary: listState.meta?.summary || { multi_source: 0, single_source: 0 },
        filterSource: listState.filterSource,
        filterKeyword: listState.filterKeyword,
        expandedGroups: visibleExpandedGroups,
        setFilterSource: listState.setFilterSource,
        setFilterKeyword: listState.setFilterKeyword,
        toggleGroup,
        fetchGroups: listState.fetchItems,
        retry: listState.retry,
        deleteGroupItem,
    };
}
