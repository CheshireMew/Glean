import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getContentOverview, getContentStats } from '../../api/content'
import { useDashboardOverviewData } from './useDashboardOverviewData'

vi.mock('../../api/content', () => ({
  getContentOverview: vi.fn(),
  getContentStats: vi.fn(),
}))

describe('useDashboardOverviewData', () => {
  beforeEach(() => vi.clearAllMocks())

  it('distinguishes unavailable statistics from legitimate zero counts', async () => {
    getContentStats.mockResolvedValueOnce({ data: { stats: [] } })
    getContentOverview.mockRejectedValueOnce(new Error('overview unavailable'))
    const { result } = renderHook(() => useDashboardOverviewData('news'))

    await waitFor(() => expect(result.current.loadState.loading).toBe(false))
    expect(result.current.loadState.loaded).toBe(false)
    expect(result.current.overview).toBeNull()
    expect(result.current.loadState.error).toBeTruthy()

    getContentStats.mockResolvedValueOnce({ data: { stats: [] } })
    getContentOverview.mockResolvedValueOnce({
      data: { incoming: 0, archive: 0, blocked: 0, review: 4, selected: 0, discarded: 0 },
    })
    await act(async () => result.current.refreshOverview({ includeStats: true }))
    expect(result.current.loadState.loaded).toBe(true)
    expect(result.current.overview.incoming).toBe(0)
    expect(result.current.overview.review).toBe(4)

    getContentOverview.mockRejectedValueOnce(new Error('refresh unavailable'))
    await act(async () => result.current.refreshOverview())
    expect(result.current.loadState.loaded).toBe(true)
    expect(result.current.overview.review).toBe(4)
    expect(result.current.loadState.error).toBeTruthy()
  })
})
