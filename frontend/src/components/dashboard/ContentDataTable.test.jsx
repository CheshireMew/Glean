import React, { useState } from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ContentDataTable from './ContentDataTable'

vi.mock('antd', () => ({
  Alert: () => null,
  Button: ({ children, ...props }) => <button type="button" {...props}>{children}</button>,
  Table: () => null,
}))

vi.mock('./NewsExpandedView', () => ({ default: () => null }))

vi.mock('./NewsToolbar', () => ({
  default: ({ searchValue, onSearchChange, onSourceChange }) => (
    <div>
      <input aria-label="搜索" value={searchValue} onChange={(event) => onSearchChange(event.target.value)} />
      <button type="button" onClick={() => onSourceChange('PANews')}>选择 PANews</button>
    </div>
  ),
}))

function Harness({ kind, fetchItems }) {
  return <QueryHarness key={kind} kind={kind} fetchItems={fetchItems} />
}

function QueryHarness({ kind, fetchItems }) {
  const [filterSource, setFilterSource] = useState(undefined)
  const [filterKeyword, setFilterKeyword] = useState('')

  return (
    <ContentDataTable
      listState={{
        items: [],
        loading: false,
        loaded: true,
        error: null,
        stale: false,
        pagination: { current: 1, pageSize: 10, total: 0 },
        filterSource,
        filterKeyword,
        setFilterSource,
        setFilterKeyword,
        fetchItems,
      }}
      columns={[]}
      spiders={[]}
      contentKind={kind}
    />
  )
}

describe('ContentDataTable query truth', () => {
  afterEach(() => vi.useRealTimers())

  it('combines the latest keyword and source and cancels the stale debounced query', () => {
    vi.useFakeTimers()
    const fetchItems = vi.fn()
    const { rerender } = render(<Harness kind="news" fetchItems={fetchItems} />)

    fireEvent.change(screen.getByRole('textbox', { name: '搜索' }), { target: { value: '以太坊' } })
    fireEvent.click(screen.getByRole('button', { name: '选择 PANews' }))

    expect(fetchItems).toHaveBeenCalledTimes(1)
    expect(fetchItems).toHaveBeenLastCalledWith(1, 10, 'PANews', '以太坊')
    act(() => vi.advanceTimersByTime(500))
    expect(fetchItems).toHaveBeenCalledTimes(1)

    rerender(<Harness kind="article" fetchItems={fetchItems} />)
    expect(screen.getByRole('textbox', { name: '搜索' })).toHaveValue('')
  })
})
