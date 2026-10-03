import { requestOperation } from './operations';

export const getWechatStatus = (config) => requestOperation('getWechatStatus', config);
export const startWechatLogin = () => requestOperation('startWechatLogin');
export const cancelWechatLogin = () => requestOperation('cancelWechatLogin', { timeout: 45000 });
export const disconnectWechat = () => requestOperation('disconnectWechat', { timeout: 45000 });
export const searchWechatAccounts = (query, begin = 0) => requestOperation('searchWechatAccounts', { params: { query, begin }, timeout: 50000 });
export const getWechatSources = (config) => requestOperation('getWechatSources', config);
export const addWechatSource = (data) => requestOperation('addWechatSource', { data });
export const updateWechatSource = (sourceId, data) => requestOperation('updateWechatSource', { path: { source_id: sourceId }, data });
