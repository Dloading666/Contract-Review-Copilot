import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE_PATH } from '../lib/apiPaths'
import { createSSEClient } from '../lib/sseClient'
import { writeSessionReportSnapshot } from '../lib/browserStorage'
import type {
  BreakpointQuestion,
  ClauseIssue,
  ExtractedEntity,
  ReviewPhase,
  RoutingDecision,
} from '../types'

interface UseStreamingReviewOptions {
  enabled?: boolean
  reviewMode?: 'light' | 'deep'
  token?: string | null
}

interface UseStreamingReviewReturn {
  phase: ReviewPhase
  reviewStage: 'idle' | 'initial' | 'deep' | 'complete'
  deepUpdateNotice: string | null
  canRetryDeepReview: boolean
  extractedEntities: ExtractedEntity | null
  routingDecision: RoutingDecision | null
  issues: ClauseIssue[]
  breakpointData: BreakpointQuestion | null
  reportParagraphs: string[]
  error: string | null
  confirm: () => void
  retryDeepReview: (payload?: {
    contractText?: string
    sessionId?: string
    issues?: ClauseIssue[]
  }) => void
  isStreaming: boolean
}

const API_BASE = API_BASE_PATH

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
  const { enabled = true, reviewMode = 'deep', token = null } = options
  const [phase, setPhase] = useState<ReviewPhase>('idle')
  const [reviewStage, setReviewStage] = useState<'idle' | 'initial' | 'deep' | 'complete'>('idle')
  const [deepUpdateNotice, setDeepUpdateNotice] = useState<string | null>(null)
  const [canRetryDeepReview, setCanRetryDeepReview] = useState(false)
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
  const contractTextRef = useRef(contractText)
  const issuesRef = useRef<ClauseIssue[]>([])
  const reviewModeRef = useRef<'light' | 'deep'>(reviewMode)
  const reviewStageRef = useRef(reviewStage)
  const startedRequestRef = useRef<string | null>(null)
  const reportFlushTimerRef = useRef<number | null>(null)
  const pendingReportParagraphsRef = useRef<string[]>([])

  useEffect(() => {
    sessionIdRef.current = sessionId
  }, [sessionId])

  useEffect(() => () => {
    if (reportFlushTimerRef.current !== null) {
      window.clearTimeout(reportFlushTimerRef.current)
    }
  }, [])

  useEffect(() => {
    tokenRef.current = token
  }, [token])

  useEffect(() => {
    contractTextRef.current = contractText
  }, [contractText])

  useEffect(() => {
    reviewModeRef.current = reviewMode
  }, [reviewMode])

  useEffect(() => {
    issuesRef.current = issues
  }, [issues])

  useEffect(() => {
    reviewStageRef.current = reviewStage
  }, [reviewStage])

  const flushReportSnapshot = useCallback((paragraphs: string[]) => {
    pendingReportParagraphsRef.current = paragraphs
    if (reportFlushTimerRef.current !== null) {
      return
    }

    reportFlushTimerRef.current = window.setTimeout(() => {
      reportFlushTimerRef.current = null
      writeSessionReportSnapshot(pendingReportParagraphsRef.current)
    }, 180)
  }, [])

  const resetStreamingState = useCallback(() => {
    setPhase('idle')
    setReviewStage('idle')
    setDeepUpdateNotice(null)
    setCanRetryDeepReview(false)
    setExtractedEntities(null)
    setRoutingDecision(null)
    setIssues([])
    setBreakpointData(null)
    pendingReportParagraphsRef.current = []
    if (reportFlushTimerRef.current !== null) {
      window.clearTimeout(reportFlushTimerRef.current)
      reportFlushTimerRef.current = null
    }
    writeSessionReportSnapshot([])
    setReportParagraphs([])
    setError(null)
    setIsStreaming(false)
  }, [])

  const handleSSEEvent = useCallback((eventType: string, data: unknown) => {
    try {
      switch (eventType) {
        case 'review_started':
          setPhase('started')
          setReviewStage('initial')
          setCanRetryDeepReview(false)
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
            setIssues((prev) => {
              const issue = payload.issue as ClauseIssue
              const duplicateIndex = prev.findIndex((item) => (
                item.clause === issue.clause && item.issue === issue.issue
              ))
              if (duplicateIndex < 0) return [...prev, issue]
              return prev.map((item, index) => (index === duplicateIndex ? { ...item, ...issue } : item))
            })
          }
          setPhase('logic_review')
          break
        }
        case 'initial_review_ready': {
          const payload = data as { issues?: ClauseIssue[]; summary?: string }
          if (payload.issues) {
            setIssues(payload.issues)
          }
          setReviewStage('initial')
          setDeepUpdateNotice(payload.summary ?? 'Initial review is ready. Deep analysis is still running.')
          setCanRetryDeepReview(false)
          setPhase('initial_ready')
          setIsStreaming(true)
          break
        }
        case 'deep_review_available': {
          const payload = data as { issues?: ClauseIssue[]; message?: string; summary?: string }
          if (payload.issues) {
            setIssues(payload.issues)
          }
          setReviewStage('initial')
          setDeepUpdateNotice(payload.message ?? payload.summary ?? 'Light scan is ready. You can continue to deep review.')
          setCanRetryDeepReview(true)
          setPhase('initial_ready')
          setIsStreaming(true)
          break
        }
        case 'deep_review_started': {
          const payload = data as { message?: string }
          setReviewStage('deep')
          setDeepUpdateNotice(payload.message ?? 'Deep analysis is running.')
          setCanRetryDeepReview(false)
          setPhase('deep_review')
          setIsStreaming(true)
          break
        }
        case 'deep_review_update': {
          const payload = data as { issues?: ClauseIssue[]; message?: string; summary?: string }
          if (payload.issues) {
            setIssues(payload.issues)
          }
          setReviewStage('deep')
          setDeepUpdateNotice(payload.message ?? payload.summary ?? 'Deep analysis updated the review results.')
          setCanRetryDeepReview(false)
          setPhase('deep_review')
          setIsStreaming(true)
          break
        }
        case 'deep_review_heartbeat': {
          const payload = data as { message?: string }
          if (payload.message) {
            setDeepUpdateNotice(payload.message)
          }
          setReviewStage('deep')
          setCanRetryDeepReview(false)
          setPhase('deep_review')
          setIsStreaming(true)
          break
        }
        case 'deep_review_complete': {
          const payload = data as { issues?: ClauseIssue[]; message?: string; summary?: string }
          if (payload.issues) {
            setIssues(payload.issues)
          }
          setReviewStage('complete')
          setDeepUpdateNotice(payload.message ?? payload.summary ?? 'Deep review completed.')
          setCanRetryDeepReview(false)
          break
        }
        case 'deep_review_failed': {
          const payload = data as { message?: string }
          setDeepUpdateNotice(payload.message ?? 'Deep analysis could not be completed. Initial results remain available.')
          setReviewStage('complete')
          setCanRetryDeepReview(true)
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
              flushReportSnapshot(next)
              return next
            })
          }
          setPhase('aggregation')
          break
        }
        case 'review_complete':
          flushReportSnapshot(pendingReportParagraphsRef.current)
          setPhase('complete')
          setReviewStage('complete')
          setIsStreaming(false)
          break
        case 'error': {
          const payload = data as { message?: string }
          if (issuesRef.current.length > 0 || reviewStageRef.current !== 'idle') {
            setDeepUpdateNotice(payload.message ?? '深度分析暂未补全，当前先展示已生成的审查结果。')
            setReviewStage('complete')
            setCanRetryDeepReview(true)
            setPhase('complete')
            setIsStreaming(false)
            break
          }
          setError(payload.message ?? 'Unknown error')
          setPhase('error')
          setIsStreaming(false)
          setReviewStage((current) => (current === 'idle' ? 'idle' : current))
          break
        }
      }
    } catch (streamError) {
      console.error('[useStreamingReview] handleEvent error:', eventType, streamError)
    }
  }, [flushReportSnapshot])

  const startStream = useCallback((url: string, body: object) => {
    clientRef.current?.abort()
    clientRef.current = createSSEClient(
      url,
      body,
      { headers: buildHeaders(tokenRef.current) },
      {
        onEvent: ({ event, data }) => handleSSEEvent(event, data),
        onError: (streamError) => {
          if (issuesRef.current.length > 0 || reviewStageRef.current !== 'idle') {
            setDeepUpdateNotice('深度分析连接已结束，当前先保留已生成的初步审查结果。')
            setReviewStage('complete')
            setCanRetryDeepReview(true)
            setPhase('complete')
            setIsStreaming(false)
            return
          }
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
    startStream(`${API_BASE}/review/confirm/${sessionIdRef.current}`, {
      confirmed: true,
      contract_text: contractTextRef.current,
      issues: issuesRef.current,
    })
  }, [startStream])

  const retryDeepReview = useCallback((payload?: {
    contractText?: string
    sessionId?: string
    issues?: ClauseIssue[]
  }) => {
    const nextContractText = payload?.contractText ?? contractTextRef.current
    const nextSessionId = payload?.sessionId ?? sessionIdRef.current
    const nextIssues = payload?.issues ?? issuesRef.current

    if (!nextContractText.trim()) return

    setError(null)
    setPhase('deep_review')
    setReviewStage('deep')
    setDeepUpdateNotice('正在继续补全深度分析与完整报告...')
    setCanRetryDeepReview(false)
    setIsStreaming(true)
    startStream(`${API_BASE}/review/deepen`, {
      contract_text: nextContractText,
      session_id: nextSessionId,
      issues: nextIssues,
    })
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

    const requestKey = `${sessionId}:${contractText}:${reviewMode}`
    if (startedRequestRef.current === requestKey) return
    startedRequestRef.current = requestKey

    resetStreamingState()
    setIsStreaming(true)
    setPhase('started')
    startStream(`${API_BASE}/review`, {
      contract_text: contractText,
      session_id: sessionId,
      review_mode: reviewModeRef.current,
    })

    return () => {
      clientRef.current?.abort()
      clientRef.current = null
    }
  }, [contractText, enabled, resetStreamingState, reviewMode, sessionId, startStream])

  return {
    phase,
    reviewStage,
    deepUpdateNotice,
    canRetryDeepReview,
    extractedEntities,
    routingDecision,
    issues,
    breakpointData,
    reportParagraphs,
    error,
    confirm,
    retryDeepReview,
    isStreaming,
  }
}
