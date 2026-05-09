import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { Download, Plus, Upload, ZoomIn, ZoomOut } from 'lucide-react'
import type { ReviewState, RiskCard } from '../App'
import { APIError, safeFetchJSON } from '../lib/apiClient'
import { apiPath } from '../lib/apiPaths'
import { MAX_CONTRACT_IMAGE_BATCH, MAX_CONTRACT_UPLOAD_FILE_BYTES, formatUploadBytes } from '../lib/uploadLimits'
interface DocPanelProps {
  review: ReviewState
  authToken?: string | null
  canExportReport?: boolean
  onExportReport?: () => void
  isExportingReport?: boolean
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

interface OcrQueueCreateResponse {
  task_id?: unknown
  status?: unknown
  queue_position?: unknown
  estimated_wait?: unknown
}

interface OcrQueueStatusResponse {
  status?: unknown
  progress_message?: unknown
  last_error?: unknown
  error_code?: unknown
  result?: unknown
}

const OCR_QUEUE_POLL_INTERVAL_MS = 800
const OCR_QUEUE_MAX_POLLS = 150

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

function buildUploadValidationMessage(files: File[]) {
  const oversizedFile = files.find((file) => file.size > MAX_CONTRACT_UPLOAD_FILE_BYTES)
  if (oversizedFile) {
    return `${oversizedFile.name} \u8d85\u8fc7\u5355\u6587\u4ef6\u4e0a\u4f20\u9650\u5236\uff0c\u8bf7\u538b\u7f29\u5230 ${formatUploadBytes(MAX_CONTRACT_UPLOAD_FILE_BYTES)} \u4ee5\u5185\u540e\u91cd\u8bd5\u3002`
  }

  if (files.length > MAX_CONTRACT_IMAGE_BATCH && files.every((file) => isImageFilename(file.name))) {
    return `\u4e00\u6b21\u6700\u591a\u4e0a\u4f20 ${MAX_CONTRACT_IMAGE_BATCH} \u5f20\u5408\u540c\u56fe\u7247\uff0c\u8bf7\u5206\u6279\u4e0a\u4f20\u3002`
  }

  return null
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
    return `正在按顺序识别 ${files.length} 张合同图片，并进行文字校对...`
  }

  const extension = getFileExtension(files[0].name)
  if (IMAGE_EXTENSIONS.has(extension)) {
    return '正在识别合同图片，并进行文字校对...'
  }

  if (extension === 'pdf') {
    return '正在逐页识别 PDF 内容，并提取文字...'
  }

  return '正在导入合同内容...'
}

function shouldUseAsyncOcrQueue(files: File[]) {
  if (files.length === 0) {
    return false
  }

  if (files.length > 1) {
    return true
  }

  const extension = getFileExtension(files[0].name)
  return extension === 'pdf' || IMAGE_EXTENSIONS.has(extension)
}

function buildAuthHeaders(authToken?: string | null) {
  return authToken ? { Authorization: `Bearer ${authToken}` } : undefined
}

function getQueueTaskMessage(payload: OcrQueueStatusResponse) {
  if (typeof payload.progress_message === 'string' && payload.progress_message.trim()) {
    return payload.progress_message
  }
  if (typeof payload.last_error === 'string' && payload.last_error.trim()) {
    return payload.last_error
  }
  return ''
}

async function sleep(ms: number) {
  await new Promise((resolve) => window.setTimeout(resolve, ms))
}

