import type { SSEEvent } from '../types'

/**
 * SSE client using fetch API (not EventSource, because we need POST).
 * Handles chunk boundaries and SSE protocol parsing.
 */
export function createSSEClient(
  url: string,
  body: object,
  callbacks: {
    onEvent: (event: SSEEvent) => void
    onError?: (error: Error) => void
  }
) {
  let aborted = false
  let retryCount = 0
  const MAX_RETRIES = 2

  let lastEventType = 'message'

  function connect(): AbortController | null {
    if (aborted) return null

    const controller = new AbortController()
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const reader = res.body!.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        function read() {
          reader.read().then(({ done, value }) => {
            if (done || aborted) return
            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() ?? ''

            let eventType = lastEventType
            let dataLines: string[] = []

            for (const raw of lines) {
              const line = raw.trim()
              if (!line) {
                // Empty line = end of event
                if (dataLines.length > 0) {
                  const jsonStr = dataLines.join('')
                  try {
                    const data = JSON.parse(jsonStr)
                    callbacks.onEvent({ event: eventType, data })
                  } catch {
                    // ignore
                  }
                  dataLines = []
                }
                continue
              }
              if (line.startsWith('event:')) {
                eventType = line.slice(6).trim()
                lastEventType = eventType
              } else if (line.startsWith('data:')) {
                dataLines.push(line.slice(5).trim())
              }
            }

            read()
          })
        }

        read()
      })
      .catch((err) => {
        if (aborted) return
        if (retryCount < MAX_RETRIES) {
          retryCount++
          setTimeout(connect, Math.pow(2, retryCount) * 1000)
        } else {
          callbacks.onError?.(err)
        }
      })

    return controller
  }

  const controller = connect()

  return {
    abort: () => {
      aborted = true
      if (controller) controller.abort()
    },
  }
}
