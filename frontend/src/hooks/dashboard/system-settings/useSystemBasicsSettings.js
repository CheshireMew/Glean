import {
    getAutomationConfig,
    getDeliverySchedule,
    getSystemTimezone,
    setSystemSettings,
} from '../../../api/config';
import { useRemoteSettings } from '../../useRemoteSettings';

const EMPTY_SYSTEM_CONFIG = {
    timezone: '',
    news: {},
    article: {},
    delivery: { news_time: '', article_time: '' },
    runtime: {},
};
const WINDOW_FIELDS = [
    'cluster_hours',
    'cluster_window_hours',
    'filter_hours',
    'ai_scoring_hours',
    'push_hours',
];
const RUNTIME_FIELDS = [
    'enabled',
    'start_time',
    'end_time',
    'interval_minutes',
    'review_batch_size',
    'enrichment_batch_size',
    'max_review_batches_per_cycle',
    'backlog_retry_seconds',
    'scraper_concurrency',
    'maintenance_interval_hours',
    'operational_retention_days',
    'content_retention_days',
];
const hasFields = (value, fields) => Boolean(
    value && fields.every((field) => Object.hasOwn(value, field))
);
const identity = (value) => value;

async function loadSystemConfig() {
    const [timezoneResponse, automationResponse, deliveryResponse] = await Promise.all([
        getSystemTimezone(),
        getAutomationConfig(),
        getDeliverySchedule(),
    ]);
    return {
        timezone: timezoneResponse.data?.timezone,
        news: automationResponse.data?.news,
        article: automationResponse.data?.article,
        runtime: automationResponse.data?.runtime,
        delivery: deliveryResponse.data,
    };
}

function isSystemConfig(config) {
    return Boolean(
        config?.timezone
        && hasFields(config.news, WINDOW_FIELDS)
        && hasFields(config.article, WINDOW_FIELDS)
        && hasFields(config.runtime, RUNTIME_FIELDS)
        && hasFields(config.delivery, ['news_time', 'article_time'])
    );
}

function saveSystemConfig(config) {
    return setSystemSettings({
        timezone: config.timezone,
        automation: { news: config.news, article: config.article, runtime: config.runtime },
        delivery: config.delivery,
    });
}

export function useSystemBasicsSettings() {
    const remote = useRemoteSettings({
        initialValue: EMPTY_SYSTEM_CONFIG,
        loadRequest: loadSystemConfig,
        normalizeResponse: identity,
        isValid: isSystemConfig,
        invalidResponseMessage: '服务器返回的系统配置不完整',
        loadErrorMessage: '无法读取当前系统配置',
        saveRequest: saveSystemConfig,
        saveSuccessMessage: '系统配置已更新',
        saveErrorMessage: '保存失败',
        saveBlockedMessage: '尚未读取到服务器当前配置，不能保存',
        scopeId: 'system-basics',
    });

    const setTimezone = (timezone) => {
        remote.setValue((previous) => ({ ...previous, timezone }));
    };
    const setDeliverySchedule = (updater) => {
        remote.setValue((previous) => ({
            ...previous,
            delivery: typeof updater === 'function' ? updater(previous.delivery) : updater,
        }));
    };
    const setRuntimeConfig = (updater) => {
        remote.setValue((previous) => ({
            ...previous,
            runtime: typeof updater === 'function' ? updater(previous.runtime) : updater,
        }));
    };
    const updateHours = (scope, key, value) => {
        remote.setValue((previous) => ({
            ...previous,
            [scope]: { ...previous[scope], [key]: value },
        }));
    };

    return {
        timezone: remote.value.timezone,
        saving: remote.action === 'save',
        loadState: remote.loadState,
        newsConfig: remote.value.news,
        articleConfig: remote.value.article,
        deliverySchedule: remote.value.delivery,
        runtimeConfig: remote.value.runtime,
        dirty: remote.dirty,
        setTimezone,
        setDeliverySchedule,
        setRuntimeConfig,
        updateHours,
        reload: remote.reload,
        reset: remote.reset,
        save: remote.save,
    };
}
