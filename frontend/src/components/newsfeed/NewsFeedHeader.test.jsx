import React, { useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import NewsFeedHeader from './NewsFeedHeader'

function HeaderHarness() {
  const [open, setOpen] = useState(false)
  return (
    <NewsFeedHeader
      searchQuery=""
      onSearchChange={vi.fn()}
      menuOpen={open}
      onToggleMenu={() => setOpen((value) => !value)}
      darkMode={false}
      onToggleDarkMode={vi.fn()}
      links={{
        home: 'https://example.test',
        telegram: 'https://t.me/example',
        x: 'https://x.com/example',
      }}
    />
  )
}

describe('NewsFeedHeader', () => {
  it('moves focus through the related-links menu and restores it on escape', async () => {
    render(<HeaderHarness />)
    const button = screen.getByRole('button', { name: '打开相关链接' })
    fireEvent.keyDown(button, { key: 'ArrowDown' })

    const items = await screen.findAllByRole('menuitem')
    await waitFor(() => expect(items[0]).toHaveFocus())
    fireEvent.keyDown(items[0], { key: 'ArrowDown' })
    expect(items[1]).toHaveFocus()
    fireEvent.keyDown(items[1], { key: 'End' })
    expect(items.at(-1)).toHaveFocus()
    fireEvent.keyDown(items.at(-1), { key: 'Escape' })
    await waitFor(() => expect(button).toHaveFocus())
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })

  it('removes the related-links control when no links are configured', () => {
    render(
      <NewsFeedHeader
        searchQuery=""
        onSearchChange={vi.fn()}
        menuOpen={false}
        onToggleMenu={vi.fn()}
        darkMode={false}
        onToggleDarkMode={vi.fn()}
        links={{}}
      />,
    )

    expect(screen.queryByRole('button', { name: '打开相关链接' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'AI News' })).toBeInTheDocument()
  })
})
