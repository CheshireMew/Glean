import { requestOperation } from './operations';

export const getPublicAIContent = ({ source, query, limit = 20, offset = 0, signal } = {}) =>
    requestOperation('getPublicAIContent', { params: { source: source || undefined, query, limit, offset }, signal });

export const refreshPublicAIContent = ({ signal } = {}) => requestOperation('refreshPublicAIContent', { signal });
