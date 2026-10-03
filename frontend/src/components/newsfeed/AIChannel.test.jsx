import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import AIChannel from './AIChannel';
import { getPublicAIContent, refreshPublicAIContent } from '../../api/aiContent';

vi.mock('../../api/aiContent', () => ({ getPublicAIContent: vi.fn(), refreshPublicAIContent: vi.fn() }));
vi.mock('./ArticleList', () => ({ ArticleItem: ({ item }) => <p>{item.title}</p> }));
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

it('keeps saved articles visible while refreshing and displays new content after completion', async () => {
    vi.useFakeTimers();
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    const saved = { items: [{ id: 1, title: '已保存的文章' }], sources: [{ key: 'lobsters', name: 'Lobsters', total: 1 }], total: 1 };
    getPublicAIContent.mockResolvedValue({ data: saved });
    refreshPublicAIContent.mockResolvedValueOnce({ data: { updating: true, sources: [] } })
        .mockResolvedValue({ data: { updating: false, sources: [] } });
    const { unmount } = render(<AIChannel />);
    await act(async () => {});
    expect(screen.getByText('已保存的文章')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '正在更新…' })).toBeDisabled();
    expect(screen.queryByText('加载中...')).not.toBeInTheDocument();
    getPublicAIContent.mockResolvedValue({ data: { ...saved, items: [{ id: 2, title: '刚更新的中文标题' }] } });
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(screen.getByText('刚更新的中文标题')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '检查更新' })).toBeEnabled();
    expect(screen.queryByText('已保存的文章')).not.toBeInTheDocument();
    unmount();
});
