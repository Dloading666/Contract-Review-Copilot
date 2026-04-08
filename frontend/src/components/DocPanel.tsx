import { useCallback, useRef, useState } from 'react'
import mammoth from 'mammoth'
import { ZoomIn, ZoomOut, Download, Menu, Upload, Eye } from 'lucide-react'
import type { ReviewState, RiskCard } from '../App'
import { DEMO_CONTRACT_FILENAME, DEMO_CONTRACT_TEXT } from '../lib/demoContract'

interface DocPanelProps {
  review: ReviewState
  onFileUpload: (text: string, filename: string) => void
  onExportReport?: () => void
}

const RISK_KEYWORDS = [
  '押金', '保证金', '违约金', '违约', '解约', '解除', '提前解除',
  '提前退租', '退租', '逾期', '滞纳金', '利息', '转租', '二房东',
  '租金贷', '服务费', '管理费', '维修', '免责', '中介费', '水电', '返还', '续租', '通知',
]

function normalizeText(text?: string | null) {
  return (text || '').replace(/[\s\u3000，。、《》"""'：:；;（）()【】[\]、-]/g, '')
}

function buildRiskKeywords(risk: RiskCard) {
  const sourceText = [risk.clause, risk.issue, risk.suggestion].join(' ')
  const keywords = new Set<string>()
  if (risk.matchedText?.trim()) keywords.add(risk.matchedText.trim())
  for (const keyword of RISK_KEYWORDS) {
    if (sourceText.includes(keyword)) keywords.add(keyword)
  }
  if (risk.clause && !['整体评估', '风险评估'].includes(risk.clause)) keywords.add(risk.clause)
  return [...keywords].filter(k => k.trim().length >= 2)
}

function matchRiskToLine(line: string, risk: RiskCard) {
  const trimmedLine = line.trim()
  if (!trimmedLine) return false
  const normalizedLine = normalizeText(trimmedLine)
  const normalizedMatchedText = normalizeText(risk.matchedText)
  if (normalizedMatchedText && (normalizedLine.includes(normalizedMatchedText) || normalizedMatchedText.includes(normalizedLine))) return true
  const score = buildRiskKeywords(risk).reduce((total, keyword) => {
    const nk = normalizeText(keyword)
    return nk && normalizedLine.includes(nk) ? total + Math.max(nk.length, 2) : total
  }, 0)
  return score >= 2
}

function getLineMatches(line: string, riskCards: RiskCard[]) {
  return riskCards
    .filter(risk => matchRiskToLine(line, risk))
    .sort((a, b) => a.level === b.level ? 0 : a.level === 'high' ? -1 : 1)
}

export function DocPanel({ review, onFileUpload, onExportReport }: DocPanelProps) {
  const [zoom, setZoom] = useState(100)

  const isEmpty = review.status === 'idle'
  const contractText = review.contractText
  const riskCards: RiskCard[] = review.riskCards || []

  const handleDownload = useCallback(() => {
    if (!contractText) return
    const blob = new Blob([contractText], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = review.filename || '合同文本.txt'
    anchor.click()
    URL.revokeObjectURL(url)
  }, [contractText, review.filename])

  const renderContractContent = () => {
    const lines = contractText.split('\n')
    return lines.map((line, index) => {
      const trimmedLine = line.trim()
      if (!trimmedLine) return <br key={index} />

      const matchedRisks = getLineMatches(line, riskCards)
      const primaryRisk = matchedRisks[0]
      const lineTitle = matchedRisks.map(r => `${r.title}：${r.issue}`).join('\n')

      if (/^第[一二三四五六七八九十\d]+条/.test(trimmedLine) || /^[一二三四五六七八九十\d]+、/.test(trimmedLine)) {
        return (
          <h4
            key={index}
            className={`doc-clause-title${primaryRisk ? ` doc-highlight--${primaryRisk.level}` : ''}`}
            title={lineTitle || undefined}
          >
            {line}
          </h4>
        )
      }

      if (/^(甲方|乙方|出租方|承租方)/.test(trimmedLine)) {
        return (
          <p
            key={index}
            className={`doc-party-line${primaryRisk ? ` doc-highlight--${primaryRisk.level}` : ''}`}
            title={lineTitle || undefined}
          >
            {line}
          </p>
        )
      }

      if (primaryRisk) {
        return (
          <p
            key={index}
            className={`doc-highlight--${primaryRisk.level}`}
            title={lineTitle || undefined}
          >
            {line}
          </p>
        )
      }

      return <p key={index} className="doc-line">{line}</p>
    })
  }

  return (
    <section className="doc-panel">
      {/* Toolbar */}
      <div className="doc-panel__toolbar">
        <div className="doc-panel__toolbar-left">
          <button className="doc-panel__icon-btn" title="文档菜单">
            <Menu size={16} />
          </button>
          <span className="doc-panel__filename">
            {review.filename || '等待上传合同'}
          </span>
        </div>
        <div className="doc-panel__toolbar-right">
          {!isEmpty && (
            <>
              <div className="doc-panel__zoom-group">
                <button
                  className="doc-panel__zoom-btn"
                  onClick={() => setZoom(v => Math.max(50, v - 10))}
                  title="缩小"
                >
                  <ZoomOut size={14} />
                </button>
                <span className="doc-panel__zoom-level">{zoom}%</span>
                <button
                  className="doc-panel__zoom-btn"
                  onClick={() => setZoom(v => Math.min(200, v + 10))}
                  title="放大"
                >
                  <ZoomIn size={14} />
                </button>
              </div>
              <button
                className="doc-panel__icon-btn"
                onClick={handleDownload}
                title="下载合同"
              >
                <Download size={16} />
              </button>
              {onExportReport && review.finalReport.length > 0 && (
                <button
                  className="px-btn px-btn--sm px-btn--orange"
                  onClick={onExportReport}
                  title="导出报告"
                >
                  导出报告
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="doc-panel__content">
        {isEmpty ? (
          <UploadArea onFileUpload={onFileUpload} />
        ) : (
          <div className="doc-paper" style={{ fontSize: `${zoom}%` }}>
            <div>{renderContractContent()}</div>
            <div className="doc-paper__watermark">
              <span className="doc-paper__watermark-text">CONFIDENTIAL LEGAL DOCUMENT</span>
              <span className="doc-paper__watermark-text">CONFIDENTIAL LEGAL DOCUMENT</span>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      {!isEmpty && (
        <div className="doc-panel__footer">
          <div className="doc-panel__footer-left">
            <span>字数：{contractText.length.toLocaleString()}</span>
            {riskCards.length > 0 && (
              <span style={{ color: 'var(--color-red)' }}>
                {riskCards.filter(c => c.level === 'high').length} 处高危 ·{' '}
                {riskCards.filter(c => c.level === 'medium').length} 处提示
              </span>
            )}
          </div>
          <div className="doc-panel__footer-right">
            <span className="doc-panel__footer-dot" />
            <span>已加载</span>
            <span style={{ color: 'var(--color-ink-muted)' }}>智审内核 V4.2.0</span>
          </div>
        </div>
      )}
    </section>
  )
}

interface UploadAreaProps {
  onFileUpload: (text: string, filename: string) => void
}

function UploadArea({ onFileUpload }: UploadAreaProps) {
  const hiddenFileInput = useRef<HTMLInputElement>(null)

  const handleUploadClick = () => hiddenFileInput.current?.click()

  const handleLoadSample = () => onFileUpload(DEMO_CONTRACT_TEXT, DEMO_CONTRACT_FILENAME)

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    const filename = file.name
    const extension = filename.split('.').pop()?.toLowerCase()
    try {
      let text = ''
      if (extension === 'txt') {
        text = await file.text()
      } else if (extension === 'docx') {
        const arrayBuffer = await file.arrayBuffer()
        const result = await mammoth.extractRawText({ arrayBuffer })
        text = result.value
      } else if (extension === 'doc') {
        alert('旧版 .doc 暂不支持直接解析，请先另存为 .docx 后再上传。')
        return
      } else if (extension === 'pdf') {
        alert('PDF 暂不支持，请将合同另存为 .docx 或 .txt 后再上传。')
        return
      } else {
        text = await file.text()
      }
      if (text.trim().length < 10) { alert('合同内容为空或过短，请检查文件是否正确。'); return }
      onFileUpload(text, filename)
    } catch (error) {
      console.error('File read error:', error)
      alert('文件读取失败，请尝试将合同另存为 .txt 格式后重新上传。')
    } finally {
      event.target.value = ''
    }
  }

  return (
    <div className="upload-area">
      {/* Pixel document icon */}
      <div className="upload-area__frame">
        <div className="upload-area__doc-icon">
          <div className="upload-area__doc-line" />
          <div className="upload-area__doc-line upload-area__doc-line--short" />
          <div className="upload-area__doc-line" />
          <div className="upload-area__doc-line upload-area__doc-line--short" />
          <div className="upload-area__doc-line" />
        </div>
      </div>

      <div className="upload-area__title">
        上传合同<br />文档
      </div>

      <p className="upload-area__desc">
        支持 .txt、.docx 格式<br />
        系统将自动扫描潜在风险条款
      </p>

      <div className="upload-area__actions">
        <button className="px-btn px-btn--blue" style={{ width: '100%' }} onClick={handleUploadClick}>
          <Upload size={14} />
          选择文件
        </button>
        <button className="px-btn px-btn--ghost" style={{ width: '100%' }} onClick={handleLoadSample}>
          <Eye size={14} />
          加载示例
        </button>
      </div>

      <input
        ref={hiddenFileInput}
        type="file"
        accept=".txt,.docx"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />
    </div>
  )
}
