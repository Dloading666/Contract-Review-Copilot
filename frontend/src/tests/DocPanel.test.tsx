import type { ComponentProps } from 'react'
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ReviewState } from '../App'
import { DocPanel } from '../components/DocPanel'

function buildReviewState(overrides: Partial<ReviewState> = {}): ReviewState {
  return {
    status: 'idle',
    sessionId: 'session-1',
    contractText: '',
    filename: '',
    ocrWarnings: [],
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

function renderDocPanel(
  reviewOverrides: Partial<ReviewState> = {},
  propOverrides: Partial<ComponentProps<typeof DocPanel>> = {},
) {
  const props: ComponentProps<typeof DocPanel> = {
    review: buildReviewState(reviewOverrides),
    authToken: 'demo-token',
    onFileUpload: vi.fn(),
    onOcrReady: vi.fn(),
    onContractTextChange: vi.fn(),
    onConfirmReview: vi.fn(),
    onReset: vi.fn(),
    onNewConversation: vi.fn(),
    ...propOverrides,
  }

  return {
    ...render(<DocPanel {...props} />),
    props,
  }
}

describe('DocPanel', () => {
  beforeEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('does not render a model selector in the upload state', () => {
    const { container } = renderDocPanel()
    expect(container.querySelector('.model-select')).toBeNull()
  })

  it('uploads multiple images through the unified OCR ingest endpoint and waits for confirmation', async () => {
    const onFileUpload = vi.fn()
    const onOcrReady = vi.fn()
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        source_type: 'image_batch',
        display_name: '合同照片 等 2 页图片',
        merged_text: '甲方：张三\n乙方：李四',
        warnings: ['第 2 页 OCR 失败：vision OCR unavailable'],
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const { container } = renderDocPanel({}, { authToken: 'demo-token', onFileUpload, onOcrReady })
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const imageFiles = [
      new File(['fake-image-1'], 'contract-1.png', { type: 'image/png' }),
      new File(['fake-image-2'], 'contract-2.png', { type: 'image/png' }),
    ]

    fireEvent.change(fileInput, { target: { files: imageFiles } })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/ocr/ingest',
        expect.objectContaining({
          method: 'POST',
          headers: { Authorization: 'Bearer demo-token' },
          body: expect.any(FormData),
        }),
      )
      expect(onOcrReady).toHaveBeenCalledWith(
        '甲方：张三\n乙方：李四',
        '合同照片 等 2 页图片',
        ['第 2 页 OCR 失败：vision OCR unavailable'],
      )
      expect(onFileUpload).not.toHaveBeenCalled()
    })
  })

  it('uploads a PDF through the ingest endpoint and waits for OCR confirmation', async () => {
    const onFileUpload = vi.fn()
    const onOcrReady = vi.fn()
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        source_type: 'pdf_ocr',
        display_name: 'lease.pdf',
        merged_text: '第一条 租赁用途\n第二条 租金',
        warnings: [],
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const { container } = renderDocPanel({}, { onFileUpload, onOcrReady })
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const pdfFile = new File(['fake-pdf'], 'lease.pdf', { type: 'application/pdf' })

    fireEvent.change(fileInput, { target: { files: [pdfFile] } })

    await waitFor(() => {
      expect(onOcrReady).toHaveBeenCalledWith('第一条 租赁用途\n第二条 租金', 'lease.pdf', [])
      expect(onFileUpload).not.toHaveBeenCalled()
    })
  })

  it('uploads txt content directly without waiting for OCR confirmation', async () => {
    const onFileUpload = vi.fn()
    const onOcrReady = vi.fn()
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        source_type: 'txt',
        display_name: 'lease.txt',
        merged_text: '租赁合同正文',
        warnings: [],
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const { container } = renderDocPanel({}, { onFileUpload, onOcrReady })
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const txtFile = new File(['contract'], 'lease.txt', { type: 'text/plain' })

    fireEvent.change(fileInput, { target: { files: [txtFile] } })

    await waitFor(() => {
      expect(onFileUpload).toHaveBeenCalledWith('租赁合同正文', 'lease.txt')
      expect(onOcrReady).not.toHaveBeenCalled()
    })
  })

  it('renders editable OCR text and warnings before the review starts', () => {
    const onContractTextChange = vi.fn()
    const onConfirmReview = vi.fn()

    const { container, getByText } = renderDocPanel(
      {
        status: 'ocr_ready',
        filename: 'contract-photo.png',
        contractText: '甲方：张三\n乙方：李四',
        ocrWarnings: ['第 1 页 OCR 失败：vision OCR unavailable'],
      },
      {
        onContractTextChange,
        onConfirmReview,
      },
    )

    const textarea = container.querySelector('.doc-editor__textarea') as HTMLTextAreaElement
    const confirmButton = container.querySelector('.doc-panel__footer-right .px-btn--green') as HTMLButtonElement
    const zoomButtons = container.querySelectorAll('.doc-panel__zoom-btn')

    expect(textarea.value).toBe('甲方：张三\n乙方：李四')
    expect(getByText('第 1 页 OCR 失败：vision OCR unavailable')).not.toBeNull()
    expect(confirmButton.disabled).toBe(false)
    expect(container.querySelector('.doc-panel__zoom-level')?.textContent).toBe('100%')

    fireEvent.click(zoomButtons[1] as HTMLButtonElement)
    expect(container.querySelector('.doc-panel__zoom-level')?.textContent).toBe('110%')
    expect(textarea.style.fontSize).toBe('16.5px')

    fireEvent.change(textarea, { target: { value: '修订后的 OCR 文本' } })
    fireEvent.click(confirmButton)

    expect(onContractTextChange).toHaveBeenCalledWith('修订后的 OCR 文本')
    expect(onConfirmReview).toHaveBeenCalledTimes(1)
  })

  it('shows a new conversation button and calls back when clicked', () => {
    const onNewConversation = vi.fn()

    const { getAllByRole } = renderDocPanel(
      {
        status: 'complete',
        filename: 'test-contract.docx',
        contractText: 'Clause 1\nDeposit: 10400',
      },
      { onNewConversation },
    )

    fireEvent.click(getAllByRole('button', { name: /new conversation/i })[0])
    expect(onNewConversation).toHaveBeenCalledTimes(1)
  })

  it('highlights matched risk lines in the document viewer', () => {
    const { getAllByText } = renderDocPanel({
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
    })

    expect(getAllByText('Deposit: 10400').some((node) => node.className.includes('doc-highlight--high'))).toBe(true)
  })

  it('resets zoom when switching to another contract session', () => {
    const { container, rerender } = renderDocPanel({
      status: 'complete',
      sessionId: 'session-1',
      filename: 'first-contract.docx',
      contractText: 'Clause 1\nDeposit: 10400\n',
    })

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
        authToken="demo-token"
        onFileUpload={vi.fn()}
        onOcrReady={vi.fn()}
        onContractTextChange={vi.fn()}
        onConfirmReview={vi.fn()}
        onReset={vi.fn()}
      />,
    )

    expect(container.querySelector('.doc-panel__zoom-level')?.textContent).toBe('100%')
  })
})
