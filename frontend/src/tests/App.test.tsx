import { describe, expect, it } from 'vitest'
import { buildReportExportParagraphs, buildThinkingSteps, canExportReviewReport } from '../App'

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

  it('marks all steps as done after completion', () => {
    expect(buildThinkingSteps('complete', null, null).map((step) => step.status)).toEqual([
      'done',
      'done',
      'done',
      'done',
    ])
  })
})

describe('report export helpers', () => {
  it('builds a Word export payload for a completed unified scan', () => {
    const review = {
      status: 'complete',
      filename: '租赁合同.docx',
      finalReport: [],
      initialSummary: '合同分析已完成，识别到 1 处潜在风险。',
      deepUpdateNotice: '合同分析已完成。',
      riskCards: [
        {
          id: 'deposit',
          level: 'high',
          title: '押金条款',
          clause: '押金不予退还',
          issue: '提前退租时押金不退，责任过重。',
          suggestion: '建议明确按实际损失扣减，剩余押金退还。',
          legalRef: '《民法典》第585条',
          matchedText: '押金不予退还',
          changeType: 'none',
        },
      ],
    } as any

    const paragraphs = buildReportExportParagraphs(review)

    expect(canExportReviewReport(review)).toBe(true)
    expect(paragraphs[0]).toContain('合同审查报告')
    expect(paragraphs.join('\n')).toContain('押金条款')
    expect(paragraphs.join('\n')).not.toContain('深度扫描')
  })

  it('does not offer export before any scan result exists', () => {
    const review = {
      status: 'complete',
      filename: '租赁合同.docx',
      finalReport: [],
      initialSummary: null,
      deepUpdateNotice: null,
      riskCards: [],
    } as any

    expect(canExportReviewReport(review)).toBe(false)
    expect(buildReportExportParagraphs(review)).toEqual([])
  })
})
