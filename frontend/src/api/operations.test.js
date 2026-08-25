import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./client', () => ({
    default: { request: vi.fn() },
}));

import client from './client';
import { requestOperation } from './operations';
import { API_RESOURCE, subscribeResource } from './resources';

describe('API operation resource invalidation', () => {
    beforeEach(() => {
        client.request.mockReset();
        client.request.mockResolvedValue({ data: {} });
    });

    it('invalidates declared content resources after a successful mutation', async () => {
        const overview = vi.fn();
        const lists = vi.fn();
        const stopOverview = subscribeResource(API_RESOURCE.CONTENT_OVERVIEW, overview);
        const stopLists = subscribeResource(API_RESOURCE.CONTENT_LISTS, lists);

        await requestOperation('deleteSourceContent', { path: { id: 42 } });

        expect(client.request).toHaveBeenCalledWith(expect.objectContaining({
            method: 'delete',
            url: '/content/source/42',
        }));
        expect(overview).toHaveBeenCalledOnce();
        expect(lists).toHaveBeenCalledOnce();
        stopOverview();
        stopLists();
    });

    it('does not infer invalidation from a mutating HTTP method', async () => {
        const listener = vi.fn();
        const stop = subscribeResource(API_RESOURCE.CONTENT_LISTS, listener);
        await requestOperation('checkContentSimilarity', { data: { news_id_1: 1, news_id_2: 2 } });
        expect(listener).not.toHaveBeenCalled();
        stop();
    });
});
