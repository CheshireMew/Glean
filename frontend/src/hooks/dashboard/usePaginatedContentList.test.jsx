import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('antd', () => ({ message: { error: vi.fn() } }));

import { usePaginatedContentList } from './usePaginatedContentList';

describe('usePaginatedContentList load truth', () => {
    it('distinguishes an initial failure from a stale refresh failure', async () => {
        const loadPage = vi.fn().mockRejectedValueOnce(new Error('initial unavailable'));
        const { result } = renderHook(() => usePaginatedContentList({
            contentKind: 'news',
            loadPage,
        }));

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.loaded).toBe(false);
        expect(result.current.stale).toBe(false);
        expect(result.current.error).toBe('initial unavailable');
        expect(result.current.items).toEqual([]);

        loadPage.mockResolvedValueOnce({
            data: { data: [{ id: 1, title: 'kept' }], total: 1, page: 1, limit: 10 },
        });
        await act(async () => result.current.retry());
        expect(result.current.loaded).toBe(true);
        expect(result.current.items).toEqual([{ id: 1, title: 'kept' }]);

        loadPage.mockRejectedValueOnce(new Error('refresh unavailable'));
        await act(async () => result.current.refreshCurrent());
        expect(result.current.loaded).toBe(true);
        expect(result.current.stale).toBe(true);
        expect(result.current.error).toBe('refresh unavailable');
        expect(result.current.items).toEqual([{ id: 1, title: 'kept' }]);
    });
});
