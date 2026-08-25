import { useCallback, useEffect, useMemo, useState } from 'react';

import { searchPublicContent } from '../../api/content';
import { CONTENT_KIND } from '../../contracts/content';

const PAGE_LIMIT = 20;

function createKindState() {
    return { items: [], total: 0, offset: 0, hasMore: false, loadingMore: false };
}

function createSearchState() {
    return {
        loading: false,
        article: createKindState(),
        brief: createKindState(),
        error: null,
    };
}

export function usePublicSearchResults(query, publications = {}) {
    const [retryNonce, setRetryNonce] = useState(0);
    const [state, setState] = useState(createSearchState);
    const normalizedQuery = query.trim();
    const enabled = normalizedQuery.length >= 1;

    useEffect(() => {
        if (!enabled) {
            return;
        }

        let cancelled = false;

        const timer = setTimeout(() => {
            const load = async () => {
                setState((previous) => ({ ...previous, loading: true, error: null }));
                try {
                    const [articleResponse, briefResponse] = await Promise.all([
                        searchPublicContent(normalizedQuery, CONTENT_KIND.ARTICLE, PAGE_LIMIT, 0, publications.article || null),
                        searchPublicContent(normalizedQuery, CONTENT_KIND.NEWS, PAGE_LIMIT, 0, publications.news || null),
                    ]);
                    if (cancelled) {
                        return;
                    }
                    const articlePayload = articleResponse.data || {};
                    const briefPayload = briefResponse.data || {};
                    setState({
                        loading: false,
                        article: {
                            items: articlePayload.items || [],
                            total: articlePayload.total || 0,
                            offset: (articlePayload.items || []).length,
                            hasMore: (articlePayload.items || []).length < (articlePayload.total || 0),
                            loadingMore: false,
                        },
                        brief: {
                            items: briefPayload.items || [],
                            total: briefPayload.total || 0,
                            offset: (briefPayload.items || []).length,
                            hasMore: (briefPayload.items || []).length < (briefPayload.total || 0),
                            loadingMore: false,
                        },
                        error: null,
                    });
                } catch (error) {
                    if (cancelled) {
                        return;
                    }
                    console.error('Failed to search public content:', error);
                    setState((previous) => ({ ...previous, loading: false, error: error?.message || '搜索失败' }));
                }
            };

            void load();
        }, 0);

        return () => {
            cancelled = true;
            clearTimeout(timer);
        };
    }, [enabled, normalizedQuery, publications.article, publications.news, retryNonce]);

    const retry = useCallback(() => setRetryNonce((value) => value + 1), []);

    const loadMore = useCallback(async (kind) => {
        const stateKey = kind === CONTENT_KIND.ARTICLE ? 'article' : 'brief';
        const current = state[stateKey];
        if (!enabled || !current.hasMore || current.loadingMore) return;
        setState((previous) => ({
            ...previous,
            [stateKey]: { ...previous[stateKey], loadingMore: true },
        }));
        try {
            const response = await searchPublicContent(
                normalizedQuery,
                kind,
                PAGE_LIMIT,
                current.offset,
                publications[kind] || null,
            );
            const payload = response.data || {};
            const nextItems = payload.items || [];
            setState((previous) => {
                const ids = new Set(previous[stateKey].items.map((item) => item.id));
                const items = [...previous[stateKey].items, ...nextItems.filter((item) => !ids.has(item.id))];
                const total = payload.total || 0;
                return {
                    ...previous,
                    [stateKey]: {
                        items,
                        total,
                        offset: current.offset + nextItems.length,
                        hasMore: current.offset + nextItems.length < total,
                        loadingMore: false,
                    },
                    error: null,
                };
            });
        } catch (error) {
            setState((previous) => ({
                ...previous,
                [stateKey]: { ...previous[stateKey], loadingMore: false },
                error: error?.message || '搜索加载更多失败',
            }));
        }
    }, [enabled, normalizedQuery, publications, state]);

    const publicState = useMemo(() => ({
            ...state,
            articleItems: state.article.items,
            briefItems: state.brief.items,
    }), [state]);

    return useMemo(() => ({
        state: publicState,
        enabled,
        retry,
        loadMore,
    }), [enabled, loadMore, publicState, retry]);
}
