import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import client from '../../api/client';
import PublicationCenterTab from './PublicationCenterTab';

vi.mock('../../api/client', () => ({ default: { request: vi.fn() } }));
// Ant Design's table layout needs browser geometry. Keep this test focused on
// the real publication buttons and API calls, independent of that layout engine.
vi.mock('antd', async (importOriginal) => {
    const actual = await importOriginal();
    return {
        ...actual,
        Table: ({ dataSource = [], columns = [] }) => <div>{dataSource.map((row) =>
            <div key={row.id}>{columns.map((column, index) => <div key={index}>
                {column.render ? column.render(row[column.dataIndex], row, index) : row[column.dataIndex]}
            </div>)}</div>
        )}</div>,
    };
});

beforeAll(() => {
    vi.stubGlobal('ResizeObserver', class {
        observe() {}
        unobserve() {}
        disconnect() {}
    });
    window.matchMedia = vi.fn().mockImplementation((query) => ({
        matches: false, media: query, addListener: vi.fn(), removeListener: vi.fn(),
        addEventListener: vi.fn(), removeEventListener: vi.fn(),
    }));
});

afterAll(() => vi.unstubAllGlobals());
beforeEach(() => vi.clearAllMocks());

describe('website publication', () => {
    it('publishes a draft to the website without requesting external delivery', async () => {
        let published = false;
        client.request.mockImplementation(async ({ method, url, params }) => {
            if (url === '/editorial/drafts/7/publish') {
                expect(method).toBe('post');
                expect(params).toEqual({ website_only: true });
                published = true;
                return { data: { status: 'published', report_id: 8, operations: [] } };
            }
            if (url === '/editorial/drafts') {
                return { data: [{ id: 7, title: 'AI 精选', status: published ? 'published' : 'draft', content_type: 'article' }] };
            }
            return { data: [] };
        });
        render(<PublicationCenterTab />);
        fireEvent.click(screen.getByRole('tab', { name: '草稿与排期' }));
        fireEvent.click(await screen.findByRole('button', { name: '仅发布到网站' }));
        expect(await screen.findByText('已发布到网站')).toBeInTheDocument();
        await waitFor(() => expect(screen.queryByRole('button', { name: '仅发布到网站' })).not.toBeInTheDocument());
        const writes = client.request.mock.calls.map(([request]) => request).filter((request) => request.method === 'post');
        expect(writes).toHaveLength(1);
        expect(writes[0].params.website_only).toBe(true);
    });
});

describe('correction delivery feedback', () => {
    it('restores incomplete channel feedback when reopening the page', async () => {
        client.request.mockImplementation(async ({ url }) => ({ data: url === '/editorial/corrections' ? [{
            id: 4, correction_type: 'correction', message: 'Stored correction', published_at: null,
            delivery: { status: 'publishing', operations: [{
                operation_key: 'correction:4:channel-b', channel_slug: 'channel-b',
                status: 'failed', sent_parts: 0, parts: 1, last_error: 'persisted error',
            }] },
        }] : [] }));
        const first = render(<PublicationCenterTab />);
        fireEvent.click(screen.getByRole('tab', { name: '更正' }));
        expect(await screen.findByText('persisted error')).toBeInTheDocument();
        first.unmount();
        render(<PublicationCenterTab />);
        fireEvent.click(screen.getByRole('tab', { name: '更正' }));
        expect(await screen.findByText('更正尚未完整送达')).toBeInTheDocument();
        expect(screen.getByText('persisted error')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: '重试未完成部分' })).toBeInTheDocument();
        expect(client.request.mock.calls.every(([request]) => request.method === 'get')).toBe(true);
    });
    it.each(['failed', 'needs_attention'])('shows %s channels and their recovery action after a successful HTTP response', async (status) => {
        let recovered = false;
        client.request.mockImplementation(async ({ method, url, data }) => {
            if (method === 'post' && url === '/delivery/retry') {
                expect(data.operation_key).toBe('correction:4:channel-b');
                recovered = true;
                return { data: { status: 'sent' } };
            }
            if (method === 'post' && url === '/editorial/corrections/4/publish') return { data: {
                correction_id: 4, status: recovered ? 'published' : 'publishing', operations: [
                    { operation_key: 'correction:4:channel-a', channel_slug: 'channel-a', status: 'sent', sent_parts: 1, parts: 1 },
                    { operation_key: 'correction:4:channel-b', channel_slug: 'channel-b', status, sent_parts: 0, parts: 1, last_error: 'delivery error' },
                ],
            } };
            if (url === '/editorial/corrections') return { data: [{ id: 4, correction_type: 'correction', message: 'Fix the fact', event_title: 'Test event', published_at: recovered ? '2026-10-05T00:00:00Z' : null }] };
            return { data: [] };
        });
        render(<PublicationCenterTab />);
        fireEvent.click(screen.getByRole('tab', { name: '更正' }));
        fireEvent.click(await screen.findByRole('button', { name: '发送更正' }));
        expect(await screen.findByText('更正尚未完整送达')).toBeInTheDocument();
        expect(screen.queryByText('更正已发送')).not.toBeInTheDocument();
        expect(screen.getByText('channel-a')).toBeInTheDocument();
        expect(screen.getByText('channel-b')).toBeInTheDocument();
        expect(screen.getByText('delivery error')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: status === 'failed' ? '重试未完成部分' : '核对后确认补发' }));
        if (status === 'needs_attention') {
            expect(client.request.mock.calls.some(([request]) => request.url === '/delivery/retry')).toBe(false);
            fireEvent.click(await screen.findByRole('button', { name: '确认补发' }));
        }
        expect(await screen.findByText('已发布')).toBeInTheDocument();
        expect(client.request.mock.calls.filter(([request]) => request.url === '/delivery/retry')).toHaveLength(1);
        expect(screen.queryByText('更正尚未完整送达')).not.toBeInTheDocument();
    });
});
