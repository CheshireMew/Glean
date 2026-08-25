import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { NEWSFEED_TABS } from '../../contracts/content'
import NewsFeedTabs from './NewsFeedTabs'

describe('NewsFeedTabs', () => {
  it('exposes real tab semantics and changes the selected feed', () => {
    const onChange = vi.fn()
    render(<NewsFeedTabs activeTab={NEWSFEED_TABS[0].key} onChange={onChange} />)

    const tabs = screen.getAllByRole('tab')
    expect(screen.getByRole('tablist', { name: '公开内容栏目' })).toBeInTheDocument()
    expect(tabs).toHaveLength(NEWSFEED_TABS.length)
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')

    fireEvent.click(tabs[1])
    expect(onChange).toHaveBeenCalledWith(NEWSFEED_TABS[1].key)
  })

  it('supports roving focus with arrow, home and end keys', () => {
    const onChange = vi.fn()
    render(<NewsFeedTabs activeTab={NEWSFEED_TABS[0].key} onChange={onChange} />)
    const tabs = screen.getAllByRole('tab')

    tabs[0].focus()
    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' })
    expect(tabs[1]).toHaveFocus()
    expect(onChange).toHaveBeenLastCalledWith(NEWSFEED_TABS[1].key)

    fireEvent.keyDown(tabs[1], { key: 'End' })
    expect(tabs.at(-1)).toHaveFocus()
    fireEvent.keyDown(tabs.at(-1), { key: 'Home' })
    expect(tabs[0]).toHaveFocus()
  })
})
