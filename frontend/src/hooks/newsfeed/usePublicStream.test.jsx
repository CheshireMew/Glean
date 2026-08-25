import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getPublicContent } from '../../api/content'
import { usePublicStream } from './usePublicStream'

vi.mock('../../api/content', () => ({
  getPublicContent: vi.fn(),
}))

describe('usePublicStream', () => {
  beforeEach(() => vi.clearAllMocks())

  it('refreshes a stream that was initially empty', async () => {
    getPublicContent
      .mockResolvedValueOnce({ data: { items: [], next_cursor: null, revision: 'r1' } })
      .mockResolvedValueOnce({ data: { items: [{ id: 9, title: 'New item' }], next_cursor: null, revision: 'r2' } })

    const { result } = renderHook(() => usePublicStream('briefs'))
    await act(async () => result.current.ensureLoaded())
    await waitFor(() => expect(result.current.state.loaded).toBe(true))
    expect(result.current.state.items).toEqual([])

    await act(async () => result.current.refresh())
    await waitFor(() => expect(result.current.state.items).toHaveLength(1))
    expect(result.current.state.items[0].title).toBe('New item')
  })

  it('rebuilds the loaded snapshot so updates and removals are both visible', async () => {
    const firstPage = Array.from({ length: 20 }, (_, index) => ({ id: index + 1, title: `Item ${index + 1}` }))
    const secondPage = Array.from({ length: 20 }, (_, index) => ({ id: index + 21, title: `Item ${index + 21}` }))
    const refreshed = [
      { id: 100, title: 'Brand new' },
      { id: 1, title: 'Item 1 updated' },
      ...Array.from({ length: 38 }, (_, index) => ({ id: index + 2, title: `Item ${index + 2}` })),
    ]
    getPublicContent
      .mockResolvedValueOnce({ data: { items: firstPage, next_cursor: 'cursor-1', revision: 'r1' } })
      .mockResolvedValueOnce({ data: { items: secondPage, next_cursor: 'cursor-2', revision: 'r1' } })
      .mockResolvedValueOnce({ data: { items: refreshed, next_cursor: 'cursor-refreshed', revision: 'r2' } })

    const { result } = renderHook(() => usePublicStream('briefs'))
    await act(async () => result.current.ensureLoaded())
    await act(async () => result.current.loadMore())
    expect(result.current.state.items).toHaveLength(40)

    await act(async () => result.current.refresh())

    expect(getPublicContent).toHaveBeenLastCalledWith('briefs', 40, null, 'r1', null)
    expect(result.current.state.items).toHaveLength(40)
    expect(result.current.state.items.find((item) => item.id === 1)?.title).toBe('Item 1 updated')
    expect(result.current.state.items.some((item) => item.id === 40)).toBe(false)
    expect(result.current.state.items[0].id).toBe(100)
    expect(result.current.state.page).toBe(2)
  })

  it('keeps the current snapshot when the server revision is unchanged', async () => {
    getPublicContent
      .mockResolvedValueOnce({ data: { items: [{ id: 1, title: 'Known' }], next_cursor: null, revision: 'r1' } })
      .mockResolvedValueOnce({ data: { items: [], next_cursor: null, revision: 'r1', not_modified: true } })

    const { result } = renderHook(() => usePublicStream('briefs'))
    await act(async () => result.current.ensureLoaded())
    await act(async () => result.current.refresh())

    expect(getPublicContent).toHaveBeenCalledTimes(2)
    expect(getPublicContent).toHaveBeenLastCalledWith('briefs', 20, null, 'r1', null)
    expect(result.current.state.items).toEqual([{ id: 1, title: 'Known' }])
  })

  it('keeps the last good snapshot and reports a refresh failure', async () => {
    getPublicContent
      .mockResolvedValueOnce({ data: { items: [{ id: 1, title: 'Known' }], next_cursor: null } })
      .mockRejectedValueOnce(new Error('network unavailable'))

    const { result } = renderHook(() => usePublicStream('longform'))
    await act(async () => result.current.ensureLoaded())
    await act(async () => result.current.refresh())

    expect(result.current.state.items).toEqual([{ id: 1, title: 'Known' }])
    expect(result.current.state.refreshError).toBe('network unavailable')
  })

  it('coalesces repeated load-more calls made before React publishes the loading state', async () => {
    let resolveNextPage
    getPublicContent
      .mockResolvedValueOnce({ data: { items: [{ id: 1, title: 'Known' }], next_cursor: 'cursor-1', revision: 'r1' } })
      .mockImplementationOnce(() => new Promise((resolve) => { resolveNextPage = resolve }))

    const { result } = renderHook(() => usePublicStream('longform'))
    await act(async () => result.current.ensureLoaded())

    let firstRequest
    act(() => {
      firstRequest = result.current.loadMore()
      void result.current.loadMore()
    })

    expect(getPublicContent).toHaveBeenCalledTimes(2)
    expect(getPublicContent).toHaveBeenLastCalledWith('longform', 20, 'cursor-1', null, null)

    resolveNextPage({ data: { items: [{ id: 2, title: 'Next' }], next_cursor: null, revision: 'r1' } })
    await act(async () => firstRequest)
    expect(result.current.state.items.map((item) => item.id)).toEqual([1, 2])
  })
})
