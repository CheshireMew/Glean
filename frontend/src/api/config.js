import { requestOperation } from './operations';
import { CONTENT_KIND } from '../contracts/content';

export const getSystemTimezone = () => requestOperation('getSystemTimezone');
export const setSystemSettings = (data) => requestOperation('setSystemSettings', { data });

export const getDeliverySchedule = () => requestOperation('getDeliverySchedule');
export const setDeliverySchedule = (data) => requestOperation('setDeliverySchedule', { data });

export const getAutomationConfig = () => requestOperation('getAutomationConfig');

export const getAiProviderConfig = () => requestOperation('getAiProviderConfig');
export const setAiProviderConfig = (data) => requestOperation('setAiProviderConfig', { data });
export const getEditorialProfiles = (kind = null) => requestOperation('getEditorialProfiles', { params: { kind } });
export const saveEditorialProfile = (profile) => requestOperation('saveEditorialProfile', { path: { slug: profile.slug }, data: profile });

export const getReviewSettings = (kind = CONTENT_KIND.NEWS) => requestOperation('getReviewSettings', { params: { kind } });
export const setReviewSettings = (data, kind = CONTENT_KIND.NEWS) => requestOperation('setReviewSettings', { data, params: { kind } });

export const getBlocklist = (kind = CONTENT_KIND.NEWS) => requestOperation('getBlocklist', { params: { kind } });
export const addBlocklist = (keyword, matchType = 'contains', kind = CONTENT_KIND.NEWS) => requestOperation('addBlocklist', { data: { keyword, match_type: matchType, kind } });
export const deleteBlocklist = (id) => requestOperation('deleteBlocklist', { path: { id } });

export const getTelegramConfig = () => requestOperation('getTelegramConfig');
export const setTelegramConfig = (data) => requestOperation('setTelegramConfig', { data });

export const getRssSources = (config = {}) => requestOperation('getRssSources', config);
export const previewRssSource = (data) => requestOperation('previewRssSource', { data, timeout: 45000 });
export const createRssSource = (data) => requestOperation('createRssSource', { data });
export const updateRssSource = (id, data) => requestOperation('updateRssSource', { path: { id }, data });
export const deleteRssSource = (id) => requestOperation('deleteRssSource', { path: { id } });
