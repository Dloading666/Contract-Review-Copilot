import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useStreamingReview } from '../hooks/useStreamingReview'

// Mock fetch
const mockFetch = vi.fn()
globalThis.fetch = mockFetch

function createMockStream(chunks: string[]) {
  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    start(controller) {
      let i = 0
      function push() {
        if (i >= chunks.length) {
          controller.close()
          return
        }
        controller.enqueue(encoder.encode(chunks[i++]))
        setTimeout(push, 10)
      }
      push()
    },
  })
  return stream
}

describe('useStreamingReview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should parse entity_extraction event correctly', async () => {
    const entityData = {
      contract_type: '租赁合同',
      parties: { lessor: '张三', lessee: '李四' },
      rent: { monthly: 8500 },
      deposit: { amount: 17000 },
    }

    const mockResponse = new Response(createMockStream([
      'event: entity_extraction\ndata: ' + JSON.stringify(entityData) + '\n\n',
    ]))

    mockFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useStreamingReview('test-session', '合同文本'))

    await waitFor(() => {
      expect(result.current.extractedEntities).toEqual(entityData)
    })
  })

  it('should accumulate logic_review issues', async () => {
    const issues = [
      { clause: '违约金条款', issue: '过高', severity: 'high', risk_level: 3, legal_reference: '民法典585' },
      { clause: '滞纳金条款', issue: '超标', severity: 'critical', risk_level: 5, legal_reference: '民法典585' },
    ]

    const chunks = issues.map(
      (issue) => `event: logic_review\ndata: ${JSON.stringify(issue)}\n\n`
    )

    const mockResponse = new Response(createMockStream(chunks))
    mockFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useStreamingReview('test-session', '合同文本'))

    await waitFor(() => {
      expect(result.current.issues.length).toBe(2)
    })
  })

  it('should set phase to breakpoint and pause streaming', async () => {
    const breakpointData = {
      needs_review: true,
      question: '确认继续？',
      issues_count: 3,
      critical_count: 1,
      high_count: 1,
      medium_count: 1,
    }

    const mockResponse = new Response(createMockStream([
      `event: breakpoint\ndata: ${JSON.stringify(breakpointData)}\n\n`,
    ]))

    mockFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useStreamingReview('test-session', '合同文本'))

    await waitFor(() => {
      expect(result.current.phase).toBe('breakpoint')
      expect(result.current.breakpointData).toEqual(breakpointData)
      expect(result.current.isStreaming).toBe(false)
    })
  })

  it('should accumulate final_report paragraphs', async () => {
    const paragraphs = [
      { paragraph: '第一段' },
      { paragraph: '第二段' },
    ]

    const chunks = paragraphs.map(
      (p) => `event: final_report\ndata: ${JSON.stringify(p)}\n\n`
    )

    const mockResponse = new Response(createMockStream(chunks))
    mockFetch.mockResolvedValue(mockResponse)

    const { result } = renderHook(() => useStreamingReview('test-session', '合同文本'))

    await waitFor(() => {
      expect(result.current.reportParagraphs).toEqual(['第一段', '第二段'])
    })
  })
})
