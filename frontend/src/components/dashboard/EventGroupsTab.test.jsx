import React from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import EventGroupsTab from './EventGroupsTab'

const fetchGroups = vi.fn()
const setFilterSource = vi.fn()
const setFilterKeyword = vi.fn()

vi.mock('../../hooks/dashboard/useEventGroups', () => ({
  useEventGroups: () => ({
    groups: [], loading: false, loaded: true, error: null, stale: false,
    pagination: { current: 1, pageSize: 20, total: 0 },
    summary: { multi_source: 0, single_source: 0 },
    filterSource: undefined, filterKeyword: '', expandedGroups: new Set(),
    setFilterSource, setFilterKeyword, toggleGroup: vi.fn(), fetchGroups,
    retry: vi.fn(), deleteGroupItem: vi.fn(),
  }),
}))

vi.mock('../../hooks/dashboard/useSimilarityCheck', () => ({
  useSimilarityCheck: () => ({
    newsId1: '', newsId2: '', similarityResult: null, checkingLoading: false,
    setNewsId1: vi.fn(), setNewsId2: vi.fn(), checkSimilarity: vi.fn(),
  }),
}))

vi.mock('./NewsToolbar', () => ({
  default: ({ onSearchChange, onSourceChange }) => (
    <div>
      <input aria-label="事件搜索" onChange={(event) => onSearchChange(event.target.value)} />
      <button type="button" onClick={() => onSourceChange('PANews')}>筛选 PANews</button>
    </div>
  ),
}))
vi.mock('./EventGroupsList', () => ({ default: () => null }))
vi.mock('./EventSimilarityCard', () => ({ default: () => null }))

describe('EventGroupsTab filters', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('keeps the latest search keyword when a source is selected immediately', () => {
    vi.useFakeTimers()
    render(<EventGroupsTab spiders={[]} contentKind="news" />)

    fireEvent.change(screen.getByRole('textbox', { name: '事件搜索' }), { target: { value: '比特币' } })
    fireEvent.click(screen.getByRole('button', { name: '筛选 PANews' }))

    expect(fetchGroups).toHaveBeenCalledTimes(1)
    expect(fetchGroups).toHaveBeenCalledWith(1, 20, 'PANews', '比特币')
    act(() => vi.advanceTimersByTime(500))
    expect(fetchGroups).toHaveBeenCalledTimes(1)
  })
})
