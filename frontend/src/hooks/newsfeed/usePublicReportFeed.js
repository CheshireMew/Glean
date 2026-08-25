import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { getPublicReports } from '../../api/content';

const PAGE_LIMIT = 20;

function createReportState() {
    return {
        items: [],
        total: 0,
        offset: 0,
        hasMore: true,
        loading: false,
        loadingMore: false,
        loaded: false,
        error: null,
    };
}

function mergeUniqueById(previous, next) {
    const ids = new Set(previous.map((item) => item.id));
    return [...previous, ...next.filter((item) => !ids.has(item.id))];
}

export function usePublicReportFeed(kind, query = '', publication = null) {
    const [state, setState] = useState(createReportState);
    const requestRef = useRef(0);
    const stateRef = useRef(state);

    useEffect(() => {
        stateRef.current = state;
    }, [state]);

    useEffect(() => {
        requestRef.current += 1;
        const next = createReportState();
        stateRef.current = next;
        setState(next);
    }, [kind, publication, query]);

    const fetchPage = useCallback(async ({ append = false, limit = PAGE_LIMIT } = {}) => {
        const current = stateRef.current;
        const requestId = requestRef.current + 1;
        requestRef.current = requestId;
        setState((previous) => ({
            ...previous,
            loading: append ? previous.loading : true,
            loadingMore: append,
            error: null,
        }));

        try {
            const offset = append ? current.items.length : 0;
            const response = await getPublicReports(kind, limit, offset, query.trim(), publication);
            if (requestRef.current !== requestId) {
                return;
            }
            const items = response.data?.items || [];
            const total = response.data?.total || 0;
            setState((previous) => ({
                items: append ? mergeUniqueById(previous.items, items) : items,
                total,
                offset: offset + items.length,
                hasMore: offset + items.length < total,
                loading: false,
                loadingMore: false,
                loaded: true,
                error: null,
            }));
        } catch (error) {
            console.error(`Failed to fetch reports for ${kind}:`, error);
            if (requestRef.current === requestId) {
                setState((previous) => ({
                    ...previous,
                    loading: false,
                    loadingMore: false,
                    error: error?.message || '日报加载失败',
                }));
            }
        }
    }, [kind, publication, query]);

    const ensureLoaded = useCallback(async () => {
        const current = stateRef.current;
        if (current.loaded || current.loading) return;
        await fetchPage();
    }, [fetchPage]);

    const refresh = useCallback(() => fetchPage({
        limit: Math.min(100, Math.max(PAGE_LIMIT, stateRef.current.items.length)),
    }), [fetchPage]);

    const loadMore = useCallback(async () => {
        const current = stateRef.current;
        if (!current.loaded || !current.hasMore || current.loadingMore) return;
        await fetchPage({ append: true });
    }, [fetchPage]);

    return useMemo(() => ({
        state,
        ensureLoaded,
        retry: refresh,
        refresh,
        loadMore,
    }), [ensureLoaded, loadMore, refresh, state]);
}
