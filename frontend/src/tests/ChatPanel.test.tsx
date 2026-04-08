import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatPanel } from '../components/ChatPanel'
import type { ModelOption, ReviewState } from '../App'

const modelOptions: ModelOption[] = [
  { key: 'glm-5', label: 'GLM-5' },
  { key: 'gemma4', label: 'Gemma4（本地免费）' },
]

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
    finalReport: ['## 审查结论', '存在 2 处需要重点处理的条款。'],
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
        selectedModel="glm-5"
        availableModels={modelOptions}
        onModelChange={vi.fn()}
        onExportReport={vi.fn()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.getByRole('button', { name: /问答/ })).toBeTruthy()
  })

  it('opens the model menu, switches model, and sends the selected model', async () => {
    const onSendMessage = vi.fn()
    const onModelChange = vi.fn()

    render(
      <ChatPanel
        review={buildReviewState()}
        selectedModel="glm-5"
        availableModels={modelOptions}
        onModelChange={onModelChange}
        onExportReport={vi.fn()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={onSendMessage}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /继续问答/ }))
    fireEvent.click(screen.getByRole('button', { name: /模型/i }))
    fireEvent.click(screen.getByRole('option', { name: /Gemma4/ }))

    expect(onModelChange).toHaveBeenCalledWith('gemma4')

    const textbox = await screen.findByRole('textbox')
    fireEvent.change(textbox, { target: { value: '押金风险在哪里？' } })
    fireEvent.click(document.querySelector('.chat-input-send') as HTMLButtonElement)

    expect(onSendMessage).toHaveBeenCalledWith('押金风险在哪里？', 'glm-5')
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
        selectedModel="glm-5"
        availableModels={modelOptions}
        onModelChange={vi.fn()}
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

  it('shows report content in the dialog and exports from there', () => {
    const onExportReport = vi.fn()

    render(
      <ChatPanel
        review={buildReviewState({
          finalReport: ['## 审查结论', '存在 2 处需要优先处理的条款。'],
        })}
        selectedModel="glm-5"
        availableModels={modelOptions}
        onModelChange={vi.fn()}
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
        selectedModel="gemma4"
        availableModels={modelOptions}
        onModelChange={vi.fn()}
        onExportReport={vi.fn()}
        onBreakpointConfirm={vi.fn()}
        onReset={vi.fn()}
        onSendMessage={vi.fn()}
      />,
    )

    expect(container.querySelector('.ai-bubble--success')?.textContent).toMatch(/已识别 0 处\s*潜在合规风险/)
    expect(screen.getByText('通过')).toBeTruthy()
    expect(screen.queryByText('自动修正')).toBeNull()
  })
})
