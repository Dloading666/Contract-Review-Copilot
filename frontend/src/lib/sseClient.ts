import { getGatewayErrorMessage } from './apiClient'
import type { SSEEvent } from '../types'

interface SSECallbacks {
  onEvent: (event: SSEEvent) => void
  onError?: (error: Error) => void
}

interface SSERequestOptions {
  headers?: Record<string, string>
}

class NonRetriableSSEError extends Error {}

/**
 * SSE client using fetch API because the backend streams from POST endpoints.
 */
export function createSSEClient(
  url: string,
  body: object,
  requestOptions: SSERequestOptions,
  callbacks: SSECallbacks,
) {
  let aborted = false
  let retryCount = 0
  const maxRetries = 2
  let controller: AbortController | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null

  function emitEvent(eventType: string, dataLines: string[]) {
    if (dataLines.length === 0) return

    try {
      callbacks.onEvent({
        event: eventType,
        data: JSON.parse(dataLines.join('')),
      })
    } catch {
      // Ignore malformed chunks so one bad event does not kill the stream.
    }
  }

  function processBufferedText(
    chunk: string,
    currentEventType: string,
    dataLines: string[],
  ): { buffer: string; currentEventType: string; dataLines: string[] } {
    const lines = chunk.split('\n')
    const remainder = lines.pop() ?? ''
    let nextEventType = currentEventType
    let nextDataLines = dataLines

    for (const rawLine of lines) {
      const line = rawLine.trim()
      if (!line) {
        emitEvent(nextEventType, nextDataLines)
        nextEventType = 'message'
        nextDataLines = []
        continue
      }

      if (line.startsWith('event:')) {
        nextEventType = line.slice(6).trim()
        continue
      }

      if (line.startsWith('data:')) {
        nextDataLines = [...nextDataLines, line.slice(5).trim()]
      }
    }

    return {
      buffer: remainder,
      currentEventType: nextEventType,
      dataLines: nextDataLines,
    }
  }

  function connect() {
    if (aborted) return
    retryTimer = null

    controller = new AbortController()
    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(requestOptions.headers ?? {}),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          const text = await res.text().catch(() => '')
          const errorMessage = getGatewayErrorMessage(res.status, text)
          if (res.status === 401 || res.status === 403 || res.status === 404) {
            throw new NonRetriableSSEError(errorMessage)
          }
          throw new Error(errorMessage)
        }

        const reader = res.body?.getReader()
        if (!reader) {
          throw new Error('Response body is not readable')
        }

        const decoder = new TextDecoder()
        let buffer = ''
        let currentEventType = 'message'
        let dataLines: string[] = []

        while (!aborted) {
          const { done, value } = await reader.read()
          if (done) {
            const flushed = processBufferedText(buffer + decoder.decode(), currentEventType, dataLines)
            currentEventType = flushed.currentEventType
            dataLines = flushed.dataLines
            buffer = flushed.buffer
            if (buffer.trim().startsWith('data:')) {
              dataLines = [...dataLines, buffer.trim().slice(5).trim()]
            } else if (buffer.trim().startsWith('event:')) {
              currentEventType = buffer.trim().slice(6).trim()
            }
            emitEvent(currentEventType, dataLines)
            return
          }

          const processed = processBufferedText(
            buffer + decoder.decode(value, { stream: true }),
            currentEventType,
            dataLines,
          )
          buffer = processed.buffer
          currentEventType = processed.currentEventType
          dataLines = processed.dataLines
        }
      })
      .catch((error) => {
        if (aborted) return

        const normalizedError = error instanceof Error && /failed to fetch/i.test(error.message)
          ? new Error('网络请求没有到达服务端，请检查网络或站点网关设置后重试')
          : error

        if (!(normalizedError instanceof NonRetriableSSEError) && retryCount < maxRetries) {
          retryCount += 1
          retryTimer = setTimeout(connect, 2 ** retryCount * 1000)
          return
        }

        callbacks.onError?.(normalizedError)
      })
  }

  connect()

  return {
    abort: () => {
      aborted = true
      if (retryTimer) {
        clearTimeout(retryTimer)
        retryTimer = null
      }
      controller?.abort()
    },
  }
}
