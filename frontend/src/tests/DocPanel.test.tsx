import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DocPanel } from '../components/DocPanel'
import type { ReviewState } from '../App'
import { DEMO_CONTRACT_FILENAME } from '../lib/demoContract'

function buildReviewState(overrides: Partial<ReviewState> = {}): ReviewState {
  return {
    status: 'idle',
    sessionId: 'session-1',
    contractText: '',
    filename: '',
    thinkingSteps: [
      { id: 'parse', label: '解析合同主体信息', status: 'pending' },
      { id: 'extract', label: '提取关键条款变量', status: 'pending' },
      { id: 'retrieve', label: '检索相关法律依据', status: 'pending' },
      { id: 'review', label: '扫描风险项', status: 'pending' },
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
  it('loads the built-in sample contract', () => {
    const onFileUpload = vi.fn()

    render(<DocPanel review={buildReviewState()} onFileUpload={onFileUpload} />)

    fireEvent.click(screen.getByRole('button', { name: /加载示例/ }))

    expect(onFileUpload).toHaveBeenCalledWith(expect.stringContaining('租赁合同'), DEMO_CONTRACT_FILENAME)
  })

  it('highlights matched risk lines in the document viewer', () => {
    render(
      <DocPanel
        review={buildReviewState({
          status: 'complete',
          filename: '测试合同.docx',
          contractText: '第一条 合同主体\n押金：人民币 5600 元\n违约金：合同总额的200%\n',
          riskCards: [
            {
              id: '1',
              level: 'high',
              title: '押金条款',
              clause: '押金条款',
              issue: '押金过高',
              suggestion: '降低押金',
              legalRef: '《民法典》第585条',
              matchedText: '押金：人民币 5600 元',
            },
          ],
        })}
        onFileUpload={vi.fn()}
      />,
    )

    expect(screen.getByText('押金：人民币 5600 元').className).toContain('doc-paper__highlight-line--high')
  })
})
