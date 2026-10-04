import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { getAuthSession } from '../api/auth';
import { setBrowserSession } from './session';
import { useAuthSession } from './useAuthSession';

vi.mock('../api/auth', () => ({ getAuthSession: vi.fn(), logout: vi.fn() }));
const seedToken = () => setBrowserSession(`header.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 60 }))}.signature`);

describe('restoring a login', () => {
    it('waits for server validation before allowing the admin page', async () => {
        seedToken();
        let finish;
        getAuthSession.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
        const { result } = renderHook(() => useAuthSession());
        expect(result.current.authenticated).toBe(false);
        expect(result.current.loading).toBe(true);
        await act(async () => finish({ data: { username: 'admin' } }));
        expect(result.current.authenticated).toBe(true);
    });
    it('keeps the admin page closed during an outage and allows retry', async () => {
        seedToken();
        getAuthSession.mockRejectedValueOnce(new Error('连接失败')).mockResolvedValueOnce({ data: { username: 'admin' } });
        const { result } = renderHook(() => useAuthSession());
        await waitFor(() => expect(result.current.error).toBe('连接失败'));
        expect(result.current.authenticated).toBe(false);
        act(() => result.current.retry());
        await waitFor(() => expect(result.current.authenticated).toBe(true));
    });
});
