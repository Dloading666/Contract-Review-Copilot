import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Download, Plus, Upload, ZoomIn, ZoomOut } from 'lucide-react'
import type { ReviewState, RiskCard } from '../App'
import type { User } from '../contexts/AuthContext'

interface DocPanelProps {
  review: ReviewState
  authToken?: string | null
  currentUser?: User | null
  onOpenRecharge?: () => void
  onFileUpload: (text: string, filename: string) => void
  onOcrReady: (text: string, filename: string, warnings?: string[]) => void
  onContractTextChange: (text: string) => void
  onConfirmReview: () => void
  onReset: () => void
  onNewConversation?: () => void
}

interface OcrIngestResponse {
  source_type?: unknown
  display_name?: unknown
  merged_text?: unknown
  warnings?: unknown
  error?: unknown
  detail?: unknown
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
  '租金',
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

const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'webp'])
const SUPPORTED_EXTENSIONS = new Set(['txt', 'docx', 'pdf', ...IMAGE_EXTENSIONS])

function normalizeText(text?: string | null) {
  return (text || '').replace(/[\s\u3000，。、“”‘’！？；：（）()\[\]【】]/g, '')
}

function getFileExtension(filename: string) {
  return filename.split('.').pop()?.toLowerCase() ?? ''
}

function isImageFilename(filename: string) {
  return IMAGE_EXTENSIONS.has(getFileExtension(filename))
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
    && (
      normalizedLine.includes(normalizedMatchedText)
      || normalizedMatchedText.includes(normalizedLine)
    )
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
    .sort((a, b) => (a.level === b.level ? 0 : a.level === 'high' ? -1 : 1))
}

function isNoRiskPlaceholderCard(card: RiskCard) {
  const summaryText = `${card.title} ${card.clause}`.toLowerCase()
  const issueText = `${card.issue} ${card.suggestion}`
  return (
    (summaryText.includes('整体评估') || summaryText.includes('风险评估'))
    && (
      issueText.includes('未发现明显不公平条款')
      || issueText.includes('合同条款基本公平合理')
      || issueText.includes('未发现明显不公平')
    )
  )
}

function buildDownloadFilename(filename: string) {
  if (!filename) {
    return '合同文本.txt'
  }

  const extension = getFileExtension(filename)
  if (extension) {
    return filename.replace(/\.[^.]+$/, '.txt')
  }

  return `${filename}.txt`
}

function extractWarnings(payload: OcrIngestResponse) {
  return Array.isArray(payload.warnings)
    ? payload.warnings.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : []
}

function buildUploadProgressText(files: File[]) {
  if (files.length === 0) {
    return '正在导入合同内容...'
  }

  if (files.length > 1 && files.every((file) => isImageFilename(file.name))) {
    return `正在按顺序识别 ${files.length} 张合同图片，并用 Kimi 校对文字...`
  }

  const extension = getFileExtension(files[0].name)
  if (IMAGE_EXTENSIONS.has(extension)) {
    return '正在识别合同图片，并用 Kimi 校对文字...'
  }

  if (extension === 'pdf') {
    return '正在解析 PDF；如为扫描件，会逐页识别并用 Kimi 校对...'
  }

  return '正在导入合同内容...'
}

