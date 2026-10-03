import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { updateCredentials } from '../../../api/auth';
import AccountSecurityCard from './AccountSecurityCard';

vi.mock('../../../api/auth', () => ({ updateCredentials: vi.fn() }));
beforeAll(() => {
    window.matchMedia = vi.fn().mockImplementation(() => ({
        matches: false, addListener: vi.fn(), removeListener: vi.fn(),
        addEventListener: vi.fn(), removeEventListener: vi.fn(),
    }));
});

describe('account password confirmation', () => {
    it('does not submit a new password when confirmation is missing or different', async () => {
        render(<AccountSecurityCard />);
        fireEvent.change(screen.getByLabelText('当前密码'), { target: { value: 'current-password!123' } });
        fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'new-password!12345' } });
        fireEvent.click(screen.getByRole('button', { name: '更新账户信息' }));
        expect(await screen.findByText('两次输入的密码不一致')).toBeInTheDocument();
        expect(updateCredentials).not.toHaveBeenCalled();
        fireEvent.change(screen.getByLabelText('确认新密码'), { target: { value: 'different-password!123' } });
        fireEvent.click(screen.getByRole('button', { name: '更新账户信息' }));
        await waitFor(() => expect(screen.getByText('两次输入的密码不一致')).toBeInTheDocument());
        expect(updateCredentials).not.toHaveBeenCalled();
    });
});
