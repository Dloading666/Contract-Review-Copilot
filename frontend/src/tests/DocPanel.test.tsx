import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DocPanel } from '../components/DocPanel'
import type { ModelOption, ReviewState } from '../App'

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

const modelOptions: ModelOption[] = [
  { key: 'gemma4', label: 'Gemma4' },
  { key: 'glm-5', label: 'GLM-5' },
]

describe('DocPanel', () => {
  it('shows a model selector in the upload state and forwards changes', () => {
    const onModelChange = vi.fn()

    render(
      <DocPanel
        review={buildReviewState()}
        selectedModel="gemma4"
        availableModels={modelOptions}
        onModelChange={onModelChange}
        onFileUpload={vi.fn()}
      />,
    )

    expect(screen.getByText(/开始分析前先选择模型/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /模型/i }))
    fireEvent.click(screen.getByRole('option', { name: 'GLM-5' }))

    expect(onModelChange).toHaveBeenCalledWith('glm-5')
  })

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

  it('resets zoom when switching to another contract session', () => {
    const { container, rerender } = render(
      <DocPanel
        review={buildReviewState({
          status: 'complete',
          sessionId: 'session-1',
          filename: 'first-contract.docx',
          contractText: 'Clause 1\nDeposit: 10400\n',
        })}
        selectedModel="gemma4"
        availableModels={modelOptions}
        onModelChange={vi.fn()}
        onFileUpload={vi.fn()}
      />,
    )

    const zoomButtons = container.querySelectorAll('.doc-panel__zoom-btn')
    fireEvent.click(zoomButtons[1] as HTMLButtonElement)
    fireEvent.click(zoomButtons[1] as HTMLButtonElement)

    expect(container.querySelector('.doc-panel__zoom-level')?.textContent).toBe('120%')

    rerender(
      <DocPanel
        review={buildReviewState({
          status: 'complete',
          sessionId: 'session-2',
          filename: 'second-contract.docx',
          contractText: 'Clause 2\nLate fee: 10%\n',
        })}
        selectedModel="gemma4"
        availableModels={modelOptions}
        onModelChange={vi.fn()}
        onFileUpload={vi.fn()}
      />,
    )

    expect(container.querySelector('.doc-panel__zoom-level')?.textContent).toBe('100%')
  })
})
