import { useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App, { buildThinkingSteps } from '../App'
import { getDisclaimerAcceptanceStorageKey } from '../lib/disclaimer'

const {
  confirmMock,
  useStreamingReviewMock,
  authState,
  fetchMock,
  idleHookState,
  completeHookState,
} = vi.hoisted(() => {
  const confirmMock = vi.fn()
  const authState = {
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    user: { email: 'demo@example.com', id: 'demo-user' },
    token: 'demo-token',
  }

  const idleHookState = {
    phase: 'idle',
    extractedEntities: null,
    routingDecision: null,
    issues: [],
    breakpointData: null,
    reportParagraphs: [],
    error: null,
    confirm: confirmMock,
    isStreaming: false,
  }

  const completeHookState = {
    phase: 'complete',
    extractedEntities: {
      parties: { lessor: 'lessor-a', lessee: 'lessee-b' },
      property: { address: 'pudong' },
      rent: { monthly: 5200 },
      deposit: { amount: 10400 },
      lease_term: { duration_text: '12 months' },
    },
    routingDecision: { strategy: 'pgvector', reason: 'rental_contract' },
    issues: [
      {
        clause: 'Deposit clause',
        issue: 'Deposit amount is too high',
        suggestion: 'Limit it to no more than two months of rent',
        level: 'high',
        legal_reference: 'Civil Code Art. 585',
        matched_text: 'deposit 10400',
      },
    ],
    breakpointData: null,
    reportParagraphs: ['Report paragraph 1'],
    error: null,
    confirm: confirmMock,
    isStreaming: false,
  }

  const useStreamingReviewMock = vi.fn((_sessionId: string, contractText: string, _options?: unknown) => (
    contractText ? completeHookState : idleHookState
  ))

  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()

    if (url === '/api/chat') {
      return {
        ok: true,
        json: async () => ({ reply: 'LLM answer' }),
      } as Response
    }

    throw new Error(`Unexpected fetch: ${url}`)
  })

  return { confirmMock, useStreamingReviewMock, authState, fetchMock, idleHookState, completeHookState }
})

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => authState,
}))

vi.mock('../hooks/useStreamingReview', () => ({
  useStreamingReview: useStreamingReviewMock,
}))

vi.mock('../components/SideNav', () => ({
  SideNav: () => <div data-testid="side-nav" />,
}))

vi.mock('../components/DisclaimerModal', () => ({
  DisclaimerModal: ({ onAccept }: { onAccept: () => void }) => {
    const [checked, setChecked] = useState(false)

    return (
      <div role="dialog" aria-label="Disclaimer">
        <label>
          <input
            type="checkbox"
            aria-label="I agree"
            checked={checked}
            onChange={(event) => setChecked(event.currentTarget.checked)}
          />
          I agree
        </label>
        <button type="button" disabled={!checked} onClick={onAccept}>
          Accept and continue
        </button>
      </div>
    )
  },
}))

vi.mock('../components/ChatPanel', () => ({
  ChatPanel: ({
    review,
    onSendMessage,
  }: {
    review: { status: string; breakpointMessage?: string | null }
    onSendMessage: (message: string) => void
  }) => (
    <div>
      <div data-testid="chat-status">{review.status}</div>
      <div data-testid="chat-breakpoint-message">{review.breakpointMessage ?? ''}</div>
      <button type="button" onClick={() => onSendMessage('Summarize the risks')}>
        send-message
      </button>
    </div>
  ),
}))

vi.mock('../components/DocPanel', () => ({
  DocPanel: ({
    review,
    onFileUpload,
    onOcrReady,
    onContractTextChange,
    onConfirmReview,
    onNewConversation,
  }: {
    review: { status: string; filename: string }
    onFileUpload: (text: string, filename: string) => void
    onOcrReady: (text: string, filename: string, warnings?: string[]) => void
    onContractTextChange: (text: string) => void
    onConfirmReview: () => void
    onNewConversation?: () => void
  }) => (
    <div>
      <div data-testid="doc-status">{`${review.status}:${review.filename || 'empty'}`}</div>
      <button type="button" onClick={() => onFileUpload('contract body', 'test-contract.docx')}>
        upload-file
      </button>
      <button type="button" onClick={() => onOcrReady('ocr text', 'contract-photo.png', ['ocr warning'])}>
        ocr-ready
      </button>
      <button type="button" onClick={() => onContractTextChange('edited ocr text')}>
        update-ocr-text
      </button>
      <button type="button" onClick={onConfirmReview}>
        confirm-ocr
      </button>
      <button type="button" onClick={onNewConversation}>
        new-conversation
      </button>
    </div>
  ),
}))

