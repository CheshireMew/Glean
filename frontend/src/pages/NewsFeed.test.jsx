import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import client from '../api/client';
import NewsFeed from './NewsFeed';

vi.mock('../api/client', () => ({ default: { request: vi.fn() } }));

const sourceItems = [
    { id: 1, title: 'No Blind Trust in AI-Generated Code', source_key: 'hacker_news', source_site: 'Hacker News', source_url: 'https://example.test/hn', source_excerpt: '', published_at: '2026-09-26 10:00:00' },
    { id: 2, title: '模型评测方法', source_key: 'rss__qbitai', source_site: '量子位', source_url: 'https://example.test/qbit', source_excerpt: '这是来源真实提供的文字。', published_at: '2026-09-26 09:00:00' },
    { id: 3, title: 'Lobsters 中文标题', source_key: 'lobsters', source_site: 'Lobsters', source_url: 'https://example.test/lobsters', source_excerpt: '', published_at: '2026-09-26 08:00:00' },
];
const sources = [
    { key: 'hacker_news', name: 'Hacker News', total: 1 },
    { key: 'rss__qbitai', name: '量子位', total: 1 },
    { key: 'rss__infoq-cn', name: 'InfoQ 中文', total: 0 },
    { key: 'rss__huggingface-blog', name: 'Hugging Face Blog', total: 0 },
    { key: 'lobsters', name: 'Lobsters', total: 1 },
];

beforeEach(() => {
    window.matchMedia = vi.fn().mockImplementation((query) => ({
        matches: false, media: query, addListener: vi.fn(), removeListener: vi.fn(),
        addEventListener: vi.fn(), removeEventListener: vi.fn(),
    }));
    client.request.mockReset();
    client.request.mockImplementation(async ({ url, params = {} }) => {
        if (url === '/public/config') return { data: { links: {}, publications: [
            { public_slug: 'deep-reads', display_name: '深度文章', content_type: 'article' },
            { public_slug: 'daily-briefs', display_name: '精选快讯', content_type: 'news' },
        ] } };
        if (url === '/public/ai/content') {
            const items = sourceItems.filter((item) => (!params.source || item.source_key === params.source)
                && (!params.query || item.title.includes(params.query)));
            return { data: { items, sources, total: items.length, limit: 20, offset: 0 } };
        }
        return { data: { items: [], total: 0, next_cursor: null, revision: 'empty' } };
    });
});

describe('public channel layout', () => {
    it('puts AI in the existing channel bar, reuses the header and hides secondary feeds', async () => {
        render(<MemoryRouter><NewsFeed /></MemoryRouter>);
        const channels = screen.getByRole('navigation', { name: '内容频道' });
        expect(await within(channels).findByRole('button', { name: /深度文章/ })).toBeInTheDocument();
        const aiButton = within(channels).getByRole('button', { name: 'AI 资讯' });
        expect(screen.queryByRole('link', { name: 'AI 资讯' })).not.toBeInTheDocument();
        expect(screen.queryByText('精选快讯')).not.toBeInTheDocument();
        for (const name of ['快讯', '快讯日报', '文章日报']) expect(screen.queryByRole('tab', { name, exact: true })).not.toBeInTheDocument();
        expect(screen.queryByText('7x24h 快讯')).not.toBeInTheDocument();
        expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
        fireEvent.click(aiButton);
        expect(await screen.findByText('No Blind Trust in AI-Generated Code')).toBeInTheDocument();
        expect(aiButton).toHaveAttribute('aria-pressed', 'true');
        expect(aiButton).toHaveClass('bg-blue-600');
        expect(screen.getByRole('heading', { name: 'Glean', level: 1 })).toBeInTheDocument();
        expect(screen.getByPlaceholderText('搜索 AI 资讯...')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: '切换到暗色模式' }));
        expect(document.documentElement).toHaveClass('dark');
        expect(screen.queryByText('来源未提供正文或摘要')).not.toBeInTheDocument();
        expect(screen.queryByText('来源提供内容 · 未确认是否为全文')).not.toBeInTheDocument();
        expect(screen.getByText('这是来源真实提供的文字。')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'No Blind Trust in AI-Generated Code' })).toHaveAttribute('href', 'https://example.test/hn');
        expect(screen.queryByText(/标题导读/)).not.toBeInTheDocument();
        fireEvent.click(within(screen.getByRole('navigation', { name: 'AI 资讯来源' })).getByRole('button', { name: /Lobsters/ }));
        await waitFor(() => expect(screen.queryByText('No Blind Trust in AI-Generated Code')).not.toBeInTheDocument());
        expect(await screen.findByRole('link', { name: 'Lobsters 中文标题' })).toHaveAttribute('href', 'https://example.test/lobsters');
        fireEvent.click(within(screen.getByRole('navigation', { name: 'AI 资讯来源' })).getByRole('button', { name: /量子位/ }));
        await waitFor(() => expect(screen.queryByText('No Blind Trust in AI-Generated Code')).not.toBeInTheDocument());
        expect(await screen.findByText('模型评测方法')).toBeInTheDocument();
        fireEvent.change(screen.getByPlaceholderText('搜索 AI 资讯...'), { target: { value: '不存在' } });
        expect(await screen.findByText('无匹配结果', {}, { timeout: 2500 })).toBeInTheDocument();
        fireEvent.click(within(channels).getByRole('button', { name: '全部默认频道' }));
        expect(screen.getByRole('tab', { name: '文章', exact: true })).toBeInTheDocument();
    });

    it('opens the AI channel from its shared URL and supports retrying a failed load', async () => {
        const working = client.request.getMockImplementation();
        let failed = false;
        client.request.mockImplementation((request) => {
            if (request.url === '/public/ai/content' && !failed) {
                failed = true;
                return Promise.reject(new Error('测试连接失败'));
            }
            return working(request);
        });
        render(<MemoryRouter initialEntries={['/?channel=ai']}><NewsFeed /></MemoryRouter>);
        expect(await screen.findByRole('alert')).toHaveTextContent('测试连接失败');
        fireEvent.click(screen.getByRole('button', { name: '重试' }));
        expect(await screen.findByText('No Blind Trust in AI-Generated Code')).toBeInTheDocument();
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
});
