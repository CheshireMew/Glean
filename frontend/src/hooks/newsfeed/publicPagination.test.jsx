import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../api/content', () => ({
    getPublicReports: vi.fn(),
    searchPublicContent: vi.fn(),
}));

import { getPublicReports, searchPublicContent } from '../../api/content';
import { usePublicReportFeed } from './usePublicReportFeed';
import { usePublicSearchResults } from './usePublicSearchResults';

describe('public pagination', () => {
    it('queries and appends daily reports from the server', async () => {
        getPublicReports
            .mockResolvedValueOnce({ data: { items: [{ id: 1 }], total: 2 } })
            .mockResolvedValueOnce({ data: { items: [{ id: 2 }], total: 2 } });
        const { result } = renderHook(() => usePublicReportFeed('news', 'protocol'));
        await act(async () => result.current.ensureLoaded());
        expect(getPublicReports).toHaveBeenNthCalledWith(1, 'news', 20, 0, 'protocol', null);
        expect(result.current.state.hasMore).toBe(true);
        await act(async () => result.current.loadMore());
        expect(getPublicReports).toHaveBeenNthCalledWith(2, 'news', 20, 1, 'protocol', null);
        expect(result.current.state.items).toEqual([{ id: 1 }, { id: 2 }]);
        expect(result.current.state.hasMore).toBe(false);
    });

    it('loads search results in bounded pages for each content kind', async () => {
        searchPublicContent
            .mockResolvedValueOnce({ data: { items: [{ id: 1 }], total: 2 } })
            .mockResolvedValueOnce({ data: { items: [], total: 0 } })
            .mockResolvedValueOnce({ data: { items: [{ id: 2 }], total: 2 } });
        const { result } = renderHook(() => usePublicSearchResults('chain'));
        await waitFor(() => expect(searchPublicContent).toHaveBeenCalledTimes(2));
        await waitFor(() => expect(result.current.state.loading).toBe(false));
        expect(searchPublicContent).toHaveBeenNthCalledWith(1, 'chain', 'article', 20, 0, null);
        await act(async () => result.current.loadMore('article'));
        expect(searchPublicContent).toHaveBeenNthCalledWith(3, 'chain', 'article', 20, 1, null);
        expect(result.current.state.articleItems).toEqual([{ id: 1 }, { id: 2 }]);
    });
});
