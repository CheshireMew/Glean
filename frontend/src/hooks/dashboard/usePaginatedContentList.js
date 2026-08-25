import { useCallback, useEffect, useRef, useState } from 'react';
import { message } from 'antd';
import { API_RESOURCE, subscribeResource } from '../../api/resources';

function defaultNormalizeResponse(payload, page, pageSize) {
    return {
        items: payload.data || [],
        pagination: {
            current: payload.page || page,
            pageSize: payload.limit || pageSize,
            total: payload.total || 0,
        },
        meta: null,
    };
}

export function usePaginatedContentList({
    contentKind,
    loadPage,
    active = true,
    initialPageSize = 10,
    enableSourceFilter = true,
    errorMessage = '加载内容失败',
    initialMeta = null,
    normalizeResponse = defaultNormalizeResponse,
}) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(false);
    const [pagination, setPagination] = useState({ current: 1, pageSize: initialPageSize, total: 0 });
    const [meta, setMeta] = useState(initialMeta);
    const [loadState, setLoadState] = useState({ loaded: false, error: null, stale: false });
    const [filterSource, setFilterSource] = useState(undefined);
    const [filterKeyword, setFilterKeyword] = useState('');
    const fetchItemsRef = useRef(null);
    const requestRef = useRef({ id: 0, controller: null });
    const previousActiveRef = useRef(active);
    const stateRef = useRef({
        pagination: { current: 1, pageSize: initialPageSize },
        filterSource: undefined,
        filterKeyword: '',
    });

    const fetchItems = useCallback(async (
        page = 1,
        pageSize = pagination.pageSize,
        source = filterSource,
        keyword = filterKeyword,
    ) => {
        requestRef.current.controller?.abort();
        const requestId = requestRef.current.id + 1;
        const controller = new AbortController();
        requestRef.current = { id: requestId, controller };
        setLoading(true);
        setLoadState((previous) => ({ ...previous, error: null }));
        try {
            const res = await loadPage({
                page,
                limit: pageSize,
                source: enableSourceFilter ? source : undefined,
                keyword,
                kind: contentKind,
                signal: controller.signal,
            });
            if (requestRef.current.id !== requestId) return;
            const payload = res.data || {};
            const normalized = normalizeResponse(payload, page, pageSize);
            setItems(normalized.items || []);
            setPagination(normalized.pagination || { current: page, pageSize, total: 0 });
            setMeta(normalized.meta ?? initialMeta);
            setLoadState({ loaded: true, error: null, stale: false });
        } catch (error) {
            if (error.code === 'ERR_CANCELED' || requestRef.current.id !== requestId) return;
            console.error(errorMessage, error);
            message.error(errorMessage);
            setLoadState((previous) => ({
                loaded: previous.loaded,
                error: error?.message || errorMessage,
                stale: previous.loaded,
            }));
        } finally {
            if (requestRef.current.id === requestId) setLoading(false);
        }
    }, [contentKind, enableSourceFilter, errorMessage, filterKeyword, filterSource, initialMeta, loadPage, normalizeResponse, pagination.pageSize]);

    fetchItemsRef.current = fetchItems;
    stateRef.current = { pagination, filterSource, filterKeyword };

    useEffect(() => {
        setFilterSource(undefined);
        setFilterKeyword('');
        setItems([]);
        setPagination({ current: 1, pageSize: initialPageSize, total: 0 });
        setMeta(initialMeta);
        setLoadState({ loaded: false, error: null, stale: false });
        previousActiveRef.current = active;
        if (!active) {
            return;
        }
        void fetchItemsRef.current?.(1, initialPageSize, undefined, '');
    }, [active, contentKind, initialMeta, initialPageSize]);

    useEffect(() => () => requestRef.current.controller?.abort(), []);

    useEffect(() => {
        if (!active) return undefined;
        return subscribeResource(API_RESOURCE.CONTENT_LISTS, () => {
            const current = stateRef.current;
            void fetchItemsRef.current?.(
                current.pagination.current,
                current.pagination.pageSize,
                current.filterSource,
                current.filterKeyword,
            );
        });
    }, [active]);

    useEffect(() => {
        const becameActive = active && !previousActiveRef.current;
        previousActiveRef.current = active;
        if (!becameActive) {
            return;
        }
        const current = stateRef.current;
        void fetchItemsRef.current?.(
            current.pagination.current,
            current.pagination.pageSize,
            current.filterSource,
            current.filterKeyword,
        );
    }, [active]);

    const refreshCurrent = useCallback(async () => {
        const current = stateRef.current;
        await fetchItemsRef.current?.(
            current.pagination.current,
            current.pagination.pageSize,
            current.filterSource,
            current.filterKeyword,
        );
    }, []);

    return {
        items,
        loading,
        loaded: loadState.loaded,
        error: loadState.error,
        stale: loadState.stale,
        pagination,
        meta,
        filterSource,
        filterKeyword,
        setFilterSource,
        setFilterKeyword,
        fetchItems,
        refreshCurrent,
        retry: refreshCurrent,
    };
}
