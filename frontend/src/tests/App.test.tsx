import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

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
            { key: 'glm-5', label: 'GLM-5' },
            { key: 'gemma4', label: 'Gemma4（本地免费）' },
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
    selectedModel,
    availableModels,
    onModelChange,
    onSendMessage,
  }: {
    review: { status: string }
    selectedModel: string
    availableModels: Array<{ key: string; label: string }>
    onModelChange: (model: 'gemma4') => void
    onSendMessage: (message: string, model: string) => void
  }) => (
    <div>
      <div data-testid="chat-status">{review.status}</div>
      <div data-testid="selected-model">{selectedModel}</div>
      <div data-testid="available-model-count">{availableModels.length}</div>
      <button type="button" onClick={() => onModelChange('gemma4')}>
        switch-model
      </button>
      <button type="button" onClick={() => onSendMessage('Summarize the risks', selectedModel)}>
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
    onModelChange: (model: 'gemma4') => void
    onFileUpload: (text: string, filename: string) => void
    onNewConversation?: () => void
  }) => (
    <div>
      <div data-testid="doc-status">{`${review.status}:${review.filename || 'empty'}`}</div>
      <div data-testid="doc-selected-model">{selectedModel}</div>
      <div data-testid="doc-available-model-count">{availableModels.length}</div>
      <button type="button" onClick={() => onModelChange('gemma4')}>
        doc-switch-model
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
      expect(screen.getByTestId('doc-status').textContent).toBe('idle:empty')
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

  it('persists the selected model per user and uses it for chat requests', async () => {
    localStorage.setItem('chatModel:demo@example.com', 'gemma4')

    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('selected-model').textContent).toBe('gemma4')
    })

    fireEvent.click(screen.getByRole('button', { name: 'send-message' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat',
        expect.objectContaining({
          body: expect.stringContaining('"model":"gemma4"'),
        }),
      )
    })
  })

  it('updates the persisted model when the user switches it', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'switch-model' }))

    await waitFor(() => {
      expect(localStorage.getItem('chatModel:demo@example.com')).toBe('gemma4')
      expect(screen.getByTestId('selected-model').textContent).toBe('gemma4')
    })
  })

  it('falls back to default model options when /api/models fails', async () => {
    fetchMock.mockImplementationOnce(async () => {
      throw new Error('models unavailable')
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('available-model-count').textContent).toBe('5')
      expect(screen.getByTestId('selected-model').textContent).toBe('gemma4')
      expect(screen.getByTestId('doc-available-model-count').textContent).toBe('5')
    })
  })

  it('shows the selector before upload and sends the selected model into review streaming', async () => {
    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('doc-selected-model').textContent).toBe('gemma4')
    })

    fireEvent.click(screen.getByRole('button', { name: 'upload-file' }))

    await waitFor(() => {
      const reviewCalls = useStreamingReviewMock.mock.calls as Array<
        [string, string, { enabled?: boolean; model?: string; token?: string }]
      >
      expect(
        reviewCalls.some(
          ([, contractText, options]) => (
            contractText === 'contract body'
            && options?.enabled === true
            && options?.model === 'gemma4'
            && options?.token === 'demo-token'
          ),
        ),
      ).toBe(true)
    })
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
      expect(screen.getByTestId('doc-status').textContent).toBe('idle:empty')
      expect(screen.getByTestId('chat-status').textContent).toBe('idle')
      expect(screen.getByTestId('selected-model').textContent).toBe('gemma4')
    })
  })
})
