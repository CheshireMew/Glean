import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import ScraperCard from './ScraperCard'

vi.mock('@ant-design/icons', () => ({
  PlayCircleOutlined: () => null,
  PauseCircleOutlined: () => null,
}))

vi.mock('antd', () => {
  const Select = ({ value, onChange, disabled, children }) => (
    <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>{children}</select>
  )
  Select.Option = ({ value, children }) => <option value={value}>{children}</option>
  return {
    Card: ({ title, extra, children }) => <section><h2>{title}</h2>{extra}{children}</section>,
    Col: ({ children }) => <div>{children}</div>,
    Select,
    Button: ({ children, onClick, disabled }) => <button type="button" onClick={onClick} disabled={disabled}>{children}</button>,
    Tag: ({ children }) => <span>{children}</span>,
  }
})

describe('ScraperCard', () => {
  it('restores the authoritative value when a configuration save fails', async () => {
    const onConfigChange = vi.fn().mockResolvedValue(false)
    render(
      <ScraperCard
        name="panews"
        displayName="PANews"
        contentKind="news"
        status={{ status: 'idle', limit: 20, interval: 30, logs: [] }}
        onRun={vi.fn()}
        onCancel={vi.fn()}
        onConfigChange={onConfigChange}
      />,
    )

    const [limitSelect] = screen.getAllByRole('combobox')
    fireEvent.change(limitSelect, { target: { value: '30' } })
    expect(onConfigChange).toHaveBeenCalledWith('panews', { limit: '30' })
    await waitFor(() => expect(limitSelect).toHaveValue('20'))
  })
})
