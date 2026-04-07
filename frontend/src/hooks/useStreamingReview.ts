import { useState, useCallback, useRef, useEffect } from 'react'
import type { ReviewPhase, ExtractedEntity, RoutingDecision, ClauseIssue, BreakpointQuestion } from '../types'

interface UseStreamingReviewReturn {
  phase: ReviewPhase
  extractedEntities: ExtractedEntity | null
  routingDecision: RoutingDecision | null
  issues: ClauseIssue[]
  breakpointData: BreakpointQuestion | null
  reportParagraphs: string[]
  error: string | null
  confirm: () => void
  isStreaming: boolean
}

const API_BASE = '/api'

export function useStreamingReview(
  sessionId: string,
  contractText: string
): UseStreamingReviewReturn {
  const [phase, setPhase] = useState<ReviewPhase>('idle')
  const [extractedEntities, setExtractedEntities] = useState<ExtractedEntity | null>(null)
  const [routingDecision, setRoutingDecision] = useState<RoutingDecision | null>(null)
  const [issues, setIssues] = useState<ClauseIssue[]>([])
  const [breakpointData, setBreakpointData] = useState<BreakpointQuestion | null>(null)
  const [reportParagraphs, setReportParagraphs] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)
  const sessionIdRef = useRef(sessionId)

  useEffect(() => {
    sessionIdRef.current = sessionId
  }, [sessionId])

  const confirm = useCallback(() => {
    // Will POST /api/review/confirm/{sessionId} to resume stream
    fetch(`${API_BASE}/review/confirm/${sessionIdRef.current}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmed: true }),
    }).catch(console.error)
  }, [])

  useEffect(() => {
    if (!contractText) return

    const controller = new AbortController()
    abortControllerRef.current = controller
    setIsStreaming(true)
    setPhase('started')
    setError(null)

    let buffer = ''

    fetch(`${API_BASE}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contract_text: contractText, session_id: sessionId }),
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const reader = res.body!.getReader()
        const decoder = new TextDecoder()

        function read() {
          reader.read().then(({ done, value }) => {
            if (done) return
            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() ?? ''

            let currentEventType = 'message'
            for (const rawLine of lines) {
              const line = rawLine.trim()
              if (!line) continue
              if (line.startsWith('event:')) {
                currentEventType = line.slice(6).trim()
                continue
              }
              if (line.startsWith('data:')) {
                const jsonStr = line.slice(5).trim()
                try {
                  const data = JSON.parse(jsonStr)
                  handleEvent(currentEventType, data)
                } catch {
                  // ignore parse errors for now
                }
              }
            }
            read()
          })
        }

        read()
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(err.message)
        setIsStreaming(false)
        setPhase('error')
      })

    function handleEvent(eventType: string, data: unknown) {
      switch (eventType) {
        case 'review_started':
          setPhase('started')
          break
        case 'entity_extraction':
          setExtractedEntities(data as ExtractedEntity)
          setPhase('extraction')
          break
        case 'routing':
          setRoutingDecision(data as RoutingDecision)
          setPhase('routing')
          break
        case 'logic_review':
          setIssues((prev) => [...prev, data as ClauseIssue])
          setPhase('logic_review')
          break
        case 'breakpoint':
          setBreakpointData(data as BreakpointQuestion)
          setPhase('breakpoint')
          setIsStreaming(false)
          break
        case 'stream_resume':
          setIsStreaming(true)
          break
        case 'final_report':
          setReportParagraphs((prev) => [...prev, (data as { paragraph: string }).paragraph])
          setPhase('aggregation')
          break
        case 'review_complete':
          setPhase('complete')
          setIsStreaming(false)
          break
        case 'error':
          setError((data as { message: string }).message)
          setPhase('error')
          setIsStreaming(false)
          break
      }
    }

    return () => {
      controller.abort()
    }
  }, [contractText, sessionId])

  return {
    phase,
    extractedEntities,
    routingDecision,
    issues,
    breakpointData,
    reportParagraphs,
    error,
    confirm,
    isStreaming,
  }
}
