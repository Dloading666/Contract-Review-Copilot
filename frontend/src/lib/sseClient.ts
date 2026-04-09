import type { SSEEvent } from '../types'

interface SSECallbacks {
  onEvent: (event: SSEEvent) => void
  onError?: (error: Error) => void
}

interface SSERequestOptions {
  headers?: Record<string, string>
}

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
          throw new Error(`HTTP ${res.status}`)
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
            emitEvent(currentEventType, dataLines)
            return
          }

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const rawLine of lines) {
            const line = rawLine.trim()
            if (!line) {
              emitEvent(currentEventType, dataLines)
              currentEventType = 'message'
              dataLines = []
              continue
            }

            if (line.startsWith('event:')) {
              currentEventType = line.slice(6).trim()
              continue
            }

            if (line.startsWith('data:')) {
              dataLines.push(line.slice(5).trim())
            }
          }
        }
      })
      .catch((error) => {
        if (aborted) return

        if (retryCount < maxRetries) {
          retryCount += 1
          retryTimer = setTimeout(connect, 2 ** retryCount * 1000)
          return
        }

        callbacks.onError?.(error)
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
