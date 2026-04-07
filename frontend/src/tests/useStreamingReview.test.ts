import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useStreamingReview } from '../hooks/useStreamingReview'

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
      contract_type: '租赁合同',
      parties: { lessor: '张三', lessee: '李四' },
      rent: { monthly: 8500, currency: '人民币', payment_cycle: '月付' },
      deposit: { amount: 17000, conditions: '退租后返还' },
      property: { address: '北京市朝阳区', area: '45' },
      lease_term: { start: '2026-05-01', end: '2027-04-30', duration_text: '12个月' },
      penalty_clause: '两个月租金',
    }

    const mockResponse = new Response(createMockStream([
      `event: entity_extraction\ndata: ${JSON.stringify({ entities: entityData })}\n\n`,
    ]))

    mockFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useStreamingReview('test-session', '合同文本'))

    await waitFor(() => {
      expect(result.current.extractedEntities).toEqual(entityData)
    })
  })

  it('accumulates logic review issues', async () => {
    const issues = [
      { clause: '违约金条款', issue: '过高', level: 'high', risk_level: 3, legal_reference: '民法典585' },
      { clause: '滞纳金条款', issue: '超标', level: 'critical', risk_level: 5, legal_reference: '民法典585' },
    ]

    const mockResponse = new Response(createMockStream(
      issues.map((issue) => `event: logic_review\ndata: ${JSON.stringify({ issue })}\n\n`),
    ))

    mockFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useStreamingReview('test-session', '合同文本'))

    await waitFor(() => {
      expect(result.current.issues).toHaveLength(2)
      expect(result.current.issues[0].clause).toBe('违约金条款')
    })
  })

  it('sets breakpoint data and pauses streaming', async () => {
    const breakpointData = {
      needs_review: true,
      question: '确认继续？',
      issues_count: 3,
      critical_count: 1,
      high_count: 1,
      medium_count: 1,
    }

    const mockResponse = new Response(createMockStream([
      `event: breakpoint\ndata: ${JSON.stringify({ breakpoint: breakpointData, issues: [] })}\n\n`,
    ]))

    mockFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useStreamingReview('test-session', '合同文本'))

    await waitFor(() => {
      expect(result.current.phase).toBe('breakpoint')
      expect(result.current.breakpointData).toEqual(breakpointData)
      expect(result.current.isStreaming).toBe(false)
    })
  })

  it('accumulates final report paragraphs', async () => {
    const paragraphs = [{ paragraph: '第一段' }, { paragraph: '第二段' }]

    const mockResponse = new Response(createMockStream(
      paragraphs.map((item) => `event: final_report\ndata: ${JSON.stringify(item)}\n\n`),
    ))

    mockFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useStreamingReview('test-session', '合同文本'))

    await waitFor(() => {
      expect(result.current.reportParagraphs).toEqual(['第一段', '第二段'])
    })
  })

  it('sends authorization headers when a token is provided', async () => {
    mockFetch.mockResolvedValue(new Response(createMockStream([])))

    renderHook(() => useStreamingReview('test-session', '合同文本', { token: 'jwt-token' }))

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
})
