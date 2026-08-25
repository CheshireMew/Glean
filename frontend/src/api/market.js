import { requestOperation } from './operations';

export const listMarketInstruments = () => requestOperation('listMarketInstruments');
export const createMarketInstrument = (data) => requestOperation('createMarketInstrument', { data });
export const updateMarketInstrument = (instrumentId, data) => requestOperation('updateMarketInstrument', { path: { instrumentId }, data });
export const getEventMarket = (eventId) => requestOperation('getEventMarket', { path: { eventId } });
export const refreshEventMarket = (eventId) => requestOperation('refreshEventMarket', { path: { eventId } });
export const saveMarketSnapshot = (eventId, instrumentId, data) => requestOperation('saveMarketSnapshot', { path: { eventId, instrumentId }, data });
export const saveMarketExpectation = (eventId, instrumentId, data) => requestOperation('saveMarketExpectation', { path: { eventId, instrumentId }, data });
