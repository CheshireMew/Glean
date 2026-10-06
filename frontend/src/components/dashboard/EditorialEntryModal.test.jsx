import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import client from '../../api/client';
import EditorialEntryModal from './EditorialEntryModal';

vi.mock('../../api/client', () => ({ default: { request: vi.fn() } }));

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
}

function entry(id, title) {
    return { id, title, review_status: 'selected', review_summary: `${title} summary`, review_reason: 'reason',
        citations: [], tags: [], revisions: [], feedback: [], editorial_version: 1 };
}

beforeAll(() => {
    window.matchMedia = vi.fn().mockImplementation((query) => ({
        matches: false, media: query, addListener: vi.fn(), removeListener: vi.fn(),
        addEventListener: vi.fn(), removeEventListener: vi.fn(),
    }));
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
});
beforeEach(() => vi.clearAllMocks());

describe('editorial object identity', () => {
    it('keeps saving disabled until the current object is confirmed', async () => {
        const loading = deferred();
        client.request.mockReturnValue(loading.promise);
        render(<EditorialEntryModal entryId={1} open onClose={() => {}} />);
        expect(screen.getByRole('button', { name: '保存新修订' })).toBeDisabled();
        fireEvent.click(screen.getByRole('button', { name: '保存新修订' }));
        expect(client.request).toHaveBeenCalledTimes(1);
        await act(async () => loading.resolve({ data: entry(1, 'A title') }));
        expect(screen.getByRole('button', { name: '保存新修订' })).toBeEnabled();
    });

    it('rejects an old response after reopening the same object', async () => {
        const old = deferred();
        client.request.mockReturnValueOnce(old.promise).mockResolvedValueOnce({ data: entry(1, 'A latest') });
        const { rerender } = render(<EditorialEntryModal entryId={1} open onClose={() => {}} />);
        rerender(<EditorialEntryModal entryId={1} open={false} onClose={() => {}} />);
        rerender(<EditorialEntryModal entryId={1} open onClose={() => {}} />);
        await screen.findByDisplayValue('A latest');
        await act(async () => old.resolve({ data: entry(1, 'A obsolete') }));
        expect(screen.getByLabelText('发布标题')).toHaveValue('A latest');
    });

    it('ignores a late A load after opening B and saves only confirmed B fields', async () => {
        const a = deferred();
        const b = entry(2, 'B title');
        client.request.mockImplementation(({ method, url, data }) => {
            if (method === 'get' && url === '/editorial/entries/1') return a.promise;
            if (method === 'get' && url === '/editorial/entries/2') return Promise.resolve({ data: b });
            if (method === 'put') return Promise.resolve({ data: { ...b, ...data } });
            throw new Error(`unexpected ${method} ${url}`);
        });
        const onSaved = vi.fn();
        const { rerender } = render(<EditorialEntryModal entryId={1} open onClose={() => {}} onSaved={onSaved} />);
        rerender(<EditorialEntryModal entryId={1} open={false} onClose={() => {}} onSaved={onSaved} />);
        rerender(<EditorialEntryModal entryId={2} open onClose={() => {}} onSaved={onSaved} />);
        await screen.findByDisplayValue('B title');
        await act(async () => a.resolve({ data: entry(1, 'A title') }));
        expect(screen.getByLabelText('发布标题')).toHaveValue('B title');
        fireEvent.change(screen.getByLabelText('发布标题'), { target: { value: 'B revised' } });
        fireEvent.click(screen.getByRole('button', { name: '保存新修订' }));
        await waitFor(() => expect(client.request.mock.calls.filter(([request]) => request.method === 'put')).toHaveLength(1));
        const write = client.request.mock.calls.find(([request]) => request.method === 'put')[0];
        expect(write.url).toBe('/editorial/entries/2');
        expect(write.data.title).toBe('B revised');
        expect(write.data.review_summary).toBe('B title summary');
    });

    it.each(['save', 'restore'])('ignores a late %s result after switching to B', async (operation) => {
        const completion = deferred();
        const a = { ...entry(1, 'A title'), revisions: [
            { revision_number: 2, snapshot: { title: 'A title' } },
            { revision_number: 1, snapshot: { title: 'A original' } },
        ] };
        client.request.mockImplementation(({ method, url }) => {
            if (method === 'get') return Promise.resolve({ data: url.endsWith('/1') ? a : entry(2, 'B title') });
            if (method === 'put' || method === 'post') return completion.promise;
            throw new Error(`unexpected ${method} ${url}`);
        });
        const onSaved = vi.fn();
        const { rerender } = render(<EditorialEntryModal entryId={1} open onClose={() => {}} onSaved={onSaved} />);
        await screen.findByDisplayValue('A title');
        if (operation === 'save') fireEvent.click(screen.getByRole('button', { name: '保存新修订' }));
        else {
            fireEvent.click(screen.getByRole('tab', { name: '修订记录 (2)' }));
            fireEvent.click(await screen.findByRole('button', { name: '恢复到此版本' }));
        }
        await waitFor(() => expect(client.request.mock.calls.some(([request]) => request.method !== 'get')).toBe(true));
        rerender(<EditorialEntryModal entryId={2} open onClose={() => {}} onSaved={onSaved} />);
        await screen.findByDisplayValue('B title');
        const loadsBeforeCompletion = client.request.mock.calls.filter(([request]) => request.method === 'get').length;
        await act(async () => completion.resolve({ data: entry(1, 'A changed') }));
        expect(screen.getByLabelText('发布标题')).toHaveValue('B title');
        expect(client.request.mock.calls.filter(([request]) => request.method === 'get')).toHaveLength(loadsBeforeCompletion);
        expect(onSaved).not.toHaveBeenCalled();
    });
});
