import { useCallback, useRef, useState } from 'react'
import mammoth from 'mammoth'
import type { ReviewState, RiskCard } from '../App'
import { DEMO_CONTRACT_FILENAME, DEMO_CONTRACT_TEXT } from '../lib/demoContract'

interface DocPanelProps {
  review: ReviewState
  onFileUpload: (text: string, filename: string) => void
}

const RISK_KEYWORDS = [
  '押金',
  '保证金',
  '违约金',
  '违约',
  '解约',
  '解除',
  '提前解除',
  '提前退租',
  '退租',
  '逾期',
  '滞纳金',
  '利息',
  '转租',
  '二房东',
  '租金贷',
  '服务费',
  '管理费',
  '维修',
  '免责',
  '中介费',
  '水电',
  '返还',
  '续租',
  '通知',
]

function normalizeText(text?: string | null) {
  return (text || '').replace(/[\s\u3000，。、《》“”"'：:；;（）()【】\[\]、-]/g, '')
}

function buildRiskKeywords(risk: RiskCard) {
  const sourceText = [risk.clause, risk.issue, risk.suggestion].join(' ')
  const keywords = new Set<string>()

  if (risk.matchedText?.trim()) {
    keywords.add(risk.matchedText.trim())
  }

  for (const keyword of RISK_KEYWORDS) {
    if (sourceText.includes(keyword)) {
      keywords.add(keyword)
    }
  }

  if (risk.clause && !['整体评估', '风险评估'].includes(risk.clause)) {
    keywords.add(risk.clause)
  }

  return [...keywords].filter((keyword) => keyword.trim().length >= 2)
}

function matchRiskToLine(line: string, risk: RiskCard) {
  const trimmedLine = line.trim()
  if (!trimmedLine) return false

  const normalizedLine = normalizeText(trimmedLine)
  const normalizedMatchedText = normalizeText(risk.matchedText)

  if (
    normalizedMatchedText
    && (normalizedLine.includes(normalizedMatchedText) || normalizedMatchedText.includes(normalizedLine))
  ) {
    return true
  }

  const score = buildRiskKeywords(risk).reduce((total, keyword) => {
    const normalizedKeyword = normalizeText(keyword)
    return normalizedKeyword && normalizedLine.includes(normalizedKeyword)
      ? total + Math.max(normalizedKeyword.length, 2)
      : total
  }, 0)

  return score >= 2
}

function getLineMatches(line: string, riskCards: RiskCard[]) {
  return riskCards
    .filter((risk) => matchRiskToLine(line, risk))
    .sort((left, right) => {
      if (left.level === right.level) return 0
      return left.level === 'high' ? -1 : 1
    })
}

export function DocPanel({ review, onFileUpload }: DocPanelProps) {
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
      const highlightClassName = primaryRisk
        ? ` doc-paper__highlight-line doc-paper__highlight-line--${primaryRisk.level}`
        : ''
      const lineTitle = matchedRisks.map((risk) => `${risk.title}：${risk.issue}`).join('\n')

      if (
        /^第[一二三四五六七八九十\d]+条/.test(trimmedLine)
        || /^[一二三四五六七八九十\d]+、/.test(trimmedLine)
      ) {
        return (
          <h4
            key={index}
            className={`doc-paper__clause-title${highlightClassName}`}
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
            className={`doc-paper__party-line${highlightClassName}`}
            title={lineTitle || undefined}
          >
            {line}
          </p>
        )
      }

      return (
        <p key={index} className={primaryRisk ? highlightClassName.trim() : undefined} title={lineTitle || undefined}>
          {line}
        </p>
      )
    })
  }

  return (
    <section className="doc-panel">
      <div className="doc-panel__toolbar">
        <div className="doc-panel__toolbar-left">
          <span className="material-symbols-outlined doc-panel__toolbar-icon">menu</span>
          <h3 className="doc-panel__filename">{review.filename || '等待上传合同'}</h3>
        </div>
        <div className="doc-panel__toolbar-right">
          {!isEmpty && (
            <>
              <div className="doc-panel__zoom">
                <button className="doc-panel__zoom-btn" onClick={() => setZoom((value) => Math.max(50, value - 10))}>
                  <span className="material-symbols-outlined">zoom_out</span>
                </button>
                <span className="doc-panel__zoom-level">{zoom}%</span>
                <button className="doc-panel__zoom-btn" onClick={() => setZoom((value) => Math.min(200, value + 10))}>
                  <span className="material-symbols-outlined">zoom_in</span>
                </button>
              </div>
              <button
                className="material-symbols-outlined doc-panel__toolbar-icon"
                onClick={handleDownload}
                title="下载合同"
              >
                download
              </button>
            </>
          )}
        </div>
      </div>

      <div className="doc-panel__content">
        {isEmpty ? (
          <UploadArea onFileUpload={onFileUpload} />
        ) : (
          <div className="doc-paper" style={{ fontSize: `${zoom}%` }}>
            <div className="doc-paper__contract-text">{renderContractContent()}</div>
            <div className="doc-paper__watermark">
              <span className="doc-paper__watermark-text">CONFIDENTIAL LEGAL DOCUMENT</span>
              <span className="doc-paper__watermark-text" style={{ top: '65%' }}>
                CONFIDENTIAL LEGAL DOCUMENT
              </span>
            </div>
          </div>
        )}
      </div>

      {!isEmpty && (
        <div className="doc-panel__footer">
          <div className="doc-panel__footer-left">
            <span>字数: {contractText.length.toLocaleString()}</span>
            {riskCards.length > 0 && (
              <span style={{ color: 'var(--error)', marginLeft: 12 }}>
                {riskCards.filter((card) => card.level === 'high').length}处高危 ·{' '}
                {riskCards.filter((card) => card.level === 'medium').length}处提示
              </span>
            )}
          </div>
          <div className="doc-panel__footer-right">
            <div className="doc-panel__footer-status">
              <span className="doc-panel__footer-dot" />
              <span>已加载</span>
            </div>
            <span>智审内核 V4.2.0</span>
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

  const handleUploadClick = () => {
    hiddenFileInput.current?.click()
  }

  const handleLoadSample = () => {
    onFileUpload(DEMO_CONTRACT_TEXT, DEMO_CONTRACT_FILENAME)
  }

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

      if (text.trim().length < 10) {
        alert('合同内容为空或过短，请检查文件是否正确。')
        return
      }

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
      <div className="upload-area__icon">
        <span className="material-symbols-outlined" style={{ fontSize: 64, opacity: 0.5 }}>
          description
        </span>
      </div>
      <h2 className="upload-area__title">上传合同文档</h2>
      <p className="upload-area__desc">
        支持 .txt、.docx 格式的合同文件
        <br />
        系统将自动分析合同中的潜在风险条款
      </p>
      <div className="upload-area__actions upload-area__actions--centered">
        <button className="upload-area__btn upload-area__btn--primary" onClick={handleUploadClick}>
          <span className="material-symbols-outlined">upload</span>
          选择文件
        </button>
        <button className="upload-area__btn upload-area__btn--secondary" onClick={handleLoadSample}>
          <span className="material-symbols-outlined">visibility</span>
          加载示例
        </button>
      </div>
      <input
        ref={hiddenFileInput}
        type="file"
        accept=".txt,.docx"
        className="upload-area__input"
        onChange={handleFileChange}
      />
    </div>
  )
}
