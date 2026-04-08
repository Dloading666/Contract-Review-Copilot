import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DocPanel } from '../components/DocPanel'
import type { ModelOption, ReviewState } from '../App'

const modelOptions: ModelOption[] = [
  { key: 'gemma4', label: 'Gemma4' },
]

function buildReviewState(overrides: Partial<ReviewState> = {}): ReviewState {
  return {
    status: 'idle',
    sessionId: 'session-1',
    contractText: '',
    filename: '',
    thinkingSteps: [
      { id: 'parse', label: 'parse', status: 'pending' },
      { id: 'extract', label: 'extract', status: 'pending' },
      { id: 'retrieve', label: 'retrieve', status: 'pending' },
      { id: 'review', label: 'review', status: 'pending' },
    ],
    extractedInfo: null,
    routingDecision: null,
    riskCards: [],
    finalReport: [],
    breakpointMessage: null,
    errorMessage: null,
    chatMessages: [],
    ...overrides,
  }
}

describe('DocPanel', () => {
  it('shows a new conversation button and calls back when clicked', () => {
    const onNewConversation = vi.fn()

    render(
      <DocPanel
        review={buildReviewState({
          status: 'complete',
          filename: 'test-contract.docx',
          contractText: 'Clause 1\nDeposit: 10400',
        })}
        selectedModel="gemma4"
        availableModels={modelOptions}
        onModelChange={vi.fn()}
        onFileUpload={vi.fn()}
        onNewConversation={onNewConversation}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /new conversation/i }))

    expect(onNewConversation).toHaveBeenCalledTimes(1)
  })

  it('highlights matched risk lines in the document viewer', () => {
    render(
      <DocPanel
        review={buildReviewState({
          status: 'complete',
          filename: 'test-contract.docx',
          contractText: 'Clause 1\nDeposit: 10400\nLate fee: 10%\n',
          riskCards: [
            {
              id: '1',
              level: 'high',
              title: 'Deposit clause',
              clause: 'Deposit clause',
              issue: 'Deposit is too high',
              suggestion: 'Reduce the deposit amount',
              legalRef: 'Civil Code Art. 585',
              matchedText: 'Deposit: 10400',
            },
          ],
        })}
        selectedModel="gemma4"
        availableModels={modelOptions}
        onModelChange={vi.fn()}
        onFileUpload={vi.fn()}
      />,
    )

    expect(screen.getByText('Deposit: 10400').className).toContain('doc-highlight--high')
  })
})
