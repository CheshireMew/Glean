import { describe, expect, it } from 'vitest';

import client from './client';

describe('API envelope client contract', () => {
    it('unwraps paginated envelopes into the list shape consumed by hooks', async () => {
        const response = await client.get('/contract-test', {
            adapter: async (config) => ({
                config,
                data: {
                    success: true,
                    data: [{ id: 1 }],
                    pagination: { total: 3, page: 1, limit: 1, pages: 3 },
                    message: '查询成功',
                    code: 200,
                    timestamp: '2026-08-23T00:00:00Z',
                },
                headers: {},
                status: 200,
                statusText: 'OK',
            }),
        });
        expect(response.data).toEqual({ data: [{ id: 1 }], total: 3, page: 1, limit: 1, pages: 3 });
    });
});
