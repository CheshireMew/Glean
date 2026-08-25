import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Modal } from 'antd'
import { listDeliveryOperations, sendSelectedContent, triggerDailyPush } from '../../api/pipeline'
import { useExportDelivery } from './useExportDelivery'

vi.mock('../../api/pipeline', () => ({
  listDeliveryOperations: vi.fn(),
  retryDelivery: vi.fn(),
  sendSelectedContent: vi.fn(),
  triggerDailyPush: vi.fn(),
}))

vi.mock('../../api/resources', () => ({
  API_RESOURCE: { DELIVERY_OPERATIONS: 'delivery-operations' },
  subscribeResource: vi.fn(() => vi.fn()),
}))

vi.mock('antd', () => ({
  Modal: { confirm: vi.fn() },
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), loading: vi.fn() },
}))

describe('useExportDelivery', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listDeliveryOperations.mockResolvedValue({ data: [] })
    sendSelectedContent.mockResolvedValue({ data: { status: 'sent', sent_count: 1 } })
    triggerDailyPush.mockResolvedValue({ data: { status: 'success', count: 1 } })
  })

  it('requires confirmation before selected content or a daily report crosses the delivery boundary', async () => {
    const item = {
      outputKey: 'selected:1',
      outputRef: { scope: 'selected', id: 1 },
      title: '待发送内容',
    }
    const { result } = renderHook(() => useExportDelivery('news', [item], ['selected:1']))
    await waitFor(() => expect(listDeliveryOperations).toHaveBeenCalled())

    act(() => result.current.sendToTelegram())
    expect(sendSelectedContent).not.toHaveBeenCalled()
    const manualConfirmation = Modal.confirm.mock.calls[0][0]
    expect(manualConfirmation.title).toContain('1 条内容')
    expect(manualConfirmation.content).toContain('待发送内容')
    await act(async () => manualConfirmation.onOk())
    expect(sendSelectedContent).toHaveBeenCalledWith(
      [{ scope: 'selected', id: 1 }],
      expect.stringMatching(/^manual-entry:/),
    )

    act(() => result.current.triggerDailyDelivery())
    expect(triggerDailyPush).not.toHaveBeenCalled()
    const dailyConfirmation = Modal.confirm.mock.calls[1][0]
    expect(dailyConfirmation.title).toContain('快讯日报')
    await act(async () => dailyConfirmation.onOk())
    expect(triggerDailyPush).toHaveBeenCalledWith('news', expect.stringMatching(/^manual-daily-news:/))
  })
})
