import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { ChatPanel } from '../components/ChatPanel'
import type { ReviewState } from '../App'

function buildReviewState(overrides: Partial<ReviewState> = {}): ReviewState {
  return {
    status: 'complete',
    sessionId: 'session-1',
    contractText: '合同内容',
    filename: '合同.txt',
    thinkingSteps: [
      { id: 'parse', label: '解析合同主体信息', status: 'done' },
      { id: 'extract', label: '提取关键条款变量', status: 'done' },
      { id: 'retrieve', label: '检索相关法律依据', status: 'done' },
      { id: 'review', label: '扫描风险项', status: 'done' },
    ],
    extractedInfo: {
      lessor: '张三',
      lessee: '李四',
      property: '北京市朝阳区',
      monthlyRent: 8500,
      deposit: 17000,
      leaseTerm: '12个月',
    },
    routingDecision: null,
    riskCards: [],
    finalReport: [],
    breakpointMessage: null,
    errorMessage: null,
    chatMessages: [
      { id: 'assistant-1', role: 'assistant', content: '欢迎提问。' },
    ],
    ...overrides,
  }
}

describe('ChatPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('sends chat messages through the callback', () => {
    const onSendMessage = vi.fn()

    render(
      <ChatPanel
        review={buildReviewState()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={onSendMessage}
      />,
    )

    fireEvent.change(screen.getByPlaceholderText('输入问题，例如：押金风险在哪？这份合同怎么改？'), {
      target: { value: '押金风险是什么？' },
    })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))

    expect(onSendMessage).toHaveBeenCalledWith('押金风险是什么？')
  })

  it('requests autofix suggestions with authorization and renders the result', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ suggestion: '建议把违约金调整为一个月租金。' }),
    }) as typeof fetch

    render(
      <ChatPanel
        review={buildReviewState({
          riskCards: [
            {
              id: '1',
              level: 'high',
              title: '违约责任条款',
              clause: '第五条',
              issue: '违约金过高',
              suggestion: '降低违约金',
              legalRef: '《民法典》第585条',
              matchedText: '违约金：合同总额的200%',
            },
          ],
        })}
        authToken="jwt-token"
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '自动修正' }))

    await waitFor(() => {
      expect(screen.getByText('建议把违约金调整为一个月租金。')).toBeTruthy()
    })

    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/autofix',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer jwt-token',
        }),
      }),
    )
  })
})
