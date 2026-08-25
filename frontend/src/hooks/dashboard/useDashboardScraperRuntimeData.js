import { useCallback, useEffect, useRef, useState } from 'react';
import { message } from 'antd';

import { createRssSource, deleteRssSource, getRssSources, updateRssSource } from '../../api/config';
import { cancelScraper, getSpiderStatus, getSpiders, runSpider, updateConfig } from '../../api/pipeline';
import { API_RESOURCE, invalidateResources, subscribeResource } from '../../api/resources';
import { getRequestErrorMessage } from './listStateHelpers';

const RUNTIME_REFRESH_INTERVAL_MS = 3000;

function mergeSpiderStatus(previous, nextStatus) {
    const merged = { ...previous };
    for (const [spider, status] of Object.entries(nextStatus)) {
        const previousSpider = previous[spider] || {};
        merged[spider] = {
            ...previousSpider,
            ...status,
            logs: status.logs && status.logs.length > 0 ? status.logs : previousSpider.logs || [],
        };
    }
    return merged;
}

export function useDashboardScraperRuntimeData(pollingEnabled = false) {
    const [spiders, setSpiders] = useState([]);
    const [spiderStatus, setSpiderStatus] = useState({});
    const [rssSources, setRssSources] = useState([]);
    const [runtimeError, setRuntimeError] = useState(null);
    const statusRequestRef = useRef({ id: 0, controller: null });
    const catalogRequestRef = useRef({ id: 0, controller: null });
    const statusSnapshotRef = useRef({});

    const refreshRuntime = useCallback(async ({ includeCatalog = false } = {}) => {
        statusRequestRef.current.controller?.abort();
        const requestId = statusRequestRef.current.id + 1;
        const statusController = new AbortController();
        statusRequestRef.current = { id: requestId, controller: statusController };
        try {
            const statusResponse = await getSpiderStatus({ signal: statusController.signal });
            if (statusRequestRef.current.id !== requestId) return;
            setRuntimeError(null);
            const previousStatus = statusSnapshotRef.current;
            const nextStatus = mergeSpiderStatus(previousStatus, statusResponse.data || {});
            statusSnapshotRef.current = nextStatus;
            setSpiderStatus(nextStatus);
            const completedRun = Object.entries(nextStatus).some(([name, current]) => (
                ['queued', 'running'].includes(previousStatus[name]?.status)
                && ['idle', 'error'].includes(current.status)
            ));
            if (completedRun) {
                invalidateResources([API_RESOURCE.CONTENT_OVERVIEW, API_RESOURCE.CONTENT_LISTS]);
            }

            if (includeCatalog) {
                catalogRequestRef.current.controller?.abort();
                const catalogId = catalogRequestRef.current.id + 1;
                const catalogController = new AbortController();
                catalogRequestRef.current = { id: catalogId, controller: catalogController };
                const [spidersResponse, rssSourcesResponse] = await Promise.all([
                    getSpiders({ signal: catalogController.signal }),
                    getRssSources({ signal: catalogController.signal }),
                ]);
                if (catalogRequestRef.current.id !== catalogId) return;
                setSpiders(spidersResponse.data.spiders || []);
                setRssSources(rssSourcesResponse.data.sources || []);
            }
        } catch (error) {
            if (error.code === 'ERR_CANCELED') return;
            if (statusRequestRef.current.id !== requestId) return;
            console.error('Failed to fetch scraper runtime:', error);
            setRuntimeError(getRequestErrorMessage(error, '爬虫运行状态加载失败'));
        }
    }, []);

    useEffect(() => subscribeResource(
        API_RESOURCE.SCRAPER_RUNTIME,
        () => void refreshRuntime({ includeCatalog: true }),
    ), [refreshRuntime]);

    useEffect(() => {
        const timer = setTimeout(() => {
            void refreshRuntime({ includeCatalog: true });
        }, 0);
        return () => {
            clearTimeout(timer);
            statusRequestRef.current.controller?.abort();
            catalogRequestRef.current.controller?.abort();
        };
    }, [refreshRuntime]);

    useEffect(() => {
        if (!pollingEnabled) return undefined;
        let cancelled = false;
        let timer;
        const poll = async () => {
            await refreshRuntime();
            if (!cancelled) timer = setTimeout(poll, RUNTIME_REFRESH_INTERVAL_MS);
        };
        timer = setTimeout(poll, RUNTIME_REFRESH_INTERVAL_MS);
        return () => {
            cancelled = true;
            clearTimeout(timer);
            statusRequestRef.current.controller?.abort();
        };
    }, [pollingEnabled, refreshRuntime]);

    const handleRunSpider = useCallback(async (name, items) => {
        try {
            await runSpider(name, items);
            message.success(`已触发爬虫：${name}（最多 ${items} 条）`);
        } catch (error) {
            console.error('Run scraper failed:', error);
            message.error(`触发失败: ${getRequestErrorMessage(error, name)}`);
        }
    }, []);

    const handleStopSpider = useCallback(async (name) => {
        try {
            await cancelScraper(name);
            message.warning(`已请求停止爬虫: ${name}`);
        } catch (error) {
            message.error(`停止失败: ${getRequestErrorMessage(error, name)}`);
        }
    }, []);

    const handleConfigChange = useCallback(async (name, changes) => {
        try {
            await updateConfig(name, changes);
            message.success(`已更新配置: ${name}`);
            await refreshRuntime();
            return true;
        } catch (error) {
            message.error(`更新配置失败: ${getRequestErrorMessage(error, '更新配置失败')}`);
            await refreshRuntime();
            return false;
        }
    }, [refreshRuntime]);

    const handleCreateRssSource = useCallback(async (payload) => {
        try {
            await createRssSource(payload);
            message.success('RSS 源已创建');
        } catch (error) {
            message.error(`创建失败: ${getRequestErrorMessage(error, '创建 RSS 源失败')}`);
            throw error;
        }
    }, []);

    const handleUpdateRssSource = useCallback(async (id, payload) => {
        try {
            await updateRssSource(id, payload);
            message.success('RSS 源已更新');
        } catch (error) {
            message.error(`更新失败: ${getRequestErrorMessage(error, '更新 RSS 源失败')}`);
            throw error;
        }
    }, []);

    const handleDeleteRssSource = useCallback(async (id) => {
        try {
            await deleteRssSource(id);
            message.success('RSS 源已删除');
        } catch (error) {
            message.error(`删除失败: ${getRequestErrorMessage(error, '删除 RSS 源失败')}`);
            throw error;
        }
    }, []);

    return {
        spiders,
        spiderStatus,
        rssSources,
        runtimeError,
        refreshRuntime,
        actions: {
            handleRunSpider,
            handleStopSpider,
            handleConfigChange,
            handleCreateRssSource,
            handleUpdateRssSource,
            handleDeleteRssSource,
        },
    };
}
