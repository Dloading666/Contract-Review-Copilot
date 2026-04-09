import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App, { buildThinkingSteps } from '../App'

const {
  confirmMock,
  useStreamingReviewMock,
  authState,
  fetchMock,
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

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()

    if (url === '/api/models') {
      return {
        ok: true,
        json: async () => ({
          default_model: 'gemma4',
          models: [
            { key: 'gemma4', label: 'Gemma4' },
            { key: 'glm-5', label: 'GLM-5' },
          ],
        }),
      } as Response
    }

    if (url === '/api/chat') {
      return {
        ok: true,
        json: async () => ({ reply: 'LLM answer' }),
      } as Response
    }

    throw new Error(`Unexpected fetch: ${url} ${init?.method ?? 'GET'}`)
  })

  return { confirmMock, useStreamingReviewMock, authState, fetchMock }
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

vi.mock('../components/ChatPanel', () => ({
  ChatPanel: ({
    review,
    onSendMessage,
  }: {
    review: { status: string }
    onSendMessage: (message: string) => void
  }) => (
    <div>
      <div data-testid="chat-status">{review.status}</div>
      <button type="button" onClick={() => onSendMessage('Summarize the risks')}>
        send-message
      </button>
    </div>
  ),
}))

vi.mock('../components/DocPanel', () => ({
  DocPanel: ({
    review,
    selectedModel,
    availableModels,
    onModelChange,
    onFileUpload,
    onNewConversation,
  }: {
    review: { status: string; filename: string }
    selectedModel: string
    availableModels: Array<{ key: string; label: string }>
    onModelChange: (model: 'glm-5' | 'gemma4') => void
    onFileUpload: (text: string, filename: string) => void
    onNewConversation?: () => void
  }) => (
    <div>
      <div data-testid="doc-status">{`${review.status}:${review.filename || 'empty'}:${selectedModel}`}</div>
      <div data-testid="model-options">{availableModels.map((option) => option.key).join(',')}</div>
      <button type="button" onClick={() => onModelChange('glm-5')}>
        switch-model
      </button>
      <button type="button" onClick={() => onFileUpload('contract body', 'test-contract.docx')}>
        upload-file
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
    useStreamingReviewMock.mockClear()
    authState.isAuthenticated = true
    authState.login = vi.fn()
    authState.logout = vi.fn()
    authState.user = { email: 'demo@example.com', id: 'demo-user' }
    authState.token = 'demo-token'
    fetchMock.mockClear()
    vi.stubGlobal('fetch', fetchMock)
    localStorage.clear()
    sessionStorage.clear()
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

  it('keeps model selection in the upload area and uses it for chat requests', async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('model-options').textContent).toContain('glm-5')
    })

    fireEvent.click(screen.getByRole('button', { name: 'switch-model' }))
    fireEvent.click(screen.getByRole('button', { name: 'send-message' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat',
        expect.objectContaining({
          body: expect.stringContaining('"model":"glm-5"'),
        }),
      )
    })
  })

  it('starts review streaming with the selected upload model', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'switch-model' }))
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
              && options?.model === 'glm-5'
            ),
          ),
      ).toBe(true)
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

  it('resets the workspace when the signed-in user changes', async () => {
    const { rerender } = render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'upload-file' }))

    await waitFor(() => {
      expect(screen.getByTestId('doc-status').textContent).toContain('complete:test-contract.docx')
    })

    authState.user = { email: 'other@example.com', id: 'other-user' }
    authState.token = 'other-token'
    rerender(<App />)

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
