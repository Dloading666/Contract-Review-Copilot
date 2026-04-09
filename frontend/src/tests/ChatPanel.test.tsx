import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatPanel } from '../components/ChatPanel'
import type { ReviewState } from '../App'

const noRiskTitle = '鏁翠綋璇勪及'
const noRiskIssue = '鏈彂鐜版槑鏄句笉鍏钩'

function buildReviewState(overrides: Partial<ReviewState> = {}): ReviewState {
  return {
    status: 'complete',
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
    const { container } = render(
      <ChatPanel
        review={buildReviewState()}
        onExportReport={vi.fn()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(screen.queryByRole('textbox')).toBeNull()
    expect(container.querySelector('.px-btn--ghost')).toBeTruthy()
    expect(container.querySelector('.chat-input-send')).toBeNull()
  })

  it('opens Q&A after clicking continue and sends the message', async () => {
    const onSendMessage = vi.fn()
    const { container } = render(
      <ChatPanel
        review={buildReviewState()}
        onExportReport={vi.fn()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={onSendMessage}
      />,
    )

    fireEvent.click(container.querySelector('.px-btn--ghost') as HTMLButtonElement)

    const textbox = await screen.findByRole('textbox')
    fireEvent.change(textbox, { target: { value: 'Where is the deposit risk?' } })
    fireEvent.click(container.querySelector('.chat-input-send') as HTMLButtonElement)

    expect(onSendMessage).toHaveBeenCalledWith('Where is the deposit risk?')
  })

  it('requests autofix suggestions with authorization and renders the result', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ suggestion: 'Rewrite the clause so the penalty stays within a reasonable range.' }),
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
    const { container } = render(
      <ChatPanel
        review={buildReviewState({
          finalReport: ['## Review summary', 'There are 2 clauses that should be revised first.'],
        })}
        onExportReport={onExportReport}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(screen.getAllByText('Review summary').length).toBeGreaterThan(0)
    expect(screen.getAllByText('There are 2 clauses that should be revised first.').length).toBeGreaterThan(0)

    fireEvent.click(container.querySelector('.px-btn--orange') as HTMLButtonElement)

    expect(onExportReport).toHaveBeenCalledTimes(1)
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
            },
          ],
        })}
        onExportReport={vi.fn()}
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
            },
          ],
        })}
        onExportReport={vi.fn()}
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
})
