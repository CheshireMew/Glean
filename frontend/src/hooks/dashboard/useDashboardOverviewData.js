import { useCallback, useEffect, useRef, useState } from 'react';

import { getContentOverview, getContentStats } from '../../api/content';
import { API_RESOURCE, subscribeResource } from '../../api/resources';
import { DEFAULT_DASHBOARD_OVERVIEW } from '../../contracts/content';
import { getRequestErrorMessage } from './listStateHelpers';


export function useDashboardOverviewData(contentKind) {
    const [stats, setStats] = useState([]);
    const [overview, setOverview] = useState(null);
    const [loadState, setLoadState] = useState({ loading: true, loaded: false, error: null });
    const requestRef = useRef(0);

    const refreshOverview = useCallback(async ({ includeStats = false } = {}) => {
        const requestId = requestRef.current + 1;
        requestRef.current = requestId;
        setLoadState((previous) => ({ ...previous, loading: true, error: null }));
        try {
            if (includeStats) {
                const [statsRes, overviewRes] = await Promise.all([
                    getContentStats(contentKind),
                    getContentOverview(contentKind),
                ]);
                if (requestRef.current !== requestId) {
                    return;
                }
                if (!Array.isArray(statsRes.data?.stats) || !overviewRes.data || typeof overviewRes.data !== 'object'
                    || !Object.keys(DEFAULT_DASHBOARD_OVERVIEW).every((key) => Object.hasOwn(overviewRes.data, key))) {
                    throw new Error('服务器返回的仪表盘统计不完整');
                }
                setStats(statsRes.data.stats);
                setOverview({ ...DEFAULT_DASHBOARD_OVERVIEW, ...overviewRes.data });
                setLoadState({ loading: false, loaded: true, error: null });
                return true;
            }

            const overviewRes = await getContentOverview(contentKind);
            if (requestRef.current !== requestId) {
                return;
            }
            if (!overviewRes.data || typeof overviewRes.data !== 'object'
                || !Object.keys(DEFAULT_DASHBOARD_OVERVIEW).every((key) => Object.hasOwn(overviewRes.data, key))) {
                throw new Error('服务器返回的仪表盘统计不完整');
            }
            setOverview({ ...DEFAULT_DASHBOARD_OVERVIEW, ...overviewRes.data });
            setLoadState({ loading: false, loaded: true, error: null });
            return true;
        } catch (error) {
            if (requestRef.current !== requestId) {
                return false;
            }
            setLoadState((previous) => ({
                loading: false,
                loaded: previous.loaded,
                error: getRequestErrorMessage(error, '无法读取仪表盘统计'),
            }));
            return false;
        }
    }, [contentKind]);

    useEffect(() => {
        const timer = setTimeout(() => {
            void refreshOverview({ includeStats: true });
        }, 0);
        return () => clearTimeout(timer);
    }, [refreshOverview]);

    useEffect(() => {
        return subscribeResource(
            API_RESOURCE.CONTENT_OVERVIEW,
            () => void refreshOverview({ includeStats: true }),
        );
    }, [refreshOverview]);

    return {
        stats,
        overview,
        loadState,
        refreshOverview,
    };
}
