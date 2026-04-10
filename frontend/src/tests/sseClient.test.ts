import { waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSSEClient } from '../lib/sseClient'

function createMockStream(chunks: string[]) {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
  })
}

describe('createSSEClient', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('does not retry non-retriable client errors like 401', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 401 }))
    const onError = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    createSSEClient('/api/review', { contract_text: 'demo' }, {}, { onEvent: vi.fn(), onError })

    await Promise.resolve()
    await vi.runAllTimersAsync()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError.mock.calls[0]?.[0]).toBeInstanceOf(Error)
    vi.useRealTimers()
  })

  it('flushes the last buffered event when the stream ends without a blank separator', async () => {
    const onEvent = vi.fn()
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        createMockStream([
          'event: final_report\n',
          'data: {"paragraph":"tail payload"}',
        ]),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    createSSEClient('/api/review', { contract_text: 'demo' }, {}, { onEvent })

    await waitFor(() => {
      expect(onEvent).toHaveBeenCalledWith({
        event: 'final_report',
        data: { paragraph: 'tail payload' },
      })
    })
  })
})
