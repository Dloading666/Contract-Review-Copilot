import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useStreamingReview } from '../hooks/useStreamingReview'
import type { ClauseIssue } from '../types'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

function createMockStream(chunks: string[]) {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      let index = 0

      function pushChunk() {
        if (index >= chunks.length) {
          controller.close()
          return
        }

        controller.enqueue(encoder.encode(chunks[index]))
        index += 1
        setTimeout(pushChunk, 10)
      }

      pushChunk()
    },
  })
}

describe('useStreamingReview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
  })

  it('parses entity extraction payloads', async () => {
    const entityData = {
      contract_type: 'rental_contract',
      parties: { lessor: 'Alice', lessee: 'Bob' },
      rent: { monthly: 8500, currency: 'CNY', payment_cycle: 'monthly' },
      deposit: { amount: 17000, conditions: 'refund after move out' },
      property: { address: 'Beijing', area: '45' },
      lease_term: { start: '2026-05-01', end: '2027-04-30', duration_text: '12 months' },
      penalty_clause: 'two months rent',
    }

    const mockResponse = new Response(createMockStream([
      `event: entity_extraction\ndata: ${JSON.stringify({ entities: entityData })}\n\n`,
    ]))

    mockFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useStreamingReview('test-session', 'contract text'))

    await waitFor(() => {
      expect(result.current.extractedEntities).toEqual(entityData)
    })
  })

  it('accumulates logic review issues', async () => {
    const issues = [
      { clause: 'Penalty clause', issue: 'Too high', level: 'high', risk_level: 3, legal_reference: 'Art. 585' },
      { clause: 'Late fee clause', issue: 'Above the cap', level: 'critical', risk_level: 5, legal_reference: 'Art. 585' },
    ]

    const mockResponse = new Response(createMockStream(
      issues.map((issue) => `event: logic_review\ndata: ${JSON.stringify({ issue })}\n\n`),
    ))

    mockFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useStreamingReview('test-session', 'contract text'))

    await waitFor(() => {
      expect(result.current.issues).toHaveLength(2)
      expect(result.current.issues[0].clause).toBe('Penalty clause')
    })
  })

  it('sets breakpoint data and pauses streaming', async () => {
    const breakpointData = {
      needs_review: true,
      question: 'Continue?',
      issues_count: 3,
      critical_count: 1,
      high_count: 1,
      medium_count: 1,
    }

    const mockResponse = new Response(createMockStream([
      `event: breakpoint\ndata: ${JSON.stringify({ breakpoint: breakpointData, issues: [] })}\n\n`,
    ]))

    mockFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useStreamingReview('test-session', 'contract text'))

    await waitFor(() => {
      expect(result.current.phase).toBe('breakpoint')
      expect(result.current.breakpointData).toEqual(breakpointData)
      expect(result.current.isStreaming).toBe(false)
    })
  })

  it('resumes aggregation after confirm and completes the report stream', async () => {
    const breakpointData = {
      needs_review: true,
      question: 'Continue?',
      issues_count: 1,
      critical_count: 0,
      high_count: 1,
      medium_count: 0,
    }

    mockFetch
      .mockResolvedValueOnce(new Response(createMockStream([
        `event: breakpoint\ndata: ${JSON.stringify({ breakpoint: breakpointData, issues: [] })}\n\n`,
      ])))
      .mockResolvedValueOnce(new Response(createMockStream([
        'event: stream_resume\ndata: {"session_id":"test-session"}\n\n',
        `event: final_report\ndata: ${JSON.stringify({ paragraph: 'Report paragraph one' })}\n\n`,
        'event: review_complete\ndata: {"session_id":"test-session"}\n\n',
      ])))

    const { result } = renderHook(() => useStreamingReview('test-session', 'contract text'))

    await waitFor(() => {
      expect(result.current.phase).toBe('breakpoint')
    })

    act(() => {
      result.current.confirm()
    })

    await waitFor(() => {
      expect(result.current.phase).toBe('complete')
      expect(result.current.reportParagraphs).toEqual(['Report paragraph one'])
    })

    expect(mockFetch).toHaveBeenNthCalledWith(
      2,
      '/api/review/confirm/test-session',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ confirmed: true, contract_text: 'contract text', issues: [] }),
      }),
    )
  })

  it('accumulates final report paragraphs', async () => {
    const paragraphs = [{ paragraph: 'Paragraph one' }, { paragraph: 'Paragraph two' }]

    const mockResponse = new Response(createMockStream(
      paragraphs.map((item) => `event: final_report\ndata: ${JSON.stringify(item)}\n\n`),
    ))

    mockFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useStreamingReview('test-session', 'contract text'))

    await waitFor(() => {
      expect(result.current.reportParagraphs).toEqual(['Paragraph one', 'Paragraph two'])
    })
  })

  it('resets stale streaming state after the contract text is cleared', async () => {
    const mockResponse = new Response(createMockStream([
      `event: final_report\ndata: ${JSON.stringify({ paragraph: 'Paragraph one' })}\n\n`,
      'event: review_complete\ndata: {}\n\n',
    ]))

    mockFetch.mockResolvedValue(mockResponse)

    const { result, rerender } = renderHook(
      ({ sessionId, contractText }) => useStreamingReview(sessionId, contractText),
      {
        initialProps: {
          sessionId: 'test-session',
          contractText: 'contract text',
        },
      },
    )

    await waitFor(() => {
      expect(result.current.phase).toBe('complete')
      expect(result.current.reportParagraphs).toEqual(['Paragraph one'])
    })

    rerender({
      sessionId: 'next-session',
      contractText: '',
    })

    await waitFor(() => {
      expect(result.current.phase).toBe('idle')
      expect(result.current.reportParagraphs).toEqual([])
      expect(result.current.issues).toEqual([])
      expect(result.current.breakpointData).toBeNull()
    })
  })

  it('sends authorization headers when a token is provided', async () => {
    mockFetch.mockResolvedValue(new Response(createMockStream([])))

    renderHook(() => useStreamingReview('test-session', 'contract text', { token: 'jwt-token' }))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled()
    })

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/review',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer jwt-token',
        }),
      }),
    )
  })

  it('does not include a model when starting a review stream', async () => {
    mockFetch.mockResolvedValue(new Response(createMockStream([])))

    renderHook(() => useStreamingReview('test-session', 'contract text'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled()
    })

    const request = mockFetch.mock.calls[0]?.[1] as { body?: string } | undefined
    expect(request?.body).toBeDefined()
    expect(request?.body).not.toContain('"model"')
  })

  it('does not include a scan mode when starting the unified review stream', async () => {
    mockFetch.mockResolvedValue(new Response(createMockStream([])))

    renderHook(() => useStreamingReview('test-session', 'contract text'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled()
    })

    const request = mockFetch.mock.calls[0]?.[1] as { body?: string } | undefined
    expect(request?.body).toBe(JSON.stringify({
      contract_text: 'contract text',
      session_id: 'test-session',
    }))
    expect(request?.body).not.toContain('review_mode')
  })

  it('keeps retry disabled after the unified review completes normally', async () => {
    const initialIssues: ClauseIssue[] = [
      {
        clause: 'Deposit clause',
        issue: 'Deposit is too high',
        level: 'high',
        risk_level: 4,
        legal_reference: 'Art. 585',
      },
    ]

    mockFetch.mockResolvedValue(new Response(createMockStream([
      `event: initial_review_ready\ndata: ${JSON.stringify({ issues: initialIssues, summary: 'Initial review is ready.' })}\n\n`,
      'event: deep_review_started\ndata: {"message":"Completing full analysis."}\n\n',
      `event: final_report\ndata: ${JSON.stringify({ paragraph: 'Unified report paragraph' })}\n\n`,
      'event: review_complete\ndata: {"session_id":"test-session"}\n\n',
    ])))

    const { result } = renderHook(() => useStreamingReview('test-session', 'contract text'))

    await waitFor(() => {
      expect(result.current.phase).toBe('complete')
      expect(result.current.canRetryDeepReview).toBe(false)
      expect(result.current.reportParagraphs).toContain('Unified report paragraph')
    })
  })

  it('allows retrying deep review after a degraded completion', async () => {
    const initialIssues: ClauseIssue[] = [
      {
        clause: 'Deposit clause',
        issue: 'Deposit is too high',
        level: 'high',
        risk_level: 4,
        legal_reference: 'Art. 585',
      },
    ]

    mockFetch
      .mockResolvedValueOnce(new Response(createMockStream([
        `event: initial_review_ready\ndata: ${JSON.stringify({ issues: initialIssues, summary: 'Initial review is ready.' })}\n\n`,
        'event: deep_review_failed\ndata: {"message":"Deep analysis could not be completed yet."}\n\n',
        'event: review_complete\ndata: {"session_id":"test-session","degraded":true}\n\n',
      ])))
      .mockResolvedValueOnce(new Response(createMockStream([
        'event: deep_review_started\ndata: {"message":"Continuing deep review."}\n\n',
        `event: final_report\ndata: ${JSON.stringify({ paragraph: 'Completed report after retry' })}\n\n`,
        'event: deep_review_complete\ndata: {"message":"Deep review completed."}\n\n',
        'event: review_complete\ndata: {"session_id":"test-session"}\n\n',
      ])))

    const { result } = renderHook(() => useStreamingReview('test-session', 'contract text'))

    await waitFor(() => {
      expect(result.current.canRetryDeepReview).toBe(true)
      expect(result.current.phase).toBe('complete')
    })

    act(() => {
      result.current.retryDeepReview({
        issues: initialIssues,
      })
    })

    await waitFor(() => {
      expect(result.current.reportParagraphs).toContain('Completed report after retry')
      expect(result.current.canRetryDeepReview).toBe(false)
    })

    expect(mockFetch).toHaveBeenNthCalledWith(
      2,
      '/api/review/deepen',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          contract_text: 'contract text',
          session_id: 'test-session',
          issues: initialIssues,
        }),
      }),
    )
  })
})
