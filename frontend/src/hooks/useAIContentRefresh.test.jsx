import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { refreshPublicAIContent } from '../api/aiContent';
import { useAIContentRefresh } from './useAIContentRefresh';

vi.mock('../api/aiContent', () => ({ refreshPublicAIContent: vi.fn() }));
let visibility;
beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(refreshPublicAIContent).mockReset();
    visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
});
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe('AI source automatic refresh', () => {
    it('checks on open, polls active work, slows down after completion, and stops on unmount', async () => {
        const onUpdated = vi.fn();
        refreshPublicAIContent.mockResolvedValueOnce({ data: { updating: true, sources: [] } })
            .mockResolvedValue({ data: { updating: false, sources: [] } });
        const { result, unmount } = renderHook(() => useAIContentRefresh(onUpdated));
        await act(async () => {});
        expect(refreshPublicAIContent).toHaveBeenCalledTimes(1);
        expect(result.current.update.updating).toBe(true);
        await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
        expect(refreshPublicAIContent).toHaveBeenCalledTimes(2);
        expect(result.current.update.updating).toBe(false);
        await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
        expect(refreshPublicAIContent).toHaveBeenCalledTimes(3);
        expect(onUpdated).toHaveBeenCalledTimes(3);
        unmount();
        await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
        expect(refreshPublicAIContent).toHaveBeenCalledTimes(3);
    });
    it('pauses hidden pages and checks on return and on manual refresh', async () => {
        visibility.mockReturnValue('hidden');
        refreshPublicAIContent.mockResolvedValue({ data: { updating: false, sources: [] } });
        const onUpdated = vi.fn();
        const { result, unmount } = renderHook(() => useAIContentRefresh(onUpdated));
        await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
        expect(refreshPublicAIContent).not.toHaveBeenCalled();
        visibility.mockReturnValue('visible');
        await act(async () => { document.dispatchEvent(new Event('visibilitychange')); });
        expect(refreshPublicAIContent).toHaveBeenCalledTimes(1);
        await act(async () => { result.current.refreshNow(); });
        expect(refreshPublicAIContent).toHaveBeenCalledTimes(2);
        unmount();
    });
    it('keeps one request in flight and recovers after network failure', async () => {
        let reject;
        refreshPublicAIContent.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; }))
            .mockResolvedValue({ data: { updating: false, sources: [] } });
        const onUpdated = vi.fn();
        const { result, unmount } = renderHook(() => useAIContentRefresh(onUpdated));
        await act(async () => {
            document.dispatchEvent(new Event('visibilitychange'));
            window.dispatchEvent(new Event('online'));
            await vi.advanceTimersByTimeAsync(30000);
        });
        expect(refreshPublicAIContent).toHaveBeenCalledTimes(1);
        await act(async () => { reject(new Error('暂时断网')); });
        expect(result.current.update.message).toBe('暂时断网');
        await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
        expect(refreshPublicAIContent).toHaveBeenCalledTimes(2);
        expect(onUpdated).toHaveBeenCalledTimes(1);
        unmount();
    });
});
