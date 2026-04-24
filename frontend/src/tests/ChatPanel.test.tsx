import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatPanel } from '../components/ChatPanel'
import type { ReviewState } from '../App'
import { EMPTY_ASSISTANT_REPLY_TEXT } from '../lib/chatText'

const noRiskTitle = '整体评估'
const noRiskIssue = '未发现明显不公平条款'

function buildReviewState(overrides: Partial<ReviewState> = {}): ReviewState {
  return {
    status: 'complete',
    reviewStage: 'complete',
    sessionId: 'session-1',
    contractText: 'contract body',
    filename: 'contract.txt',
    thinkingSteps: [
      { id: 'parse', label: 'parse', status: 'done' },
      { id: 'extract', label: 'extract', status: 'done' },
      { id: 'retrieve', label: 'retrieve', status: 'done' },
      { id: 'review', label: 'review', status: 'done' },
    ],
    extractedInfo: {
      lessor: 'Lessor',
      lessee: 'Lessee',
      property: 'Beijing',
      monthlyRent: 8500,
      deposit: 17000,
      leaseTerm: '12 months',
    },
    routingDecision: null,
    riskCards: [],
    finalReport: ['## Review summary', 'There are 2 clauses that should be revised first.'],
    initialSummary: null,
    deepUpdateNotice: null,
    breakpointMessage: null,
    errorMessage: null,
    chatMessages: [
      { id: 'assistant-1', role: 'assistant', content: 'Welcome, ask anything about the contract.' },
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

  it('keeps Q&A collapsed until the user explicitly opens it for a generated report', () => {
    render(
      <ChatPanel
        review={buildReviewState()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(screen.getByRole('textbox')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /继续问答/i })).toBeNull()
    expect(screen.queryByText('避坑指南')).toBeNull()
  })

  it('allows sending a question immediately after the full report is ready', async () => {
    const onSendMessage = vi.fn()
    const { container } = render(
      <ChatPanel
        review={buildReviewState()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={onSendMessage}
      />,
    )

    const textbox = await screen.findByRole('textbox')
    fireEvent.change(textbox, { target: { value: 'Where is the deposit risk?' } })
    fireEvent.click(container.querySelector('.chat-input-send') as HTMLButtonElement)

    expect(onSendMessage).toHaveBeenCalledWith('Where is the deposit risk?')
  })

  it('shows fallback text instead of an empty assistant bubble', async () => {
    render(
      <ChatPanel
        review={buildReviewState({
          chatMessages: [
            { id: 'user-1', role: 'user', content: '这个合同怎么改？' },
            { id: 'assistant-empty', role: 'assistant', content: '\u200b\n\ufeff' },
          ],
        })}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText(EMPTY_ASSISTANT_REPLY_TEXT)).toBeTruthy()
    })
  })

  it('does not show retrieval copy inside the assistant bubble while loading', () => {
    render(
      <ChatPanel
        review={buildReviewState({
          chatMessages: [
            { id: 'user-1', role: 'user', content: '帮我看看这个条款' },
            { id: 'assistant-loading', role: 'assistant', content: '', status: 'retrieving' },
          ],
        })}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(screen.queryByText(EMPTY_ASSISTANT_REPLY_TEXT)).toBeNull()
    expect(screen.queryByText(/Retrieving evidence/i)).toBeNull()
    expect(screen.getByLabelText('retrieving')).toBeTruthy()
  })

  it('does not render reference blocks under assistant answers', async () => {
    render(
      <ChatPanel
        review={buildReviewState({
          chatMessages: [
            { id: 'user-1', role: 'user', content: 'Can I ask for the deposit back?' },
            {
              id: 'assistant-1',
              role: 'assistant',
              content: 'The deposit return term should be clear and time-bound.',
              status: 'complete',
            },
          ],
        })}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(await screen.findByText('The deposit return term should be clear and time-bound.')).toBeTruthy()
    expect(screen.queryByText('参考来源')).toBeNull()
    expect(screen.queryByText(/Civil Code Article 585/)).toBeNull()
  })

  it('requests autofix suggestions with authorization and renders the result', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      text: async () => JSON.stringify({ suggestion: 'Rewrite the clause so the penalty stays within a reasonable range.' }),
    }) as typeof fetch

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
              changeType: 'none',
            },
          ],
        })}
        authToken="jwt-token"
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    fireEvent.click(container.querySelector('.risk-card__action-btn--fix') as HTMLButtonElement)

    await waitFor(() => {
      expect(screen.getByText('Rewrite the clause so the penalty stays within a reasonable range.')).toBeTruthy()
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
              changeType: 'none',
            },
          ],
        })}
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

  it('renders the final report inline without showing the old completion popup', () => {
    render(
      <ChatPanel
        review={buildReviewState({
          finalReport: ['## Review summary', 'There are 2 clauses that should be revised first.'],
        })}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(screen.getAllByText('Review summary').length).toBeGreaterThan(0)
    expect(screen.getAllByText('There are 2 clauses that should be revised first.').length).toBeGreaterThan(0)
    expect(screen.queryByText('避坑指南')).toBeNull()
    expect(screen.queryByRole('button', { name: /导出报告/i })).toBeNull()
  })

  it('renders the no-risk fallback as a zero-risk green state', () => {
    const { container } = render(
      <ChatPanel
        review={buildReviewState({
          finalReport: [],
          riskCards: [
            {
              id: 'placeholder-1',
              level: 'medium',
              title: noRiskTitle,
              clause: noRiskTitle,
              issue: noRiskIssue,
              suggestion: 'Keep checking the contract before signing.',
              legalRef: 'Civil Code Contract Book',
              matchedText: '',
              changeType: 'none',
            },
          ],
        })}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(container.querySelector('.ai-bubble--success')?.textContent).toMatch(/0/)
    expect(container.querySelector('.risk-card--success')).toBeTruthy()
    expect(container.querySelector('.risk-card__action-btn--fix')).toBeNull()
  })

  it('goes straight into Q&A for a no-risk completion without showing export actions', async () => {
    const onSendMessage = vi.fn()
    const { container } = render(
      <ChatPanel
        review={buildReviewState({
          finalReport: [],
          riskCards: [
            {
              id: 'placeholder-1',
              level: 'medium',
              title: noRiskTitle,
              clause: noRiskTitle,
              issue: noRiskIssue,
              suggestion: 'Keep checking the contract before signing.',
              legalRef: 'Civil Code Contract Book',
              matchedText: '',
              changeType: 'none',
            },
          ],
        })}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={onSendMessage}
      />,
    )

    const textbox = await screen.findByRole('textbox')
    expect(textbox).toBeTruthy()
    expect(container.querySelector('.px-btn--orange')).toBeNull()

    fireEvent.change(textbox, { target: { value: 'What should I still double-check before signing?' } })
    fireEvent.click(container.querySelector('.chat-input-send') as HTMLButtonElement)

    expect(onSendMessage).toHaveBeenCalledWith('What should I still double-check before signing?')
  })

  it('opens Q&A after a light scan with intermediate findings even without a full report', async () => {
    const onSendMessage = vi.fn()
    const { container } = render(
      <ChatPanel
        review={buildReviewState({
          finalReport: [],
          initialSummary: '初步审查已完成。',
          deepUpdateNotice: '轻度扫描已完成，你可以继续深度扫描。',
          riskCards: [
            {
              id: 'risk-1',
              level: 'high',
              title: 'Deposit clause',
              clause: 'Clause 3',
              issue: 'Deposit is too high',
              suggestion: 'Reduce the deposit',
              legalRef: 'Civil Code Art. 585',
              matchedText: 'Deposit: 20000',
              changeType: 'none',
            },
          ],
        })}
        canRetryDeepReview
        onRetryDeepReview={vi.fn()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={onSendMessage}
      />,
    )

    const textbox = await screen.findByRole('textbox')
    expect(textbox).toBeTruthy()
    expect(screen.getByRole('button', { name: /继续深度扫描/i })).toBeTruthy()

    fireEvent.change(textbox, { target: { value: 'What is the main deposit risk?' } })
    fireEvent.click(container.querySelector('.chat-input-send') as HTMLButtonElement)

    expect(onSendMessage).toHaveBeenCalledWith('What is the main deposit risk?')
  })

  it('keeps Q&A available while deep scan continues in the background', async () => {
    const onSendMessage = vi.fn()
    const { container } = render(
      <ChatPanel
        review={buildReviewState({
          status: 'reviewing',
          reviewStage: 'deep',
          finalReport: [],
          initialSummary: '初步审查已完成。',
          deepUpdateNotice: '正在继续补全深度分析与完整报告...',
          riskCards: [
            {
              id: 'risk-1',
              level: 'high',
              title: 'Deposit clause',
              clause: 'Clause 3',
              issue: 'Deposit is too high',
              suggestion: 'Reduce the deposit',
              legalRef: 'Civil Code Art. 585',
              matchedText: 'Deposit: 20000',
              changeType: 'none',
            },
          ],
        })}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={onSendMessage}
      />,
    )

    expect(await screen.findByRole('textbox')).toBeTruthy()
    expect(screen.getByText(/初步审查结果已经可以问答/)).toBeTruthy()

    fireEvent.change(container.querySelector('.chat-input-textarea') as HTMLTextAreaElement, {
      target: { value: 'Can I keep asking while deep scan runs?' },
    })
    fireEvent.click(container.querySelector('.chat-input-send') as HTMLButtonElement)

    expect(onSendMessage).toHaveBeenCalledWith('Can I keep asking while deep scan runs?')
  })

  it('keeps Q&A available after the user already entered chat and the full report is ready', async () => {
    render(
      <ChatPanel
        review={buildReviewState({
          chatMessages: [
            { id: 'user-1', role: 'user', content: 'Can you explain the deposit risk?' },
            { id: 'assistant-1', role: 'assistant', content: 'Yes, the deposit amount is above the typical range.' },
          ],
        })}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(await screen.findByRole('textbox')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /导出报告/i })).toBeNull()
  })

  it('keeps Q&A open once the full report is ready even before the final completion event lands', async () => {
    render(
      <ChatPanel
        review={buildReviewState({
          status: 'reviewing',
          reviewStage: 'complete',
          finalReport: ['## Review summary', 'Complete report body'],
          chatMessages: [
            { id: 'user-1', role: 'user', content: 'Can you explain the latest changes?' },
            { id: 'assistant-1', role: 'assistant', content: 'The report is now complete.' },
          ],
        })}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(await screen.findByRole('textbox')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /导出报告/i })).toBeNull()
  })

  it('hides the continue deep review action once a full report already exists', () => {
    render(
      <ChatPanel
        review={buildReviewState({
          finalReport: ['## Review summary', 'Complete report body'],
          deepUpdateNotice: '深度审查已完成，页面内容已自动更新。',
        })}
        canRetryDeepReview
        onRetryDeepReview={vi.fn()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button', { name: '继续深度扫描' })).toBeNull()
  })

  it('shows a continue deep review action after a degraded completion', () => {
    const onRetryDeepReview = vi.fn()

    render(
      <ChatPanel
        review={buildReviewState({
          finalReport: [],
          deepUpdateNotice: '深度分析暂未补全，当前先展示初步审查结果。',
        })}
        canRetryDeepReview
        onRetryDeepReview={onRetryDeepReview}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '继续深度扫描' }))
    expect(onRetryDeepReview).toHaveBeenCalledTimes(1)
  })
})
