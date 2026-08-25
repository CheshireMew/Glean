import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  getAiProviderConfig,
  getAutomationConfig,
  getDeliverySchedule,
  getSystemTimezone,
  getTelegramConfig,
  setAiProviderConfig,
  setSystemSettings,
  setTelegramConfig,
} from '../../../api/config'
import { useAiProviderSettings } from './useAiProviderSettings'
import { useSystemBasicsSettings } from './useSystemBasicsSettings'
import { useTelegramSettings } from './useTelegramSettings'
import { testAiConnection, testTelegramPush } from '../../../api/pipeline'

vi.mock('../../../api/config', () => ({
  getAiProviderConfig: vi.fn(),
  getAutomationConfig: vi.fn(),
  getDeliverySchedule: vi.fn(),
  getSystemTimezone: vi.fn(),
  getTelegramConfig: vi.fn(),
  setAiProviderConfig: vi.fn(),
  setSystemSettings: vi.fn(),
  setTelegramConfig: vi.fn(),
}))

vi.mock('../../../api/pipeline', () => ({
  testAiConnection: vi.fn(),
  testTelegramPush: vi.fn(),
}))

vi.mock('antd', () => ({
  message: { success: vi.fn(), error: vi.fn() },
}))

describe('settings truth boundaries', () => {
  beforeEach(() => vi.clearAllMocks())

  it('does not save system defaults when any current setting fails to load', async () => {
    getSystemTimezone.mockResolvedValue({ data: { timezone: 'UTC' } })
    getAutomationConfig.mockRejectedValue(new Error('automation unavailable'))
    getDeliverySchedule.mockResolvedValue({ data: { news_time: '19:00', article_time: '20:00' } })
    const { result } = renderHook(() => useSystemBasicsSettings())

    await waitFor(() => expect(result.current.loadState.loading).toBe(false))
    expect(result.current.loadState.loaded).toBe(false)
    expect(result.current.loadState.error).toBeTruthy()
    await act(async () => result.current.save())
    expect(setSystemSettings).not.toHaveBeenCalled()
  })

  it('loads the authoritative system snapshot before enabling an atomic save', async () => {
    getSystemTimezone.mockResolvedValue({ data: { timezone: 'UTC' } })
    getAutomationConfig.mockResolvedValue({
      data: {
        news: {
          cluster_hours: 2,
          cluster_window_hours: 2,
          filter_hours: 6,
          ai_scoring_hours: 10,
          push_hours: 12,
        },
        article: {
          cluster_hours: 168,
          cluster_window_hours: 72,
          filter_hours: 72,
          ai_scoring_hours: 168,
          push_hours: 72,
        },
        runtime: {
          enabled: true,
          start_time: '08:00',
          end_time: '23:59',
          interval_minutes: 60,
          review_batch_size: 50,
          enrichment_batch_size: 25,
          max_review_batches_per_cycle: 7,
          backlog_retry_seconds: 15,
          scraper_concurrency: 2,
          maintenance_interval_hours: 24,
          operational_retention_days: 30,
          content_retention_days: 365,
        },
      },
    })
    getDeliverySchedule.mockResolvedValue({ data: { news_time: '19:00', article_time: '20:00' } })
    setSystemSettings.mockResolvedValue({ data: {} })
    const { result } = renderHook(() => useSystemBasicsSettings())

    await waitFor(() => expect(result.current.loadState.loaded).toBe(true))
    expect(result.current.timezone).toBe('UTC')
    expect(result.current.runtimeConfig.max_review_batches_per_cycle).toBe(7)
    await act(async () => result.current.save())
    expect(setSystemSettings).toHaveBeenCalledWith(expect.objectContaining({
      timezone: 'UTC',
      automation: expect.objectContaining({
        runtime: expect.objectContaining({ backlog_retry_seconds: 15 }),
      }),
    }))
  })

  it('blocks Telegram and AI writes when their current server values are unknown', async () => {
    getTelegramConfig.mockRejectedValue(new Error('telegram unavailable'))
    getAiProviderConfig.mockRejectedValue(new Error('ai unavailable'))
    const telegram = renderHook(() => useTelegramSettings())
    const ai = renderHook(() => useAiProviderSettings())

    await waitFor(() => expect(telegram.result.current.loadState.loading).toBe(false))
    await waitFor(() => expect(ai.result.current.loadState.loading).toBe(false))
    await act(async () => telegram.result.current.save())
    await act(async () => ai.result.current.save())

    expect(telegram.result.current.loadState.loaded).toBe(false)
    expect(ai.result.current.loadState.loaded).toBe(false)
    expect(setTelegramConfig).not.toHaveBeenCalled()
    expect(setAiProviderConfig).not.toHaveBeenCalled()
  })

  it('tests the current drafts without saving them', async () => {
    getTelegramConfig.mockResolvedValue({ data: { bot_token: 'saved-token', chat_id: 'saved-chat', enabled: false } })
    getAiProviderConfig.mockResolvedValue({
      data: {
        providers: [{ name: 'primary', api_key: 'saved-key', base_url: 'https://saved.test/v1', model: 'saved-model' }],
        analysis_concurrency: 3,
        enrichment_concurrency: 2,
        throttle_seconds: 0,
      },
    })
    testTelegramPush.mockResolvedValue({ data: {} })
    testAiConnection.mockResolvedValue({ data: { ok: true } })

    const telegram = renderHook(() => useTelegramSettings())
    const ai = renderHook(() => useAiProviderSettings())
    await waitFor(() => expect(telegram.result.current.loadState.loaded).toBe(true))
    await waitFor(() => expect(ai.result.current.loadState.loaded).toBe(true))

    act(() => {
      telegram.result.current.setConfig((previous) => ({ ...previous, bot_token: 'draft-token', chat_id: 'draft-chat' }))
      ai.result.current.updateProvider(0, 'model', 'draft-model')
    })
    expect(telegram.result.current.dirty).toBe(true)
    expect(ai.result.current.dirty).toBe(true)

    await act(async () => telegram.result.current.test())
    await act(async () => ai.result.current.test())

    expect(testTelegramPush).toHaveBeenCalledWith({ bot_token: 'draft-token', chat_id: 'draft-chat', enabled: false })
    expect(testAiConnection).toHaveBeenCalledWith(expect.objectContaining({
      providers: [expect.objectContaining({ model: 'draft-model' })],
    }))
    expect(setTelegramConfig).not.toHaveBeenCalled()
    expect(setAiProviderConfig).not.toHaveBeenCalled()
  })
})
