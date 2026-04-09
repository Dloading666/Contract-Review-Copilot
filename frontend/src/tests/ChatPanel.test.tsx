import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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
      { id: 'review', label: '扫描风险项目', status: 'done' },
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
    finalReport: ['## 审查结论', '存在 2 处需要优先处理的条款。'],
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
    Object.defineProperty(window.HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
      writable: true,
    })
    Object.defineProperty(window, 'scrollTo', {
      configurable: true,
      value: vi.fn(),
      writable: true,
    })
  })

  it('keeps Q&A collapsed until the user explicitly opens it', () => {
    render(
      <ChatPanel
        review={buildReviewState()}
        onExportReport={vi.fn()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.getByRole('button', { name: /继续问答/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /模型/i })).toBeNull()
  })

  it('opens Q&A and sends the message without a model selector', async () => {
    const onSendMessage = vi.fn()

    render(
      <ChatPanel
        review={buildReviewState()}
        onExportReport={vi.fn()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={onSendMessage}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /继续问答/ }))

    const textbox = await screen.findByRole('textbox')
    fireEvent.change(textbox, { target: { value: '押金风险在哪里？' } })
    fireEvent.click(document.querySelector('.chat-input-send') as HTMLButtonElement)

    expect(screen.queryByRole('button', { name: /模型/i })).toBeNull()
    expect(onSendMessage).toHaveBeenCalledWith('押金风险在哪里？')
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
              matchedText: '违约金：合同总额的100%',
            },
          ],
        })}
        authToken="jwt-token"
        onExportReport={vi.fn()}
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

  it('toggles risk details when the card header is clicked', async () => {
    const { container } = render(
      <ChatPanel
        review={buildReviewState({
          riskCards: [
            {
              id: '1',
              level: 'high',
              title: 'Penalty clause',
              clause: 'Clause 5',
              issue: 'Penalty is too high',
              suggestion: 'Lower the penalty',
              legalRef: 'Civil Code Art. 585',
              matchedText: 'Penalty: 100% of contract value',
            },
          ],
        })}
        onExportReport={vi.fn()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(screen.queryByText('Lower the penalty')).toBeNull()

    fireEvent.click(container.querySelector('.risk-card__header') as HTMLDivElement)

    await waitFor(() => {
      expect(screen.getByText('Lower the penalty')).toBeTruthy()
    })
  })

  it('shows report content in the dialog and exports from there', () => {
    const onExportReport = vi.fn()

    render(
      <ChatPanel
        review={buildReviewState({
          finalReport: ['## 审查结论', '存在 2 处需要优先处理的条款。'],
        })}
        onExportReport={onExportReport}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(screen.getAllByText('审查结论').length).toBeGreaterThan(0)
    expect(screen.getAllByText('存在 2 处需要优先处理的条款。').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: '导出报告' }))

    expect(onExportReport).toHaveBeenCalledTimes(1)
  })

  it('shows guide generation feedback with elapsed seconds after confirmation', async () => {
    vi.useFakeTimers()

    const guideRiskCard = {
      id: '1',
      level: 'high' as const,
      title: 'Rent loan clause',
      clause: 'Clause 6',
      issue: 'The contract contains installment, credit, or auto-debit arrangements that may indicate rent-loan risk.',
      suggestion: 'Remove rent-loan, credit authorization, and auto-debit related clauses.',
      legalRef: 'Civil Code Art. 496',
      matchedText: 'The tenant shall cooperate with installment financing and authorize automatic deductions.',
    }

    const { rerender } = render(
      <ChatPanel
        review={buildReviewState({
          status: 'breakpoint',
          riskCards: [guideRiskCard],
          breakpointMessage: 'Need confirmation before generating the full guide.',
          finalReport: [],
        })}
        onExportReport={vi.fn()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    rerender(
      <ChatPanel
        review={buildReviewState({
          status: 'reviewing',
          riskCards: [guideRiskCard],
          breakpointMessage: null,
          finalReport: [],
        })}
        onExportReport={vi.fn()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getAllByText(/正在生成避坑指南中/).length).toBeGreaterThan(0)
    expect(screen.getByText('0秒')).toBeTruthy()

    act(() => {
      vi.advanceTimersByTime(1000)
    })

    expect(screen.getByText('1秒')).toBeTruthy()
    vi.useRealTimers()
  })

  it('renders the no-risk fallback as a zero-risk green state', () => {
    const { container } = render(
      <ChatPanel
        review={buildReviewState({
          riskCards: [
            {
              id: 'placeholder-1',
              level: 'medium',
              title: '整体评估',
              clause: '整体评估',
              issue: '未发现明显不公平条款。',
              suggestion: '签约前仍建议逐条核对押金、解约和证据留存要求。',
              legalRef: '《民法典》合同编',
              matchedText: '',
            },
          ],
        })}
        onExportReport={vi.fn()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(container.querySelector('.ai-bubble--success')?.textContent).toMatch(/0\s*处/)
    expect(screen.getByText('通过')).toBeTruthy()
    expect(screen.queryByText('自动修正')).toBeNull()
  })
})
