import type { ComponentProps } from 'react'
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ReviewState } from '../App'
import { DocPanel } from '../components/DocPanel'
import { MAX_CONTRACT_IMAGE_BATCH } from '../lib/uploadLimits'

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) => (name.toLowerCase() === 'content-type' ? 'application/json' : null),
    },
    text: async () => JSON.stringify(payload),
  }
}

function buildReviewState(overrides: Partial<ReviewState> = {}): ReviewState {
  return {
    status: 'idle',
    reviewStage: 'idle',
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
    initialSummary: null,
    deepUpdateNotice: null,
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
    vi.stubGlobal('alert', vi.fn())
  })

  it('does not render a model selector in the upload state', () => {
    const { container } = renderDocPanel()
    expect(container.querySelector('.model-select')).toBeNull()
  })

  it('uploads multiple images through the OCR queue and waits for confirmation', async () => {
    const onFileUpload = vi.fn()
    const onOcrReady = vi.fn()
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/ocr/queue' && init?.method === 'POST') {
        return jsonResponse({
          task_id: 'ocr-task-images',
          status: 'pending',
          queue_position: 1,
          estimated_wait: '即将开始',
        })
      }

      if (url === '/api/ocr/queue/ocr-task-images') {
        return jsonResponse({
          status: 'completed',
          result: {
            source_type: 'image_batch',
            display_name: '合同照片 等 2 页图片',
            merged_text: '甲方：张三\n乙方：李四',
            warnings: ['第 2 页 OCR 失败：vision OCR unavailable'],
          },
        })
      }

      return jsonResponse({ error: 'unexpected request' }, 500)
    })
    vi.stubGlobal('fetch', fetchMock)

    const { container } = renderDocPanel({}, { authToken: 'demo-token', onFileUpload, onOcrReady })
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const imageFiles = [
      new File(['fake-image-1'], 'contract-1.png', { type: 'image/png' }),
      new File(['fake-image-2'], 'contract-2.png', { type: 'image/png' }),
    ]

    fireEvent.change(fileInput, { target: { files: imageFiles } })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenNthCalledWith(
        1,
        '/api/ocr/queue',
        expect.objectContaining({
          method: 'POST',
          headers: { Authorization: 'Bearer demo-token' },
          body: expect.any(FormData),
        }),
      )
      expect(fetchMock).toHaveBeenNthCalledWith(
        2,
        '/api/ocr/queue/ocr-task-images',
        expect.objectContaining({
          headers: { Authorization: 'Bearer demo-token' },
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

  it('uploads a PDF through the OCR queue and waits for OCR confirmation', async () => {
    const onFileUpload = vi.fn()
    const onOcrReady = vi.fn()
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/ocr/queue' && init?.method === 'POST') {
        return jsonResponse({
          task_id: 'ocr-task-pdf',
          status: 'pending',
          queue_position: 1,
          estimated_wait: '即将开始',
        })
      }

      if (url === '/api/ocr/queue/ocr-task-pdf') {
        return jsonResponse({
          status: 'completed',
          result: {
            source_type: 'pdf_ocr',
            display_name: 'lease.pdf',
            merged_text: '第一条 租赁用途\n第二条 租金',
            warnings: [],
          },
        })
      }

      return jsonResponse({ error: 'unexpected request' }, 500)
    })
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
    const fetchMock = vi.fn(async () => (
      jsonResponse({
        source_type: 'txt',
        display_name: 'lease.txt',
        merged_text: '租赁合同正文',
        warnings: [],
      })
    ))
    vi.stubGlobal('fetch', fetchMock)

    const { container } = renderDocPanel({}, { onFileUpload, onOcrReady })
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const txtFile = new File(['contract'], 'lease.txt', { type: 'text/plain' })

    fireEvent.change(fileInput, { target: { files: [txtFile] } })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/ocr/ingest',
        expect.objectContaining({
          method: 'POST',
          headers: { Authorization: 'Bearer demo-token' },
          body: expect.any(FormData),
        }),
      )
      expect(onFileUpload).toHaveBeenCalledWith('租赁合同正文', 'lease.txt')
      expect(onOcrReady).not.toHaveBeenCalled()
    })
  })



  it('blocks oversized image batches before calling the ingest endpoint', () => {
    const fetchMock = vi.fn()
    const alertMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('alert', alertMock)

    const { container } = renderDocPanel()
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const imageFiles = Array.from({ length: MAX_CONTRACT_IMAGE_BATCH + 1 }, (_, index) => (
      new File([`img-${index}`], `contract-${index + 1}.png`, { type: 'image/png' })
    ))

    fireEvent.change(fileInput, { target: { files: imageFiles } })

    expect(fetchMock).not.toHaveBeenCalled()
    expect(alertMock).toHaveBeenCalledTimes(1)
    expect(alertMock.mock.calls[0]?.[0]).toContain(String(MAX_CONTRACT_IMAGE_BATCH))
  })

  it('supports dragging files into the upload area', async () => {
    const onOcrReady = vi.fn()
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/ocr/queue' && init?.method === 'POST') {
        return jsonResponse({
          task_id: 'ocr-task-drag',
          status: 'pending',
          queue_position: 1,
          estimated_wait: '即将开始',
        })
      }

      if (url === '/api/ocr/queue/ocr-task-drag') {
        return jsonResponse({
          status: 'completed',
          result: {
            source_type: 'image_batch',
            display_name: 'dragged-photo.png',
            merged_text: '拖拽上传识别结果',
            warnings: [],
          },
        })
      }

      return jsonResponse({ error: 'unexpected request' }, 500)
    })
    vi.stubGlobal('fetch', fetchMock)

    const { container } = renderDocPanel({}, { onOcrReady })
    const uploadArea = container.querySelector('.upload-area') as HTMLDivElement
    const imageFile = new File(['fake-image'], 'dragged-photo.png', { type: 'image/png' })

    fireEvent.dragOver(uploadArea, {
      dataTransfer: {
        files: [imageFile],
        dropEffect: 'copy',
      },
    })
    fireEvent.drop(uploadArea, {
      dataTransfer: {
        files: [imageFile],
      },
    })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenNthCalledWith(
        1,
        '/api/ocr/queue',
        expect.objectContaining({
          method: 'POST',
          headers: { Authorization: 'Bearer demo-token' },
          body: expect.any(FormData),
        }),
      )
      expect(fetchMock).toHaveBeenNthCalledWith(
        2,
        '/api/ocr/queue/ocr-task-drag',
        expect.objectContaining({
          headers: { Authorization: 'Bearer demo-token' },
        }),
      )
      expect(onOcrReady).toHaveBeenCalledWith('拖拽上传识别结果', 'dragged-photo.png', [])
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
    const confirmButton = getByText('深度扫描') as HTMLButtonElement
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
    expect(onConfirmReview).toHaveBeenCalledWith('deep')
  })

  it('lets the user choose light scan from the confirmation footer', () => {
    const onConfirmReview = vi.fn()

    const { getByRole } = renderDocPanel(
      {
        status: 'ocr_ready',
        filename: 'lease.txt',
        contractText: '绉熻祦鍚堝悓姝ｆ枃',
      },
      {
        onConfirmReview,
      },
    )

    fireEvent.click(getByRole('button', { name: /轻度扫描/i }))
    expect(onConfirmReview).toHaveBeenCalledWith('light')
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

  it('hides OCR-derived contract content after deep review completes', () => {
    const { container, getAllByText, getByText, queryByText } = renderDocPanel({
      status: 'complete',
      reviewStage: 'complete',
      documentSource: 'ocr',
      filename: 'contract-photo.png',
      contractText: '甲方：张三\n乙方：李四\n租金：5000元',
      finalReport: ['## Review summary', 'Complete report body'],
    })

    expect(getAllByText('深度扫描已完成').length).toBeGreaterThan(0)
    expect(getByText('原始照片识别内容已自动收起，当前保留完整审查报告与问答结果。')).toBeTruthy()
    expect(queryByText('甲方：张三')).toBeNull()
    expect(container.querySelector('.doc-panel__zoom-group')).toBeNull()
  })

  it('shows the export report action to the left of new conversation when a report is ready', () => {
    const onExportReport = vi.fn()
    const onNewConversation = vi.fn()

    const { getByRole, container } = renderDocPanel(
      {
        status: 'complete',
        reviewStage: 'complete',
        filename: 'test-contract.docx',
        contractText: 'Clause 1\nDeposit: 10400',
        finalReport: ['## Review summary', 'Complete report body'],
      },
      {
        canExportReport: true,
        onExportReport,
        onNewConversation,
      },
    )

    const exportButton = getByRole('button', { name: /导出报告/i })
    const newConversationButton = getByRole('button', { name: /new conversation/i })
    const toolbarButtons = Array.from(container.querySelectorAll('.doc-panel__toolbar-right button'))

    expect(toolbarButtons.indexOf(exportButton)).toBeLessThan(toolbarButtons.indexOf(newConversationButton))

    fireEvent.click(exportButton)
    expect(onExportReport).toHaveBeenCalledTimes(1)
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
          changeType: 'none',
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
