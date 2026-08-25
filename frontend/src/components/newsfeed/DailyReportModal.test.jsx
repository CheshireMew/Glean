import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import DailyReportModal from './DailyReportModal'

const report = {
  type: 'news',
  date: '2026-08-11',
  created_at: '2026-08-11T10:00:00Z',
  items: [{
    id: 7,
    position: 1,
    section: '模型',
    title: '新的推理模型发布',
    source_site: 'Example',
    source_url: 'https://example.com/model',
    source_count: 2,
    enriched_summary: '这是结构化摘要。',
    enriched_impact: '推理成本降低。',
    enriched_background: '来自持续迭代。',
  }],
}

describe('DailyReportModal', () => {
  it('renders structured report details in an accessible dialog', () => {
    render(<DailyReportModal report={report} onClose={() => {}} />)

    expect(screen.getByRole('dialog', { name: '2026-08-11 精选快讯合集' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '新的推理模型发布' })).toHaveAttribute('href', 'https://example.com/model')
    expect(screen.getByText('2 个来源交叉印证')).toBeInTheDocument()
    expect(screen.getByText(/推理成本降低/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '关闭日报' })).toHaveFocus()
  })

  it('closes with Escape', () => {
    const onClose = vi.fn()
    render(<DailyReportModal report={report} onClose={onClose} />)

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
