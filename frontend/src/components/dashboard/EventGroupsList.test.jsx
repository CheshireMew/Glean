import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import EventGroupsList from './EventGroupsList'

vi.mock('./EventEvidenceDrawer', () => ({ default: () => null }))

vi.mock('antd', () => ({
  Alert: ({ message }) => <div>{message}</div>,
  Button: ({ children, onClick }) => <button type="button" onClick={onClick}>{children}</button>,
  Pagination: () => <nav aria-label="分页" />,
  Tag: ({ children }) => <span>{children}</span>,
}))

const group = {
  type: 'multi_source',
  event: { id: 12, title: '测试事件标题', published_at: '2026-08-24 12:00:00' },
  primary: { id: 1, title: '主来源', source_site: '主来源站点', source_url: 'https://example.test/main' },
  sources: [
    { id: 1, title: '主来源', source_site: '主来源站点', source_url: 'https://example.test/main' },
    { id: 2, title: '备用来源', source_site: '备用站点', source_url: 'https://example.test/alt', similarity: 0.9, published_at: '2026-08-24 12:01:00' },
  ],
  alternatives: [
    { id: 2, title: '备用来源', source_site: '备用站点', source_url: 'https://example.test/alt', similarity: 0.9, published_at: '2026-08-24 12:01:00' },
  ],
}

describe('EventGroupsList', () => {
  it('uses a keyboard-accessible disclosure button for multi-source events', () => {
    const toggleGroup = vi.fn()
    render(
      <EventGroupsList
        loading={false}
        loaded
        error={null}
        stale={false}
        groups={[group]}
        pagination={{ current: 1, pageSize: 20, total: 1 }}
        summary={{ multi_source: 1, single_source: 0 }}
        expandedGroups={new Set()}
        toggleGroup={toggleGroup}
        deleteNews={vi.fn()}
        onPageChange={vi.fn()}
        onRetry={vi.fn()}
      />,
    )

    const toggle = screen.getByRole('button', { name: '展开事件 12 的来源' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    toggle.focus()
    expect(toggle).toHaveFocus()
    fireEvent.click(toggle)
    expect(toggleGroup).toHaveBeenCalledWith(12)
  })
})
