import { requestOperation } from './operations';

export const listSourceCatalog = () => requestOperation('listSourceCatalog');
export const syncSourceCatalog = () => requestOperation('syncSourceCatalog');
export const updateSourceCatalog = (sourceKey, data) => requestOperation('updateSourceCatalog', { path: { sourceKey }, data });
export const snapshotSourceHealth = (params = {}) => requestOperation('snapshotSourceHealth', { params });
export const listSourceHealth = (params = {}) => requestOperation('listSourceHealth', { params });
export const listSourceIncidents = (params = {}) => requestOperation('listSourceIncidents', { params });
export const updateSourceIncident = (incidentId, data) => requestOperation('updateSourceIncident', { path: { incidentId }, data });
