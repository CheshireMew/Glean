import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { getPublicContent } from '../../api/content';

const PAGE_LIMIT = 20;
const MAX_PAGES = 50;

function createStreamState() {
    return {
        items: [],
        page: 0,
        nextCursor: null,
        hasMore: true,
        loading: false,
        loadingMore: false,
        loaded: false,
        error: null,
        refreshError: null,
        revision: null,
    };
}

function mergeUniqueById(previous, next) {
    const existingIds = new Set(previous.map((item) => item.id));
    return [...previous, ...next.filter((item) => !existingIds.has(item.id))];
}

export function usePublicStream(stream, publication = null) {
    const [state, setState] = useState(createStreamState);
    const requestRef = useRef(0);
    const generationRef = useRef(0);
    const pageRequestRef = useRef(null);
    const refreshRequestRef = useRef(null);
    const stateRef = useRef(state);

    const updateState = useCallback((update) => {
        const next = update(stateRef.current);
        stateRef.current = next;
        setState(next);
    }, []);

    useEffect(() => {
        requestRef.current += 1;
        generationRef.current += 1;
        pageRequestRef.current = null;
        refreshRequestRef.current = null;
        const next = createStreamState();
        stateRef.current = next;
        setState(next);
        return () => {
            requestRef.current += 1;
            generationRef.current += 1;
            pageRequestRef.current = null;
            refreshRequestRef.current = null;
        };
    }, [stream, publication]);

    const fetchPage = useCallback((nextPage, { append = false, silent = false } = {}) => {
        if (pageRequestRef.current) return pageRequestRef.current.promise;
        const request = {};
        pageRequestRef.current = request;
        request.promise = (async () => {
            const requestId = requestRef.current + 1;
            requestRef.current = requestId;

            if (!silent) {
                updateState((previous) => ({
                    ...previous,
                    loading: append ? previous.loading : true,
                    loadingMore: append,
                    error: null,
                    refreshError: null,
                }));
            }

            try {
                const response = await getPublicContent(stream, PAGE_LIMIT, append ? stateRef.current.nextCursor : null, null, publication);
                if (requestRef.current !== requestId) {
                    return;
                }
                const nextItems = response.data?.items || [];
                updateState((previous) => ({
                    ...previous,
                    items: append ? mergeUniqueById(previous.items, nextItems) : nextItems,
                    page: nextPage,
                    nextCursor: response.data?.next_cursor || null,
                    hasMore: Boolean(response.data?.next_cursor) && nextPage < MAX_PAGES,
                    loading: false,
                    loadingMore: false,
                    loaded: true,
                    error: null,
                    refreshError: null,
                    // Appending a newer page cannot certify the earlier pages.
                    // A mixed snapshot must be refreshed without known_revision.
                    revision: append
                        ? (previous.revision && response.data?.revision === previous.revision ? previous.revision : null)
                        : (response.data?.revision || previous.revision),
                }));
            } catch (error) {
                console.error(`Failed to fetch ${stream}:`, error);
                if (requestRef.current === requestId) {
                    updateState((previous) => ({
                        ...previous,
                        loading: false,
                        loadingMore: false,
                        error: error?.message || '公开内容加载失败',
                    }));
                }
            } finally {
                if (pageRequestRef.current === request) pageRequestRef.current = null;
            }
        })();
        return request.promise;
    }, [publication, stream, updateState]);

    const ensureLoaded = useCallback(async () => {
        const current = stateRef.current;
        if (current.loaded || current.loading) {
            return;
        }
        await fetchPage(1);
    }, [fetchPage]);

    const refresh = useCallback(() => {
        if (refreshRequestRef.current) return refreshRequestRef.current.promise;
        const generation = generationRef.current;
        const request = {};
        refreshRequestRef.current = request;
        request.promise = (async () => {
            try {
                // A refresh must include the page the user has already requested, and its cursor.
                // Serializing snapshot mutations also makes not_modified meaningful at that depth.
                if (pageRequestRef.current) await pageRequestRef.current.promise;
                if (generationRef.current !== generation) return;
                const current = stateRef.current;
                if (!current.loaded) {
                    await fetchPage(1, { silent: true });
                    return;
                }
                const requestId = requestRef.current + 1;
                requestRef.current = requestId;
                const targetSize = Math.max(PAGE_LIMIT, current.items.length);
                try {
                    const response = await getPublicContent(
                        stream,
                        Math.min(MAX_PAGES * PAGE_LIMIT, targetSize),
                        null,
                        current.revision,
                        publication,
                    );
                    if (requestRef.current !== requestId) {
                        return;
                    }
                    if (response.data?.not_modified) {
                        updateState((previous) => ({ ...previous, refreshError: null }));
                        return;
                    }
                    const snapshot = response.data?.items || [];
                    const nextCursor = response.data?.next_cursor || null;
                    const page = Math.max(1, Math.ceil(snapshot.length / PAGE_LIMIT));
                    updateState((previous) => ({
                        ...previous,
                        items: snapshot,
                        page,
                        nextCursor,
                        hasMore: Boolean(nextCursor) && page < MAX_PAGES,
                        refreshError: null,
                        revision: response.data?.revision || previous.revision,
                    }));
                } catch (error) {
                    console.error(`Failed to refresh ${stream}:`, error);
                    if (requestRef.current === requestId) {
                        updateState((previous) => ({
                            ...previous,
                            refreshError: error?.message || '自动刷新失败',
                        }));
                    }
                }
            } finally {
                if (refreshRequestRef.current === request) refreshRequestRef.current = null;
            }
        })();
        return request.promise;
    }, [fetchPage, publication, stream, updateState]);

    const retry = useCallback(async () => {
        const generation = generationRef.current;
        if (refreshRequestRef.current) await refreshRequestRef.current.promise;
        if (pageRequestRef.current) await pageRequestRef.current.promise;
        if (generationRef.current !== generation) return;
        await fetchPage(1);
    }, [fetchPage]);

    const loadMore = useCallback(async () => {
        const generation = generationRef.current;
        if (pageRequestRef.current) return pageRequestRef.current.promise;
        if (refreshRequestRef.current) await refreshRequestRef.current.promise;
        if (generationRef.current !== generation) return;
        const current = stateRef.current;
        if (!current.loaded || !current.hasMore || current.loadingMore || current.page >= MAX_PAGES) {
            return;
        }
        await fetchPage(current.page + 1, { append: true });
    }, [fetchPage]);

    return useMemo(() => ({
        state,
        ensureLoaded,
        refresh,
        loadMore,
        retry,
    }), [ensureLoaded, loadMore, refresh, retry, state]);
}
