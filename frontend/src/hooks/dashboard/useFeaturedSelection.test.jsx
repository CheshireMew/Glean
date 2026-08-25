import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useFeaturedSelection } from './useFeaturedSelection';

vi.mock('antd', () => ({
    message: {
        success: vi.fn(),
        warning: vi.fn(),
    },
}));

describe('useFeaturedSelection', () => {
    beforeEach(() => localStorage.clear());

    it('keeps typed output identities and separate drafts for each content kind', () => {
        const { result, rerender } = renderHook(
            ({ kind }) => useFeaturedSelection(kind),
            { initialProps: { kind: 'news' } },
        );

        act(() => result.current.handleAddToFeatured({ id: 7, title: '快讯' }, 'review'));
        expect(result.current.manuallyFeatured[0].outputKey).toBe('review:7');
        expect(result.current.manuallyFeatured[0].outputRef).toEqual({ scope: 'review', id: 7 });

        rerender({ kind: 'article' });
        expect(result.current.manuallyFeatured).toEqual([]);
        act(() => result.current.handleAddToFeatured({ id: 7, title: '文章' }, 'archive'));
        expect(result.current.manuallyFeatured[0].outputKey).toBe('archive:7');

        rerender({ kind: 'news' });
        expect(result.current.manuallyFeatured.map((item) => item.outputKey)).toEqual(['review:7']);
        expect(JSON.parse(localStorage.getItem('ainews.output-draft.news'))[0].outputKey).toBe('review:7');
        expect(JSON.parse(localStorage.getItem('ainews.output-draft.article'))[0].outputKey).toBe('archive:7');
    });
});
