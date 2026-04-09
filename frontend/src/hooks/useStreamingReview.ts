import { useCallback, useEffect, useRef, useState } from 'react'
import { createSSEClient } from '../lib/sseClient'
import type {
  BreakpointQuestion,
  ClauseIssue,
  ExtractedEntity,
  ReviewPhase,
  RoutingDecision,
} from '../types'

interface UseStreamingReviewOptions {
  enabled?: boolean
  token?: string | null
}

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

function buildHeaders(token?: string | null) {
  const headers: Record<string, string> = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  return headers
}

export function useStreamingReview(
  sessionId: string,
  contractText: string,
  options: UseStreamingReviewOptions = {},
): UseStreamingReviewReturn {
  const { enabled = true, token = null } = options
  const [phase, setPhase] = useState<ReviewPhase>('idle')
  const [extractedEntities, setExtractedEntities] = useState<ExtractedEntity | null>(null)
  const [routingDecision, setRoutingDecision] = useState<RoutingDecision | null>(null)
  const [issues, setIssues] = useState<ClauseIssue[]>([])
  const [breakpointData, setBreakpointData] = useState<BreakpointQuestion | null>(null)
  const [reportParagraphs, setReportParagraphs] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const clientRef = useRef<{ abort: () => void } | null>(null)
  const sessionIdRef = useRef(sessionId)
  const tokenRef = useRef(token)
  const startedRequestRef = useRef<string | null>(null)

  useEffect(() => {
    sessionIdRef.current = sessionId
  }, [sessionId])

  useEffect(() => {
    tokenRef.current = token
  }, [token])

  const resetStreamingState = useCallback(() => {
    setPhase('idle')
    setExtractedEntities(null)
    setRoutingDecision(null)
    setIssues([])
    setBreakpointData(null)
    setReportParagraphs([])
    setError(null)
    setIsStreaming(false)
  }, [])

  const handleSSEEvent = useCallback((eventType: string, data: unknown) => {
    try {
      switch (eventType) {
        case 'review_started':
          setPhase('started')
          setIsStreaming(true)
          break
        case 'entity_extraction': {
          const payload = data as { entities?: ExtractedEntity }
          setExtractedEntities(payload.entities ?? null)
          setPhase('extraction')
          break
        }
        case 'routing': {
          const payload = data as { routing?: RoutingDecision }
          setRoutingDecision(payload.routing ?? null)
          setPhase('routing')
          break
        }
        case 'logic_review': {
          const payload = data as { issue?: ClauseIssue }
          if (payload.issue) {
            setIssues((prev) => [...prev, payload.issue as ClauseIssue])
          }
          setPhase('logic_review')
          break
        }
        case 'breakpoint': {
          const payload = data as { breakpoint?: BreakpointQuestion; issues?: ClauseIssue[] }
          setBreakpointData(payload.breakpoint ?? null)
          if (payload.issues) {
            setIssues(payload.issues)
          }
          setPhase('breakpoint')
          setIsStreaming(false)
          break
        }
        case 'stream_resume':
          setIsStreaming(true)
          break
        case 'final_report': {
          const payload = data as { paragraph?: string }
          if (payload.paragraph) {
            setReportParagraphs((prev) => {
              const next = [...prev, payload.paragraph as string]
              try {
                sessionStorage.setItem('lastReport', next.join('\n\n'))
              } catch {
                // Ignore storage errors in private browsing or tests.
              }
              return next
            })
          }
          setPhase('aggregation')
          break
        }
        case 'review_complete':
          setPhase('complete')
          setIsStreaming(false)
          break
        case 'error': {
          const payload = data as { message?: string }
          setError(payload.message ?? 'Unknown error')
          setPhase('error')
          setIsStreaming(false)
          break
        }
      }
    } catch (streamError) {
      console.error('[useStreamingReview] handleEvent error:', eventType, streamError)
    }
  }, [])

  const startStream = useCallback((url: string, body: object) => {
    clientRef.current?.abort()
    clientRef.current = createSSEClient(
      url,
      body,
      { headers: buildHeaders(tokenRef.current) },
      {
        onEvent: ({ event, data }) => handleSSEEvent(event, data),
        onError: (streamError) => {
          setError(streamError.message)
          setPhase('error')
          setIsStreaming(false)
        },
      },
    )
  }, [handleSSEEvent])

  const confirm = useCallback(() => {
    setError(null)
    setBreakpointData(null)
    setPhase('aggregation')
    setIsStreaming(true)
    startStream(`${API_BASE}/review/confirm/${sessionIdRef.current}`, { confirmed: true })
  }, [startStream])

  useEffect(() => {
    if (!contractText) {
      clientRef.current?.abort()
      clientRef.current = null
      startedRequestRef.current = null
      resetStreamingState()
      return
    }

    if (!enabled) return

    const requestKey = `${sessionId}:${contractText}`
    if (startedRequestRef.current === requestKey) return
    startedRequestRef.current = requestKey

    resetStreamingState()
    setIsStreaming(true)
    setPhase('started')
    startStream(`${API_BASE}/review`, {
      contract_text: contractText,
      session_id: sessionId,
    })

    return () => {
      clientRef.current?.abort()
      clientRef.current = null
    }
  }, [contractText, enabled, resetStreamingState, sessionId, startStream])

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
