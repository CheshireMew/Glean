import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import RssSourceManager from './RssSourceManager';
import { previewRssSource } from '../../api/config';

vi.mock('../../api/config', () => ({ previewRssSource: vi.fn() }));
beforeAll(() => {
    window.matchMedia = vi.fn().mockImplementation((query) => ({ matches: false, media: query, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() }));
});

describe('RSS preview', () => {
    it('shows fetch errors and allows retrying', async () => {
        previewRssSource.mockRejectedValueOnce(new Error('RSS 预览失败：连接超时'));
        render(<RssSourceManager sources={[]} contentKind="article" onCreate={vi.fn()} onUpdate={vi.fn()} onDelete={vi.fn()} />);
        fireEvent.click(screen.getByText('新增 RSS 源'));
        fireEvent.change(screen.getByLabelText('RSS 地址'), { target: { value: 'https://example.com/feed' } });
        fireEvent.click(screen.getByText('预览内容'));
        expect(await screen.findByText('RSS 预览失败：连接超时')).toBeInTheDocument();
        previewRssSource.mockResolvedValueOnce({ data: { notice: '重试成功', items: [] } });
        fireEvent.click(screen.getByText('预览内容'));
        expect(await screen.findByText('重试成功')).toBeInTheDocument();
        expect(screen.queryByText('RSS 预览失败：连接超时')).not.toBeInTheDocument();
    });

    it('previews before required source details are filled, without saving', async () => {
        const onCreate = vi.fn();
        previewRssSource.mockResolvedValue({ data: { notice: '订阅源内容，全文状态未知', items: [{ title: 'An essay', url: 'https://example.com/article', author: 'Writer', published_at: '2026-09-05', content: 'First paragraph\n\nLast paragraph' }] } });
        render(<RssSourceManager sources={[]} contentKind="article" onCreate={onCreate} onUpdate={vi.fn()} onDelete={vi.fn()} />);
        fireEvent.click(screen.getByText('新增 RSS 源'));
        fireEvent.change(screen.getByLabelText('RSS 地址'), { target: { value: 'https://example.com/feed' } });
        fireEvent.click(screen.getByText('预览内容'));
        expect(await screen.findByText('An essay')).toBeInTheDocument();
        expect(previewRssSource).toHaveBeenCalledWith({ feed_url: 'https://example.com/feed', parser_type: 'generic', limit: 3 });
        expect(onCreate).not.toHaveBeenCalled();
        fireEvent.change(screen.getByLabelText('RSS 地址'), { target: { value: 'https://example.com/other' } });
        await waitFor(() => expect(screen.queryByText('An essay')).not.toBeInTheDocument());
    });
});
