import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { listReviewedContent } from '../../api/content'
import { useExportItems } from './useExportItems'

vi.mock('../../api/content', () => ({
  listReviewedContent: vi.fn(),
}))

vi.mock('antd', () => ({
  message: { success: vi.fn(), error: vi.fn() },
}))

describe('useExportItems', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps loaded output pools isolated by content kind', async () => {
    listReviewedContent.mockImplementation(({ kind }) => Promise.resolve({
      data: {
        data: [{
          id: 1,
          title: kind === 'article' ? '文章结果' : '快讯结果',
          published_at: new Date().toISOString(),
          review_score: 9,
          enrichment_status: 'completed',
        }],
        total: 1,
      },
    }))

    const { result, rerender } = renderHook(
      ({ kind }) => useExportItems(kind, []),
      { initialProps: { kind: 'article' } },
    )

    await act(async () => result.current.loadItems())
    expect(result.current.visibleItems.map((item) => item.title)).toEqual(['文章结果'])

    rerender({ kind: 'news' })
    expect(result.current.visibleItems).toEqual([])

    await act(async () => result.current.loadItems())
    expect(result.current.visibleItems.map((item) => item.title)).toEqual(['快讯结果'])

    rerender({ kind: 'article' })
    expect(result.current.visibleItems.map((item) => item.title)).toEqual(['文章结果'])
  })
})