export function DocPanel({
  review,
  authToken,
  currentUser,
  onOpenRecharge,
  onFileUpload,
  onOcrReady,
  onContractTextChange,
  onConfirmReview,
  onReset,
  onNewConversation,
}: DocPanelProps) {
  const [zoom, setZoom] = useState(100)

  useEffect(() => {
    setZoom(100)
  }, [review.sessionId, review.filename])

  const isEmpty = review.status === 'idle'
  const isOcrReady = review.status === 'ocr_ready'
  const contractText = review.contractText
  const ocrWarnings = review.ocrWarnings ?? []
  const riskCards = useMemo(
    () => (review.riskCards || []).filter((card) => !isNoRiskPlaceholderCard(card)),
    [review.riskCards],
  )

  const handleDownload = useCallback(() => {
    if (!contractText) return

    const blob = new Blob([contractText], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = buildDownloadFilename(review.filename)
    anchor.click()
    URL.revokeObjectURL(url)
  }, [contractText, review.filename])

  const renderContractContent = () => {
    const lines = contractText.split('\n')

    return lines.map((line, index) => {
      const trimmedLine = line.trim()
      if (!trimmedLine) {
        return <br key={index} />
      }

      const matchedRisks = getLineMatches(line, riskCards)
      const primaryRisk = matchedRisks[0]
      const lineTitle = matchedRisks.map((risk) => `${risk.title}：${risk.issue}`).join('\n')

      if (/^第[一二三四五六七八九十百千\d]+条/.test(trimmedLine) || /^[一二三四五六七八九十百千\d]+、/.test(trimmedLine)) {
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

      return (
        <p key={index} className="doc-line">
          {line}
        </p>
      )
    })
  }

  return (
    <section className="doc-panel">
      <div className="doc-panel__toolbar">
        <div className="doc-panel__toolbar-left">
          <span className="doc-panel__filename">{review.filename || '等待上传合同'}</span>
        </div>

        <div className="doc-panel__toolbar-right">
          {!isEmpty && (
            <>
              {onNewConversation && (
                <button
                  className="px-btn px-btn--sm px-btn--ghost"
                  aria-label="new conversation"
                  onClick={onNewConversation}
                  title="新建对话"
                >
                  <Plus size={14} />
                  新建对话
                </button>
              )}

              {!isOcrReady && (
                <div className="doc-panel__zoom-group">
                  <button
                    className="doc-panel__zoom-btn"
                    onClick={() => setZoom((value) => Math.max(50, value - 10))}
                    title="缩小"
                  >
                    <ZoomOut size={14} />
                  </button>
                  <span className="doc-panel__zoom-level">{zoom}%</span>
                  <button
                    className="doc-panel__zoom-btn"
                    onClick={() => setZoom((value) => Math.min(200, value + 10))}
                    title="放大"
                  >
                    <ZoomIn size={14} />
                  </button>
                </div>
              )}

              <button
                className="doc-panel__icon-btn"
                onClick={handleDownload}
                title="下载合同文本"
              >
                <Download size={16} />
              </button>
            </>
          )}
        </div>
      </div>

      <div className="doc-panel__content">
        {isEmpty ? (
          <UploadArea
            authToken={authToken}
            currentUser={currentUser}
            onOpenRecharge={onOpenRecharge}
            onFileUpload={onFileUpload}
            onOcrReady={onOcrReady}
          />
        ) : isOcrReady ? (
          <div className="doc-paper doc-paper--editable">
            <div className="doc-editor__heading">合同识别结果</div>
            <p className="doc-editor__hint">
              识别结果已经回填到右侧文档区。请先检查并修正错字、漏字或页序问题，再点击“确认并开始分析”。
            </p>
            {ocrWarnings.length > 0 && (
              <div className="doc-editor__warnings" role="status" aria-live="polite">
                {ocrWarnings.map((warning, index) => (
                  <p key={`${warning}-${index}`} className="doc-editor__warning-line">
                    {warning}
                  </p>
                ))}
              </div>
            )}
            <textarea
              className="doc-editor__textarea"
              value={contractText}
              onChange={(event) => onContractTextChange(event.target.value)}
              spellCheck={false}
            />
          </div>
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

      {!isEmpty && (
        <div className="doc-panel__footer">
          <div className="doc-panel__footer-left">
            {isOcrReady ? (
              <>
                <span>已识别 {contractText.length.toLocaleString()} 个字符</span>
                {ocrWarnings.length > 0 && (
                  <span style={{ color: 'var(--color-orange)' }}>
                    {ocrWarnings.length} 条识别提醒待检查
                  </span>
                )}
              </>
            ) : (
              <>
                <span>字数：{contractText.length.toLocaleString()}</span>
                {riskCards.length > 0 && (
                  <span style={{ color: 'var(--color-red)' }}>
                    {riskCards.filter((card) => card.level === 'high').length} 处高危 ·{' '}
                    {riskCards.filter((card) => card.level === 'medium').length} 处提示
                  </span>
                )}
              </>
            )}
          </div>

          <div className="doc-panel__footer-right">
            {isOcrReady ? (
              <>
                <button className="px-btn px-btn--sm px-btn--ghost" onClick={onReset}>
                  重新上传
                </button>
                <button
                  className="px-btn px-btn--sm px-btn--green"
                  onClick={onConfirmReview}
                  disabled={!contractText.trim()}
                >
                  确认并开始分析
                </button>
              </>
            ) : (
              <>
                <span className="doc-panel__footer-dot" />
                <span>已加载</span>
                <span style={{ color: 'var(--color-ink-muted)' }}>智审内核 Kimi K2.5</span>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

interface UploadAreaProps {
  authToken?: string | null
  currentUser?: User | null
  onOpenRecharge?: () => void
  onFileUpload: (text: string, filename: string) => void
  onOcrReady: (text: string, filename: string, warnings?: string[]) => void
}

function UploadArea({
  authToken,
  currentUser,
  onOpenRecharge,
  onFileUpload,
  onOcrReady,
}: UploadAreaProps) {
  const hiddenFileInput = useRef<HTMLInputElement>(null)
  const [isProcessingFile, setIsProcessingFile] = useState(false)
  const [processingText, setProcessingText] = useState('')

  const handleUploadClick = () => hiddenFileInput.current?.click()

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    if (files.length === 0) return

    const unsupportedFile = files.find((file) => !SUPPORTED_EXTENSIONS.has(getFileExtension(file.name)))
    if (unsupportedFile) {
      alert(`暂不支持 ${unsupportedFile.name} 这种文件格式，请上传 TXT、DOCX、PDF 或合同图片。`)
      event.target.value = ''
      return
    }

    if (files.length > 1 && !files.every((file) => isImageFilename(file.name))) {
      alert('一次仅支持批量上传多张合同图片；TXT、DOCX、PDF 请单独上传。')
      event.target.value = ''
      return
    }

    try {
      setIsProcessingFile(true)
      setProcessingText(buildUploadProgressText(files))

      const formData = new FormData()
      files.forEach((file) => formData.append('files', file))

      const response = await fetch('/api/ocr/ingest', {
        method: 'POST',
        headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
        body: formData,
      })

      const payload = await response.json() as OcrIngestResponse
      if (!response.ok) {
        throw new Error(
          (typeof payload.error === 'string' && payload.error)
          || (typeof payload.detail === 'string' && payload.detail)
          || '合同导入失败，请稍后重试。',
        )
      }

      const mergedText = typeof payload.merged_text === 'string' ? payload.merged_text : ''
      if (!mergedText.trim()) {
        throw new Error('未提取到可用的合同文本，请检查文件是否清晰完整。')
      }

      const displayName = typeof payload.display_name === 'string' && payload.display_name.trim()
        ? payload.display_name
        : files[0].name
      const sourceType = typeof payload.source_type === 'string' ? payload.source_type : ''
      const warnings = extractWarnings(payload)

      if (sourceType === 'image_batch' || sourceType === 'pdf_ocr') {
        onOcrReady(mergedText, displayName, warnings)
      } else {
        onFileUpload(mergedText, displayName)
      }
    } catch (error) {
      console.error('File ingest error:', error)
      const message = error instanceof Error ? error.message : '文件导入失败，请稍后重试。'
      alert(message)
    } finally {
      setIsProcessingFile(false)
      setProcessingText('')
      event.target.value = ''
    }
  }

  return (
    <div className="upload-area">
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
        上传合同
        <br />
        文档或照片
      </div>

      <p className="upload-area__desc">
        支持 `.txt`、`.docx`、`.pdf`、`.jpg`、`.png`、`.webp`
        <br />
        可一次选择多张合同照片，系统会按选择顺序识别，再由你确认后开始分析
      </p>

      {currentUser && (
        <div className="upload-area__account">
          <div className="upload-area__account-title">权益摘要</div>
          <div className="upload-area__account-grid">
            <div>
              <strong>{currentUser.freeReviewRemaining}</strong>
              <span>剩余免费完整审查</span>
            </div>
            <div>
              <strong>¥{(currentUser.walletBalanceFen / 100).toFixed(currentUser.walletBalanceFen % 100 === 0 ? 0 : 2)}</strong>
              <span>钱包余额</span>
            </div>
            <div>
              <strong>¥1</strong>
              <span>本次审查价格</span>
            </div>
          </div>
          <p className="upload-area__account-hint">
            {!currentUser.phoneVerified
              ? '当前账户尚未绑定手机号，绑定后才能启动完整审查。'
              : currentUser.freeReviewRemaining > 0 || currentUser.walletBalanceFen >= 100
                ? '当前账户可直接开始完整审查。'
                : '免费次数已用完且钱包余额不足 1 元，请先充值。'}
          </p>
          {currentUser.phoneVerified && currentUser.freeReviewRemaining <= 0 && currentUser.walletBalanceFen < 100 && (
            <button type="button" className="px-btn px-btn--orange upload-area__recharge-btn" onClick={onOpenRecharge}>
              先去充值
            </button>
          )}
        </div>
      )}

      <div className="upload-area__actions">
        <button
          className="px-btn px-btn--blue"
          style={{ width: '100%' }}
          onClick={handleUploadClick}
          disabled={isProcessingFile}
        >
          <Upload size={14} />
          {isProcessingFile ? '导入中...' : '选择文件'}
        </button>
      </div>

      {processingText && (
        <p className="upload-area__status" role="status" aria-live="polite">
          {processingText}
        </p>
      )}

      <input
        ref={hiddenFileInput}
        type="file"
        accept=".txt,.docx,.pdf,.jpg,.jpeg,.png,.webp"
        multiple
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />
    </div>
  )
}
