import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSEClient } from './sseClient'

describe('createSSEClient', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('clears a scheduled retry when the client is aborted', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('network down'))
    globalThis.fetch = fetchMock as typeof fetch

    const client = createSSEClient(
      '/api/review',
      { contract_text: 'demo' },
      {},
      { onEvent: vi.fn(), onError: vi.fn() },
    )

    await vi.runAllTicks()
    expect(fetchMock).toHaveBeenCalledTimes(1)

    client.abort()
    vi.advanceTimersByTime(5_000)

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
