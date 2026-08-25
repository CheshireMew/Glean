import { requestOperation } from './operations';
import { CONTENT_KIND } from '../contracts/content';

const PIPELINE_TIMEOUT = { timeout: 5 * 60 * 1000 };

export const getSpiders = (config = {}) => requestOperation('getSpiders', config);
export const getSpiderStatus = (config = {}) => requestOperation('getSpiderStatus', config);
export const runSpider = (name, items = 10) => requestOperation('runSpider', { path: { name }, data: { items } });
export const cancelScraper = (name) => requestOperation('cancelScraper', { path: { name } });
export const updateConfig = (name, { interval, limit }) => requestOperation('updateConfig', { path: { name }, data: { interval, limit } });

export const checkContentSimilarity = (newsId1, newsId2) =>
    requestOperation('checkContentSimilarity', { data: { news_id_1: newsId1, news_id_2: newsId2 } });

export const runReview = (data) => requestOperation('runReview', { data, ...PIPELINE_TIMEOUT });
export const applyBlocklist = (timeRangeHours, kind = CONTENT_KIND.NEWS) => requestOperation('applyBlocklist', { data: { time_range_hours: timeRangeHours, kind }, ...PIPELINE_TIMEOUT });
export const restoreBlockedContent = (kind = CONTENT_KIND.NEWS) => requestOperation('restoreBlockedContent', { params: { kind } });
export const requeueReviewEntry = (id) => requestOperation('requeueReviewEntry', { path: { id } });
export const requeueReviewedContent = (kind = CONTENT_KIND.NEWS) => requestOperation('requeueReviewedContent', { params: { kind } });
export const clearReviewDecisions = (kind = CONTENT_KIND.NEWS) => requestOperation('clearReviewDecisions', { params: { kind } });

export const testTelegramPush = (config) => requestOperation('testTelegramPush', { data: config });
export const sendSelectedContent = (entries, operationKey) => requestOperation('sendSelectedContent', { data: { entries, operation_key: operationKey }, ...PIPELINE_TIMEOUT });
export const triggerDailyPush = (kind = CONTENT_KIND.NEWS, operationKey) => requestOperation(
    kind === CONTENT_KIND.ARTICLE ? 'triggerDailyArticle' : 'triggerDailyNews',
    { data: { operation_key: operationKey }, ...PIPELINE_TIMEOUT },
);
export const retryDelivery = (operationKey) => requestOperation('retryDelivery', { data: { operation_key: operationKey }, ...PIPELINE_TIMEOUT });
export const listDeliveryOperations = (status) => requestOperation('listDeliveryOperations', { params: { limit: 50, status } });

export const getAnalystApiKeys = () => requestOperation('getAnalystApiKeys');
export const createAnalystApiKey = (keyName, notes) => requestOperation('createAnalystApiKey', { data: { key_name: keyName, notes } });
export const deleteAnalystApiKey = (keyId) => requestOperation('deleteAnalystApiKey', { path: { keyId } });
export const setAnalystApiKeyEnabled = (keyId, enabled) => requestOperation('setAnalystApiKeyEnabled', { path: { keyId }, data: { enabled } });
export const testAiConnection = (config) => requestOperation('testAiConnection', { data: config, timeout: 90 * 1000 });
