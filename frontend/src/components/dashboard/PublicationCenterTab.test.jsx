import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
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