vi.mock('../pages/LoginPage', () => ({
  LoginPage: () => null,
}))

vi.mock('../pages/RegisterPage', () => ({
  RegisterPage: () => null,
}))

vi.mock('../pages/SettingsPage', () => ({
  SettingsPage: () => null,
}))

describe('App new conversation flow', () => {
  beforeEach(() => {
    confirmMock.mockReset()
    useStreamingReviewMock.mockReset()
    useStreamingReviewMock.mockImplementation((_sessionId: string, contractText: string) => (
      contractText ? completeHookState : idleHookState
    ))
    authState.isAuthenticated = true
    authState.login = vi.fn()
    authState.logout = vi.fn()
    authState.user = { email: 'demo@example.com', id: 'demo-user' }
    authState.token = 'demo-token'
    fetchMock.mockClear()
    vi.stubGlobal('fetch', fetchMock)
    localStorage.clear()
    sessionStorage.clear()
    localStorage.setItem(getDisclaimerAcceptanceStorageKey('demo@example.com'), 'accepted')
  })

  it('requires accepting the disclaimer before using the site on a new device', async () => {
    localStorage.removeItem(getDisclaimerAcceptanceStorageKey('demo@example.com'))

    render(<App />)

    expect(screen.getByRole('dialog', { name: 'Disclaimer' })).toBeTruthy()

    const confirmButton = screen.getByRole('button', { name: 'Accept and continue' })
    expect(confirmButton.getAttribute('disabled')).not.toBeNull()

    fireEvent.click(screen.getByRole('checkbox', { name: 'I agree' }))
    expect(confirmButton.getAttribute('disabled')).toBeNull()

    fireEvent.click(confirmButton)

    await waitFor(() => {
      expect(screen.getByTestId('doc-status').textContent).toContain('idle:empty')
    })
    expect(localStorage.getItem(getDisclaimerAcceptanceStorageKey('demo@example.com'))).toBe('accepted')
  })

  it('saves the current reviewed conversation into history before starting a new one', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'upload-file' }))

    await waitFor(() => {
      expect(screen.getByTestId('doc-status').textContent).toContain('complete:test-contract.docx')
    })

    fireEvent.click(screen.getByRole('button', { name: 'send-message' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat',
        expect.objectContaining({ method: 'POST' }),
      )
    })

    fireEvent.click(screen.getByRole('button', { name: 'new-conversation' }))

    await waitFor(() => {
      expect(screen.getByTestId('doc-status').textContent).toContain('idle:empty')
    })

    const savedHistory = JSON.parse(localStorage.getItem('reviewHistory:demo@example.com') || '[]')

    expect(savedHistory).toHaveLength(1)
    expect(savedHistory[0]).toMatchObject({
      filename: 'test-contract.docx',
      status: 'complete',
      contractText: 'contract body',
      finalReport: ['Report paragraph 1'],
    })
    expect(savedHistory[0].chatMessages.length).toBeGreaterThan(1)
    expect(localStorage.getItem('reviewHistory')).toBeNull()
  })

  it('starts review streaming without requesting or passing a model selector', async () => {
    render(<App />)

    expect(fetchMock).not.toHaveBeenCalledWith('/api/models', expect.anything())

    fireEvent.click(screen.getByRole('button', { name: 'upload-file' }))

    await waitFor(() => {
      const reviewCalls = useStreamingReviewMock.mock.calls as Array<
        [string, string, { enabled?: boolean; token?: string; model?: string }]
      >

      expect(
        reviewCalls.some(
          ([, contractText, options]) => (
            contractText === 'contract body'
            && options?.enabled === true
            && options?.token === 'demo-token'
            && options?.model === undefined
          ),
        ),
      ).toBe(true)
    })
  })

  it('sends chat requests without a model field', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'send-message' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat',
        expect.objectContaining({
          body: expect.not.stringContaining('"model"'),
        }),
      )
    })
  })

  it('waits for OCR confirmation before starting the review stream', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'ocr-ready' }))

    await waitFor(() => {
      expect(screen.getByTestId('doc-status').textContent).toContain('ocr_ready:contract-photo.png')
    })

    const reviewCallsBeforeConfirm = useStreamingReviewMock.mock.calls as Array<
      [string, string, { enabled?: boolean; token?: string; model?: string }]
    >
    expect(
      reviewCallsBeforeConfirm.some(
        ([, contractText, options]) => contractText === 'ocr text' && options?.enabled === true,
      ),
    ).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'update-ocr-text' }))
    fireEvent.click(screen.getByRole('button', { name: 'confirm-ocr' }))

    await waitFor(() => {
      const reviewCallsAfterConfirm = useStreamingReviewMock.mock.calls as Array<
        [string, string, { enabled?: boolean; token?: string; model?: string }]
      >

      expect(
        reviewCallsAfterConfirm.some(
          ([, contractText, options]) => (
            contractText === 'edited ocr text'
            && options?.enabled === true
            && options?.token === 'demo-token'
          ),
        ),
      ).toBe(true)
      expect(screen.getByTestId('doc-status').textContent).toContain('complete:contract-photo.png')
    })
  })

  it('goes straight to complete when only the placeholder issue is present', async () => {
    useStreamingReviewMock.mockImplementation((_sessionId: string, contractText: string) => (
      contractText
        ? {
            phase: 'complete',
            extractedEntities: null,
            routingDecision: null,
            issues: [
              {
                clause: 'Overall summary',
                issue: 'No obviously unfair clauses were detected.',
                suggestion: 'Keep checking deposit, termination, and evidence retention clauses before signing.',
                level: 'low',
                legal_reference: 'Civil Code Contract Book',
                matched_text: '',
                risk_level: 1,
              },
            ],
            breakpointData: null,
            reportParagraphs: [],
            error: null,
            confirm: confirmMock,
            isStreaming: false,
          }
        : {
            phase: 'idle',
            extractedEntities: null,
            routingDecision: null,
            issues: [],
            breakpointData: null,
            reportParagraphs: [],
            error: null,
            confirm: confirmMock,
            isStreaming: false,
          }
    ) as any)

    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'upload-file' }))

    await waitFor(() => {
      expect(screen.getByTestId('chat-status').textContent).toBe('complete')
      expect(screen.getByTestId('chat-breakpoint-message').textContent).toBe('')
      expect(screen.getByTestId('doc-status').textContent).toContain('complete:test-contract.docx')
    })
  })

  it('saves review history only once when the review first reaches complete', async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem')

    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'upload-file' }))

    await waitFor(() => {
      expect(screen.getByTestId('doc-status').textContent).toContain('complete:test-contract.docx')
      expect(
        setItemSpy.mock.calls.filter(([key]) => key === 'reviewHistory:demo@example.com').length,
      ).toBe(1)
    })

    fireEvent.click(screen.getByRole('button', { name: 'send-message' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat',
        expect.objectContaining({ method: 'POST' }),
      )
    })

    expect(
      setItemSpy.mock.calls.filter(([key]) => key === 'reviewHistory:demo@example.com').length,
    ).toBe(1)

    setItemSpy.mockRestore()
  })

  it('requires the next signed-in user to accept the disclaimer again', async () => {
    const { rerender } = render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'upload-file' }))

    await waitFor(() => {
      expect(screen.getByTestId('doc-status').textContent).toContain('complete:test-contract.docx')
    })

    authState.user = { email: 'other@example.com', id: 'other-user' }
    authState.token = 'other-token'
    rerender(<App />)

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: 'Disclaimer' })).toBeTruthy()
    })

    fireEvent.click(screen.getByRole('checkbox', { name: 'I agree' }))
    fireEvent.click(screen.getByRole('button', { name: 'Accept and continue' }))

    await waitFor(() => {
      expect(screen.getByTestId('doc-status').textContent).toContain('idle:empty')
      expect(screen.getByTestId('chat-status').textContent).toBe('idle')
    })
  })
})

describe('buildThinkingSteps', () => {
  it('marks parse as active when the stream just started', () => {
    expect(buildThinkingSteps('started', null, null).map((step) => step.status)).toEqual([
      'active',
      'pending',
      'pending',
      'pending',
    ])
  })

  it('marks extraction as active during entity extraction', () => {
    expect(buildThinkingSteps('extraction', null, null).map((step) => step.status)).toEqual([
      'done',
      'active',
      'pending',
      'pending',
    ])
  })

  it('marks retrieval as active during routing', () => {
    expect(buildThinkingSteps('routing', null, null).map((step) => step.status)).toEqual([
      'done',
      'done',
      'active',
      'pending',
    ])
  })

  it('marks review as active during logic review', () => {
    expect(buildThinkingSteps('logic_review', null, null).map((step) => step.status)).toEqual([
      'done',
      'done',
      'done',
      'active',
    ])
  })
})