export function DocPanel({
  review,
  authToken,
  canExportReport = false,
  onExportReport,
  isExportingReport = false,
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
  const shouldHideOcrSourceAfterDeepReview = (
    review.documentSource === 'ocr'
    && review.reviewStage === 'complete'
    && review.finalReport.length > 0
    && !isOcrReady
  )
  const canInspectContractText = !shouldHideOcrSourceAfterDeepReview
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
              {canExportReport && onExportReport && (
                <button
                  className="px-btn px-btn--sm px-btn--orange"
                  onClick={onExportReport}
                  title="导出报告"
                  disabled={isExportingReport}
                >
                  <Download size={14} />
                  {isExportingReport ? '导出中...' : '导出报告'}
                </button>
              )}

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

              {canInspectContractText && (
                <>
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

                  <button
                    className="doc-panel__icon-btn"
                    onClick={handleDownload}
                    title="下载合同文本"
                  >
                    <Download size={16} />
                  </button>
                </>
              )}
            </>
          )}
        </div>
      </div>

      <div className="doc-panel__content">
        {isEmpty ? (
          <UploadArea
            authToken={authToken}
            onFileUpload={onFileUpload}
            onOcrReady={onOcrReady}
          />
        ) : isOcrReady ? (
          <div className="doc-paper doc-paper--editable" style={{ fontSize: `${zoom}%` }}>
            <div className="doc-editor__heading">合同识别结果</div>
            <p className="doc-editor__hint">
              识别结果已经回填到右侧文档区。请先检查并修正错字、漏字或页序问题，再开始合同分析。
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
              style={{ fontSize: `${15 * zoom / 100}px` }}
              spellCheck={false}
            />
          </div>
        ) : shouldHideOcrSourceAfterDeepReview ? (
          <div className="doc-paper" style={{ fontSize: `${zoom}%` }}>
            <div className="doc-editor__heading">合同分析已完成</div>
            <p className="doc-editor__hint">
              原始照片识别内容已自动收起，当前保留完整审查报告与问答结果。
            </p>
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
              shouldHideOcrSourceAfterDeepReview ? (
                <>
                  <span>合同分析已完成</span>
                  <span style={{ color: 'var(--color-ink-muted)' }}>原始照片识别内容已自动收起</span>
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
              )
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
                  开始分析
                </button>
              </>
            ) : (
              <>
                <span className="doc-panel__footer-dot" />
                <span>已加载</span>
                <span style={{ color: 'var(--color-ink-muted)' }}>智审内核已就绪</span>
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
  onFileUpload: (text: string, filename: string) => void
  onOcrReady: (text: string, filename: string, warnings?: string[]) => void
}

function UploadArea({
  authToken,
  onFileUpload,
  onOcrReady,
}: UploadAreaProps) {
  const hiddenFileInput = useRef<HTMLInputElement>(null)
  const [isProcessingFile, setIsProcessingFile] = useState(false)
  const [isDragActive, setIsDragActive] = useState(false)
  const [processingText, setProcessingText] = useState('')

  const handleUploadClick = () => hiddenFileInput.current?.click()

  const processFiles = useCallback(async (files: File[], resetInput?: () => void) => {
    if (files.length === 0) return

    const unsupportedFile = files.find((file) => !SUPPORTED_EXTENSIONS.has(getFileExtension(file.name)))
    if (unsupportedFile) {
      alert(`暂不支持 ${unsupportedFile.name} 这种文件格式，请上传 TXT、DOCX、PDF 或合同图片。`)
      resetInput?.()
      return
    }

    if (files.length > 1 && !files.every((file) => isImageFilename(file.name))) {
      alert('一次仅支持批量上传多张合同图片；TXT、DOCX、PDF 请单独上传。')
      resetInput?.()
      return
    }

    const validationMessage = buildUploadValidationMessage(files)
    if (validationMessage) {
      alert(validationMessage)
      resetInput?.()
      return
    }

    try {
      setIsProcessingFile(true)
      setProcessingText(buildUploadProgressText(files))

      const formData = new FormData()
      files.forEach((file) => formData.append('files', file))

      let payload: OcrIngestResponse | null = null
      if (shouldUseAsyncOcrQueue(files)) {
        const queuePayload = await safeFetchJSON<OcrQueueCreateResponse>(apiPath('/ocr/queue'), {
          method: 'POST',
          headers: buildAuthHeaders(authToken),
          body: formData,
        })
        const taskId = typeof queuePayload.task_id === 'string' ? queuePayload.task_id : ''
        if (!taskId) {
          throw new APIError('OCR 队列创建失败，请稍后重试。')
        }

        const estimatedWait = typeof queuePayload.estimated_wait === 'string' ? queuePayload.estimated_wait : ''
        setProcessingText(estimatedWait ? `上传完成，正在排队识别（${estimatedWait}）...` : '上传完成，正在排队识别...')

        let latestTask: OcrQueueStatusResponse | null = null
        for (let pollCount = 0; pollCount < OCR_QUEUE_MAX_POLLS; pollCount += 1) {
          const task = await safeFetchJSON<OcrQueueStatusResponse>(apiPath(`/ocr/queue/${taskId}`), {
            headers: buildAuthHeaders(authToken),
          })
          latestTask = task

          const progressMessage = getQueueTaskMessage(task)
          if (progressMessage) {
            setProcessingText(progressMessage)
          }

          if (task.status === 'completed') {
            if (!task.result || typeof task.result !== 'object') {
              throw new APIError('OCR 任务已完成，但未返回可用结果。')
            }
            payload = task.result as OcrIngestResponse
            break
          }

          if (task.status === 'failed' || task.status === 'dead_letter' || task.status === 'cancelled') {
            throw new APIError(progressMessage || 'OCR 任务处理失败，请稍后重试。')
          }

          await sleep(OCR_QUEUE_POLL_INTERVAL_MS)
        }

        if (!latestTask || latestTask.status !== 'completed') {
          throw new APIError('OCR 任务处理超时，请稍后重试。')
        }
      } else {
        payload = await safeFetchJSON<OcrIngestResponse>(apiPath('/ocr/ingest'), {
          method: 'POST',
          headers: buildAuthHeaders(authToken),
          body: formData,
        })
      }

      if (!payload) {
        throw new APIError('OCR 结果读取失败，请稍后重试。')
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

      if (sourceType === 'txt' || sourceType === 'docx') {
        onFileUpload(mergedText, displayName)
      } else {
        onOcrReady(mergedText, displayName, warnings)
      }
    } catch (error) {
      console.error('File ingest error:', error)
      const message = error instanceof Error ? error.message : '文件导入失败，请稍后重试。'
      alert(message)
    } finally {
      setIsProcessingFile(false)
      setProcessingText('')
      resetInput?.()
    }
  }, [authToken, onFileUpload, onOcrReady])

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    void processFiles(files, () => {
      event.target.value = ''
    })
  }

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
    if (!isProcessingFile) {
      setIsDragActive(true)
    }
  }

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) {
      return
    }
    setIsDragActive(false)
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragActive(false)
    if (isProcessingFile) return
    const files = Array.from(event.dataTransfer.files ?? [])
    void processFiles(files)
  }

  return (
    <div
      className={`upload-area ${isDragActive ? 'upload-area--drag-active' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
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


      <p className="upload-area__hint">
        直接拖拽文件或照片到这里，也可以点击下方按钮选择
      </p>

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
