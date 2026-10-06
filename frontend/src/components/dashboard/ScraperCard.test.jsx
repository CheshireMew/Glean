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
  it('shows missing configuration and prevents an invalid run', () => {
    const onRun = vi.fn()
    const props = {
      name: 'blockbeats', displayName: '律动', contentKind: 'news',
      status: { status: 'idle', interval: 60, limit: 5, logs: [], configuration_error: '请配置律动 API Key' },
      onRun, onCancel: vi.fn(), onConfigChange: vi.fn(),
    }
    const { rerender } = render(<ScraperCard {...props} />)
    expect(screen.getByText('待配置')).toBeInTheDocument()
    expect(screen.getByText('请配置律动 API Key')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '运行' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '运行' }))
    expect(onRun).not.toHaveBeenCalled()
    rerender(<ScraperCard {...props} status={{ ...props.status, configuration_error: null }} />)
    expect(screen.getByText('就绪')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '运行' })).toBeEnabled()
  })

  it('shows the cooldown and prevents manual requests during it', () => {
    const onRun = vi.fn()
    render(<ScraperCard name="odaily" displayName="Odaily" contentKind="news"
      status={{ status: 'error', interval: 60, limit: 5, cooldown_until: Date.now() / 1000 + 1800, cooldown_reason: '网站要求稍后再试', logs: [] }}
      onRun={onRun} onCancel={vi.fn()} onConfigChange={vi.fn()} />)
    expect(screen.getByText('冷却中')).toBeInTheDocument()
    expect(screen.getByText('网站要求稍后再试')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '运行' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '运行' }))
    expect(onRun).not.toHaveBeenCalled()
  })

  it('keeps manual mode after the server returns a null interval', async () => {
    const props = {
      name: 'odaily', displayName: 'Odaily', contentKind: 'news',
      status: { status: 'idle', limit: 5, interval: 60, logs: [] },
      onRun: vi.fn(), onCancel: vi.fn(), onConfigChange: vi.fn().mockResolvedValue(true),
    }
    const { rerender } = render(<ScraperCard {...props} />)
    const intervalSelect = screen.getAllByRole('combobox')[1]
    fireEvent.change(intervalSelect, { target: { value: 'manual' } })
    await waitFor(() => expect(props.onConfigChange).toHaveBeenCalledWith('odaily', { interval: 'manual' }))
    rerender(<ScraperCard {...props} status={{ ...props.status, interval: null }} />)
    await waitFor(() => expect(intervalSelect).toHaveValue('manual'))
    expect(screen.getByText('仅手动')).toBeInTheDocument()
  })

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
