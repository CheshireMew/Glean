import { beforeEach, describe, expect, it, vi } from 'vitest';
import { logout } from './auth';
import { requestOperation } from './operations';
import { getCsrfToken, setBrowserSession } from '../auth/session';

vi.mock('./operations', () => ({ requestOperation: vi.fn() }));
const token = () => `header.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 60 }))}.signature`;

describe('server logout', () => {
    beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); });
    it('revokes the server session before clearing the browser token', async () => {
        const value = token();
        setBrowserSession(value);
        requestOperation.mockImplementation(async () => { expect(getCsrfToken()).toBe(value); });
        await logout();
        expect(requestOperation).toHaveBeenCalledWith('logout');
        expect(getCsrfToken()).toBeNull();
    });
    it('does not pretend logout succeeded when the server is unavailable', async () => {
        const value = token();
        setBrowserSession(value);
        requestOperation.mockRejectedValue(new Error('连接失败'));
        await expect(logout()).rejects.toThrow('连接失败');
        expect(getCsrfToken()).toBe(value);
    });
    it('clears a session that the server already rejected', async () => {
        setBrowserSession(token());
        requestOperation.mockRejectedValue({ response: { status: 401 } });
        await logout();
        expect(getCsrfToken()).toBeNull();
    });
});
