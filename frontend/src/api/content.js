import { requestOperation } from './operations';
import { CONTENT_KIND } from '../contracts/content';

export const getContentOverview = (kind = CONTENT_KIND.NEWS) => requestOperation('getContentOverview', { params: { kind } });
export const getContentStats = (kind = CONTENT_KIND.NEWS) => requestOperation('getContentStats', { params: { kind } });

export const listIncomingContent = ({ page = 1, limit = 50, source = null, keyword = null, kind = CONTENT_KIND.NEWS, signal } = {}) =>
    requestOperation('listIncomingContent', { params: { page, limit, source, keyword, kind }, signal });
export const deleteSourceContent = (id) => requestOperation('deleteSourceContent', { path: { id } });

export const listContentEvents = ({ page = 1, limit = 20, source = null, keyword = null, kind = CONTENT_KIND.NEWS, signal } = {}) =>
    requestOperation('listContentEvents', { params: { page, limit, source, keyword, kind }, signal });

export const listArchiveContent = ({ page = 1, limit = 50, source = null, keyword = null, kind = CONTENT_KIND.NEWS, signal } = {}) =>
    requestOperation('listArchiveContent', { params: { page, limit, source, keyword, kind }, signal });
export const deleteArchiveContent = (id) => requestOperation('deleteArchiveContent', { path: { id } });

export const listBlockedContent = ({ page = 1, limit = 50, keyword = null, kind = CONTENT_KIND.NEWS, signal } = {}) =>
    requestOperation('listBlockedContent', { params: { page, limit, keyword, kind }, signal });

export const listReviewQueue = ({ page = 1, limit = 50, source = null, keyword = null, kind = CONTENT_KIND.NEWS, signal } = {}) =>
    requestOperation('listReviewQueue', { params: { page, limit, source, keyword, kind }, signal });

export const listReviewedContent = ({ decision, page = 1, limit = 50, source = null, keyword = null, kind = CONTENT_KIND.NEWS, signal } = {}) =>
    requestOperation('listReviewedContent', { params: { decision, page, limit, source, keyword, kind }, signal });

export const deleteReviewEntry = (id) => requestOperation('deleteReviewEntry', { path: { id } });
export const restoreArchiveEntry = (id) => requestOperation('restoreArchiveEntry', { path: { id } });
export const restoreBlockedEntry = (id) => requestOperation('restoreBlockedEntry', { path: { id } });

export const exportContent = (params) => requestOperation('exportContent', { params, responseType: 'blob' });

export const getPublicContent = (stream, limit = 20, cursor = null, knownRevision = null, publication = null) =>
    requestOperation('getPublicContent', { params: { stream, limit, cursor, known_revision: knownRevision, publication } });

export const getPublicSiteConfig = () => requestOperation('getPublicSiteConfig');

export const getPublicReports = (kind = null, limit = 20, offset = 0, query = '', publication = null) =>
    requestOperation('getPublicReports', { params: { kind, limit, offset, query: query || undefined, publication } });

export const searchPublicContent = (query, kind = 'all', limit = 20, offset = 0, publication = null) =>
    requestOperation('searchPublicContent', { params: { query, kind, limit, offset, publication } });
