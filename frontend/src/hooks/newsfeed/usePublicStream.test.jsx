import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getPublicContent } from '../../api/content'
import { usePublicStream } from './usePublicStream'

vi.mock('../../api/content', () => ({
  getPublicContent: vi.fn(),
}))

describe('usePublicStream', () => {
  beforeEach(() => vi.resetAllMocks())

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

  it('refreshes the full loaded depth when a later page has a newer revision', async () => {
    const initial = Array.from({ length: 20 }, (_, index) => ({ id: index + 1, title: `Old ${index}` }))
    const later = Array.from({ length: 20 }, (_, index) => ({ id: index + 21, title: `Later ${index}` }))
    getPublicContent
      .mockResolvedValueOnce({ data: { items: initial, next_cursor: 'page-2', revision: 'r1' } })
      .mockResolvedValueOnce({ data: { items: later, next_cursor: 'page-3', revision: 'r2' } })
      .mockResolvedValueOnce({ data: { items: [{ ...initial[0], title: 'Updated first item' }, ...initial.slice(1), ...later], next_cursor: 'page-3', revision: 'r2' } })
    const { result } = renderHook(() => usePublicStream('longform'))
    await act(async () => result.current.ensureLoaded())
    await act(async () => result.current.loadMore())
    await act(async () => result.current.refresh())
    expect(getPublicContent).toHaveBeenLastCalledWith('longform', 40, null, null, null)
    expect(result.current.state.items).toHaveLength(40)
    expect(result.current.state.items[0].title).toBe('Updated first item')
    expect(result.current.state.revision).toBe('r2')
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

  it.each(['success', 'not_modified', 'failure'])('finishes pagination before applying a concurrent %s refresh', async (outcome) => {
    let resolveAppend
    const firstPage = Array.from({ length: 20 }, (_, index) => ({ id: index + 1 }))
    const nextPage = Array.from({ length: 20 }, (_, index) => ({ id: index + 21 }))
    getPublicContent
      .mockResolvedValueOnce({ data: { items: firstPage, next_cursor: 'c1', revision: 'r1' } })
      .mockImplementationOnce(() => new Promise((resolve) => { resolveAppend = resolve }))
    if (outcome === 'failure') getPublicContent.mockRejectedValueOnce(new Error('refresh failed'))
    else getPublicContent.mockResolvedValueOnce({ data: {
      items: outcome === 'success' ? [...firstPage, ...nextPage] : [],
      next_cursor: 'c2', revision: 'r1', not_modified: outcome === 'not_modified',
    } })
    getPublicContent.mockResolvedValueOnce({ data: { items: [{ id: 41 }], next_cursor: null, revision: 'r1' } })
    const { result } = renderHook(() => usePublicStream('briefs'))
    await act(async () => result.current.ensureLoaded())
    let append
    let refresh
    act(() => {
      append = result.current.loadMore()
      refresh = result.current.refresh()
    })
    await act(async () => {
      resolveAppend({ data: { items: nextPage, next_cursor: 'c2', revision: 'r1' } })
      await Promise.all([append, refresh])
    })
    expect(result.current.state.loadingMore).toBe(false)
    expect(result.current.state.loading).toBe(false)
    expect(result.current.state.items).toHaveLength(40)
    expect(getPublicContent.mock.calls[2][1]).toBe(40)
    await act(async () => result.current.loadMore())
    expect(result.current.state.items).toHaveLength(41)
    expect(result.current.state.items[40].id).toBe(41)
  })

  it.each(['success', 'not_modified', 'failure'])('uses the current cursor when pagination follows an in-flight %s refresh', async (outcome) => {
    let finishRefresh
    getPublicContent
      .mockResolvedValueOnce({ data: { items: [{ id: 1 }], next_cursor: 'old-cursor', revision: 'r1' } })
      .mockImplementationOnce(() => new Promise((resolve, reject) => {
        finishRefresh = () => outcome === 'failure' ? reject(new Error('refresh failed')) : resolve({ data: {
          items: [{ id: 1, title: 'updated' }], next_cursor: 'new-cursor',
          revision: 'r2', not_modified: outcome === 'not_modified',
        } })
      }))
      .mockResolvedValueOnce({ data: { items: [{ id: 2 }], next_cursor: null, revision: 'r2' } })
    const { result } = renderHook(() => usePublicStream('briefs'))
    await act(async () => result.current.ensureLoaded())
    let refresh
    let append
    act(() => {
      refresh = result.current.refresh()
      append = result.current.loadMore()
      void result.current.loadMore()
    })
    expect(getPublicContent).toHaveBeenCalledTimes(2)
    await act(async () => {
      finishRefresh()
      await Promise.all([refresh, append])
    })
    expect(getPublicContent).toHaveBeenCalledTimes(3)
    expect(getPublicContent.mock.calls[2][2]).toBe(outcome === 'success' ? 'new-cursor' : 'old-cursor')
    expect(result.current.state.items.map((item) => item.id)).toEqual([1, 2])
    expect(result.current.state.loadingMore).toBe(false)
  })

  it('rejects old stream responses without clearing the new stream request', async () => {
    let resolveOld
    let resolveNew
    getPublicContent
      .mockResolvedValueOnce({ data: { items: [{ id: 1 }], next_cursor: 'old', revision: 'r1' } })
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveNew = resolve }))
      .mockResolvedValueOnce({ data: { items: [{ id: 11 }], next_cursor: null, revision: 'r2' } })
    const { result, rerender } = renderHook(({ stream }) => usePublicStream(stream), { initialProps: { stream: 'briefs' } })
    await act(async () => result.current.ensureLoaded())
    let oldPage
    let oldRefresh
    act(() => {
      oldPage = result.current.loadMore()
      oldRefresh = result.current.refresh()
    })
    rerender({ stream: 'longform' })
    let newPage
    act(() => { newPage = result.current.ensureLoaded() })
    await act(async () => {
      resolveOld({ data: { items: [{ id: 2 }], next_cursor: null } })
      await Promise.all([oldPage, oldRefresh])
    })
    expect(result.current.state.items).toEqual([])
    expect(result.current.state.loading).toBe(true)
    await act(async () => {
      resolveNew({ data: { items: [{ id: 10 }], next_cursor: 'new', revision: 'r2' } })
      await newPage
    })
    await act(async () => result.current.loadMore())
    expect(result.current.state.items.map((item) => item.id)).toEqual([10, 11])
    expect(getPublicContent).toHaveBeenCalledTimes(4)
  })
})
