import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import WechatSourceManager from './WechatSourceManager';
import * as wechat from '../../api/wechat';
import { requestOperation } from '../../api/operations';

vi.mock('../../api/wechat', () => ({
    getWechatStatus: vi.fn(), startWechatLogin: vi.fn(), cancelWechatLogin: vi.fn(),
    disconnectWechat: vi.fn(), searchWechatAccounts: vi.fn(), getWechatSources: vi.fn(),
    addWechatSource: vi.fn(), updateWechatSource: vi.fn(),
}));
vi.mock('../../api/operations', () => ({ requestOperation: vi.fn() }));

beforeEach(() => {
    vi.resetAllMocks();
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
    window.matchMedia = vi.fn().mockImplementation((query) => ({ matches: false, media: query,
        addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    wechat.getWechatStatus.mockResolvedValue({ data: { state: 'connected', login: { state: 'idle' } } });
    wechat.getWechatSources.mockResolvedValue({ data: { sources: [] } });
    requestOperation.mockResolvedValue({ data: {} });
});

describe('微信公众号采集', () => {
    it('requires login before search and displays the real login QR returned by the server', async () => {
        wechat.getWechatStatus.mockResolvedValue({ data: { state: 'disconnected', login: { state: 'idle' } } });
        render(<WechatSourceManager />);
        expect(await screen.findByText('尚未登录')).toBeInTheDocument();
        expect(screen.getByRole('textbox', { name: '公众号名称或微信号' })).toBeDisabled();
        wechat.startWechatLogin.mockImplementation(async () => {
            wechat.getWechatStatus.mockResolvedValue({ data: { state: 'disconnected', login: {
                state: 'waiting', qr_image: 'data:image/png;base64,test', message: '请扫码确认',
            } } });
            return { data: {} };
        });
        fireEvent.click(screen.getByRole('button', { name: '扫码登录' }));
        expect(await screen.findByRole('img', { name: '微信公众平台登录二维码' })).toHaveAttribute('src', 'data:image/png;base64,test');
        expect(wechat.startWechatLogin).toHaveBeenCalledOnce();
    });

    it('searches, subscribes without duplicates and submits collection through the worker queue', async () => {
        const account = { fake_id: 'fake-account', name: '测试 AI 来源', alias: 'test_ai', introduction: '来源简介' };
        wechat.searchWechatAccounts.mockResolvedValue({ data: { accounts: [account], begin: 0, has_more: false } });
        wechat.addWechatSource.mockImplementation(async () => {
            wechat.getWechatSources.mockResolvedValue({ data: { sources: [{ ...account,
                id: 3, enabled: true, runtime_name: 'wechat__3', default_limit: 10, default_interval: 240,
            }] } });
            return { data: {} };
        });
        render(<WechatSourceManager />);
        await screen.findByText('已登录');
        fireEvent.change(screen.getByRole('textbox', { name: '公众号名称或微信号' }), { target: { value: '测试 AI' } });
        fireEvent.click(screen.getByRole('button', { name: /搜\s*索/ }));
        expect(await screen.findByText('来源简介')).toBeInTheDocument();
        expect(wechat.searchWechatAccounts).toHaveBeenCalledWith('测试 AI', 0);
        fireEvent.click(screen.getByRole('button', { name: /^添\s*加$/ }));
        expect(await screen.findByRole('button', { name: '已添加' })).toBeDisabled();
        expect(wechat.addWechatSource).toHaveBeenCalledWith(account);
        fireEvent.click(screen.getByRole('button', { name: '立即采集' }));
        await waitFor(() => expect(requestOperation).toHaveBeenCalledWith('runSpider', {
            path: { name: 'wechat__3' }, data: { items: 10 },
        }));
        expect(await screen.findByText('已加入采集队列，采集完成后可在 AI 资讯页查看')).toBeInTheDocument();
    });

    it('shows fetch failures without turning them into an empty successful search', async () => {
        wechat.searchWechatAccounts.mockRejectedValue(new Error('微信登录已失效，请重新扫码'));
        render(<WechatSourceManager />);
        await screen.findByText('已登录');
        fireEvent.change(screen.getByRole('textbox', { name: '公众号名称或微信号' }), { target: { value: '测试' } });
        fireEvent.click(screen.getByRole('button', { name: /搜\s*索/ }));
        expect(await screen.findByText('微信登录已失效，请重新扫码')).toBeInTheDocument();
        expect(screen.queryByText('没有找到公众号，可换用微信号搜索')).not.toBeInTheDocument();
    });
});
