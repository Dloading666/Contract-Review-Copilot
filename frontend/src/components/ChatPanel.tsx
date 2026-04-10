import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  CheckSquare,
  ChevronDown,
  ChevronUp,
  Download,
  FileText,
  Loader,
  Send,
  TriangleAlert,
  Wand2,
} from 'lucide-react'
import type { ReviewState, RiskCard } from '../App'
interface ChatPanelProps {
  review: ReviewState
  authToken?: string | null
  onExportReport: () => void
  isExportingReport?: boolean
  onBreakpointConfirm: () => void
  onReset: () => void
  onSendMessage: (message: string) => void
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

export function ChatPanel({
  review,
  authToken,
  onExportReport,
  isExportingReport = false,
  onBreakpointConfirm,
  onReset,
  onSendMessage,
}: ChatPanelProps) {
  const [inputValue, setInputValue] = useState('')
  const [expandedCard, setExpandedCard] = useState<string | null>(null)
  const [autoFixSuggestions, setAutoFixSuggestions] = useState<Record<string, string>>({})
  const [loadingFix, setLoadingFix] = useState<string | null>(null)
  const [elapsedTime, setElapsedTime] = useState(0)
  const [isGeneratingGuide, setIsGeneratingGuide] = useState(false)
  const [showChatComposer, setShowChatComposer] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const finalReportRef = useRef<HTMLDivElement>(null)
  const previousStatusRef = useRef(review.status)
  const hasUserMessages = review.chatMessages.some((message) => message.role === 'user')

  useEffect(() => {
    if (review.status === 'reviewing') {
      setElapsedTime(0)
      timerRef.current = setInterval(() => setElapsedTime((value) => value + 1), 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [review.status])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: 'smooth' })
  }, [review.chatMessages, review.riskCards])

  useEffect(() => {
    setShowChatComposer(false)
    setInputValue('')
    setExpandedCard(null)
    setAutoFixSuggestions({})
    setLoadingFix(null)
  }, [review.sessionId])

  useEffect(() => {
    if (hasUserMessages) {
      setShowChatComposer(true)
    }
  }, [hasUserMessages])

  useEffect(() => {
    if (review.finalReport.length === 1) {
      finalReportRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    }
  }, [review.finalReport.length])

  useEffect(() => {
    const cameFromBreakpoint = previousStatusRef.current === 'breakpoint'
    if (cameFromBreakpoint && review.status === 'reviewing' && review.finalReport.length === 0) {
      setIsGeneratingGuide(true)
    }

    if (
      review.status === 'idle'
      || review.status === 'error'
      || review.status === 'complete'
      || review.finalReport.length > 0
    ) {
      setIsGeneratingGuide(false)
    }

    previousStatusRef.current = review.status
  }, [review.finalReport.length, review.status])

  const formatTime = (seconds: number) => (
    seconds < 60
      ? `${seconds}秒`
      : `${Math.floor(seconds / 60)}分${seconds % 60}秒`
  )

  const handleSend = () => {
    const message = inputValue.trim()
    if (!message) return
    onSendMessage(message)
    setInputValue('')
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSend()
    }
  }

  const handleAutoFix = async (card: RiskCard) => {
    setLoadingFix(card.id)
    setExpandedCard(card.id)

    try {
      const response = await fetch('/api/autofix', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({
          clause: card.clause,
          issue: card.issue,
          suggestion: card.suggestion,
          legal_ref: card.legalRef,
        }),
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const data = await response.json() as { suggestion?: string }
      setAutoFixSuggestions((prev) => ({
        ...prev,
        [card.id]: data.suggestion ?? '生成修正建议失败。',
      }))
    } catch {
      setAutoFixSuggestions((prev) => ({
        ...prev,
        [card.id]: `建议将「${card.clause}」条款修改为符合法律规定的表述。参考依据：${card.legalRef}。可优先采用这条建议：${card.suggestion}`,
      }))
    } finally {
      setLoadingFix(null)
    }
  }

  const toggleExpandedCard = (cardId: string) => {
    setExpandedCard((current) => (current === cardId ? null : cardId))
  }

  const isReviewing = review.status === 'reviewing'
  const isOcrReady = review.status === 'ocr_ready'
  const isBreakpoint = review.status === 'breakpoint'
  const isComplete = review.status === 'complete'
  const hasContent = review.status !== 'idle'
  const isGeneratingGuideInProgress = isReviewing && isGeneratingGuide && review.finalReport.length === 0
  const reviewingStatusText = isGeneratingGuideInProgress ? '正在生成避坑指南中...' : '正在分析合同...'
  const reviewingIndicatorText = isGeneratingGuideInProgress
    ? '正在生成避坑指南中...'
    : '认真审查中，请耐心等待...'
  const substantiveRiskCards = review.riskCards.filter((card) => !isNoRiskPlaceholderCard(card))
  const noRiskSummaryCard = review.riskCards.find((card) => isNoRiskPlaceholderCard(card)) ?? null
  const hasNoRiskConclusion = Boolean(noRiskSummaryCard) && substantiveRiskCards.length === 0
  const canChatAboutReport = isComplete && review.finalReport.length > 0
  const canChatWithoutReport = isComplete && hasNoRiskConclusion
  const showChatHistory = (
    (canChatAboutReport && showChatComposer)
    || canChatWithoutReport
  ) && review.chatMessages.length > 0

  const highRiskCount = substantiveRiskCards.filter((card) => card.level === 'high').length
  const mediumRiskCount = substantiveRiskCards.filter((card) => card.level === 'medium').length

  useEffect(() => {
    if (review.status === 'complete' && hasNoRiskConclusion) {
      setShowChatComposer(true)
    }
  }, [hasNoRiskConclusion, review.status])

  return (
    <section className="chat-panel">
      <div className="chat-panel__header">
        <div className="chat-panel__avatar" style={{ background: 'none', border: 'none', padding: 0 }}>
          <img
            src="/doge.png"
            alt="Doge"
            style={{
              width: 52,
              height: 52,
              border: '4px solid black',
              objectFit: 'contain',
              imageRendering: 'pixelated',
              background: 'white',
            }}
          />
        </div>
        <div>
          <div className="chat-panel__title">Doge合同审查助手</div>
          <div className="chat-panel__status">
            {hasContent ? (
              <>
                <span className={`chat-panel__status-dot ${isReviewing ? 'chat-panel__status-dot--pulse' : ''}`} />
                <span>
                  {isReviewing && reviewingStatusText}
                  {isOcrReady && '等待确认识别文字...'}
                  {isBreakpoint && '等待确认...'}
                  {isComplete && '审查完成'}
                  {review.status === 'error' && '处理失败'}
                </span>
              </>
            ) : (
              <span>等待上传合同</span>
            )}
          </div>
        </div>
      </div>

      <div className="chat-panel__messages">
        {hasContent && !isOcrReady && (
          <motion.div className="thinking-steps" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            {review.thinkingSteps.map((step) => (
              <div
                key={step.id}
                className={`thinking-step ${
                  step.status === 'done'
                    ? 'thinking-step--done'
                    : step.status === 'active'
                      ? 'thinking-step--active'
                      : ''
                }`}
              >
                {step.status === 'done' && (
                  <span className="thinking-step__check">
                    <CheckSquare size={14} color="white" />
                  </span>
                )}
                {step.status === 'active' && <span className="thinking-step__spinner" />}
                {step.status === 'pending' && <span className="thinking-step__empty" />}
                <span>{step.label}</span>
              </div>
            ))}
          </motion.div>
        )}

        {isOcrReady && (
          <motion.div className="ai-bubble" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            图片文字识别已完成，请先在右侧确认或修改识别结果，再开始合同分析。
          </motion.div>
        )}

        {(substantiveRiskCards.length > 0 || hasNoRiskConclusion || isComplete) && (
          <motion.div
            className={`ai-bubble${hasNoRiskConclusion ? ' ai-bubble--success' : ''}`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {substantiveRiskCards.length > 0 && (
              <>
                已识别到 <strong>{substantiveRiskCards.length} 处</strong> 潜在合规风险。
                {substantiveRiskCards[0] && <> 其中“{substantiveRiskCards[0].title}”建议优先处理。</>}
              </>
            )}
            {hasNoRiskConclusion && <>已识别到 <strong>0 处</strong> 潜在合规风险。当前合同未发现明显不公平条款。</>}
            {isComplete && review.finalReport.length === 0 && !hasNoRiskConclusion && <>审查完成，暂未发现明显风险点。</>}
          </motion.div>
        )}

        {substantiveRiskCards.length > 0 && (
          <div className="risk-cards">
            {substantiveRiskCards.map((card) => (
              <motion.div
                key={card.id}
                className={`risk-card risk-card--${card.level}`}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
              >
                <div
                  className="risk-card__header risk-card__header--interactive"
                  onClick={() => toggleExpandedCard(card.id)}
                >
                  <span className={`risk-card__badge risk-card__badge--${card.level}`}>
                    {card.level === 'high' ? '高风险' : '提示'}
                  </span>
                  {expandedCard === card.id ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                </div>

                <div className="risk-card__body">
                  <div className="risk-card__title">{card.title}</div>
                  <div className="risk-card__desc">
                    <strong>条款：</strong>
                    {card.clause}
                  </div>
                  <div className="risk-card__desc">{card.issue}</div>
                  {card.legalRef && <div className="risk-card__legal">法律依据：{card.legalRef}</div>}
                </div>

                <AnimatePresence>
                  {expandedCard === card.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      style={{ overflow: 'hidden' }}
                    >
                      <div className="risk-card__detail">
                        <strong>建议操作：</strong>
                        {card.suggestion}
                      </div>
                      {autoFixSuggestions[card.id] && (
                        <div className="risk-card__fix">
                          <strong>AI 修正建议：</strong>
                          <p style={{ marginTop: 6, lineHeight: 1.7 }}>{autoFixSuggestions[card.id]}</p>
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>

                <div className="risk-card__actions">
                  <button
                    className="risk-card__action-btn risk-card__action-btn--fix"
                    onClick={() => handleAutoFix(card)}
                    disabled={loadingFix === card.id}
                  >
                    {loadingFix === card.id ? (
                      <>
                        <Loader size={14} /> 生成中...
                      </>
                    ) : (
                      <>
                        <Wand2 size={14} /> 自动修正
                      </>
                    )}
                  </button>
                  <button
                    className="risk-card__action-btn"
                    onClick={() => toggleExpandedCard(card.id)}
                  >
                    {expandedCard === card.id ? (
                      <>
                        <ChevronUp size={14} /> 收起详情
                      </>
                    ) : (
                      <>
                        <FileText size={14} /> 查看法务意见
                      </>
                    )}
                  </button>
                </div>
              </motion.div>
            ))}
          </div>
        )}

        {hasNoRiskConclusion && noRiskSummaryCard && (
          <motion.div
            className="risk-card risk-card--success"
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <div className="risk-card__header">
              <span className="risk-card__badge risk-card__badge--success">通过</span>
              <span style={{ fontFamily: 'var(--font-pixel)', fontSize: 14, color: 'var(--color-green)' }}>
                未发现明显不公平条款
              </span>
            </div>
            <div className="risk-card__body">
              <div className="risk-card__title">{noRiskSummaryCard.title || '整体评估'}</div>
              <div className="risk-card__desc">
                <strong>结论：</strong>
                {noRiskSummaryCard.issue}
              </div>
              <div className="risk-card__desc">
                <strong>建议：</strong>
                {noRiskSummaryCard.suggestion}
              </div>
              {noRiskSummaryCard.legalRef && (
                <div className="risk-card__legal">法律依据：{noRiskSummaryCard.legalRef}</div>
              )}
            </div>
          </motion.div>
        )}

        {isBreakpoint && review.breakpointMessage && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            style={{
              border: '4px solid var(--color-orange)',
              background: 'var(--color-orange-light)',
              padding: '14px 18px',
              fontFamily: 'var(--font-pixel)',
              fontSize: 13,
              lineHeight: 1.8,
              color: 'var(--color-ink)',
              display: 'flex',
              gap: 12,
              alignItems: 'flex-start',
            }}
          >
            <TriangleAlert size={20} color="var(--color-orange)" style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <div style={{ fontWeight: 700, color: 'var(--color-orange)', marginBottom: 6 }}>风险扫描完成</div>
              <div>{review.breakpointMessage}</div>
              <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {highRiskCount > 0 && (
                  <span className="breakpoint-card__tag breakpoint-card__tag--high">
                    {highRiskCount} 条高危
                  </span>
                )}
                {mediumRiskCount > 0 && (
                  <span className="breakpoint-card__tag">
                    {mediumRiskCount} 条提示
                  </span>
                )}
              </div>
              <div style={{ marginTop: 10, fontSize: 12, color: 'var(--color-ink-muted)' }}>
                点击下方「确认，生成完整报告」继续
              </div>
            </div>
          </motion.div>
        )}

        {isReviewing && (review.riskCards.length === 0 || isGeneratingGuideInProgress) && (
          <div className="streaming-indicator">
            <div className="streaming-dots">
              <span className="streaming-dot" />
              <span className="streaming-dot" />
              <span className="streaming-dot" />
            </div>
            <span>{reviewingIndicatorText}</span>
            <span style={{ marginLeft: 'auto', fontSize: 8, color: 'var(--color-ink-muted)' }}>
              {formatTime(elapsedTime)}
            </span>
          </div>
        )}

        {review.finalReport.length > 0 && (
          <motion.div
            ref={finalReportRef}
            className="final-report"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="final-report__heading-strip">合同审查报告</div>
            <div className="final-report__body">
              {review.finalReport.map((paragraph, index) => {
                if (paragraph.startsWith('## ')) {
                  return (
                    <h2 key={paragraph + index} className="final-report__h2">
                      {paragraph.replace('## ', '')}
                    </h2>
                  )
                }

                if (paragraph.startsWith('### ')) {
                  return (
                    <h3 key={paragraph + index} className="final-report__h3">
                      {paragraph.replace('### ', '')}
                    </h3>
                  )
                }

                return (
                  <p key={paragraph + index} className="final-report__text">
                    {paragraph}
                  </p>
                )
              })}
            </div>
          </motion.div>
        )}

        {showChatHistory && (
          <motion.div className="chat-messages" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            {review.chatMessages.map((message) => (
              <motion.div
                key={message.id}
                className={`chat-msg ${message.role === 'user' ? 'chat-msg--user' : ''}`}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <div className="chat-msg__label">{message.role === 'assistant' ? '助手' : '你'}</div>
                <div className="chat-msg__bubble">
                  {message.content.split('\n').map((line, index) => (
                    <p key={`${message.id}-${index}`}>{line}</p>
                  ))}
                </div>
              </motion.div>
            ))}
          </motion.div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="chat-panel__input">
        {canChatAboutReport ? (
          showChatComposer ? (
            <div className="chat-input-stack">
              <div className="chat-input-row">
                <textarea
                  className="chat-input-textarea"
                  placeholder="报告已生成，可以问我：押金风险在哪里？这份合同怎么改？"
                  value={inputValue}
                  onChange={(event) => setInputValue(event.target.value)}
                  onKeyDown={handleKeyDown}
                />
                <button className="chat-input-send" onClick={handleSend} disabled={!inputValue.trim()}>
                  <Send size={24} />
                </button>
              </div>
            </div>
          ) : (
            <div className="chat-locked">
              <span style={{ fontSize: 22 }}>避坑指南</span>
              <span>完整报告已生成。你可以先在这里查看避坑指南内容，再导出 Word 报告。</span>
              <div
                style={{
                  width: '100%',
                  maxHeight: 260,
                  overflowY: 'auto',
                  border: '3px solid black',
                  background: 'white',
                  padding: '16px 18px',
                  textAlign: 'left',
                }}
              >
                {review.finalReport.map((paragraph, index) => {
                  if (paragraph.startsWith('## ')) {
                    return (
                      <div
                        key={paragraph + index}
                        style={{
                          fontFamily: 'var(--font-ui)',
                          fontSize: 12,
                          fontWeight: 700,
                          lineHeight: 1.7,
                          color: 'var(--color-ink)',
                          marginBottom: 10,
                        }}
                      >
                        {paragraph.replace('## ', '')}
                      </div>
                    )
                  }

                  if (paragraph.startsWith('### ')) {
                    return (
                      <div
                        key={paragraph + index}
                        style={{
                          fontFamily: 'var(--font-ui)',
                          fontSize: 13,
                          fontWeight: 700,
                          color: 'var(--color-orange)',
                          margin: '10px 0 6px',
                        }}
                      >
                        {paragraph.replace('### ', '')}
                      </div>
                    )
                  }

                  return (
                    <p
                      key={paragraph + index}
                      style={{
                        fontFamily: 'var(--font-ui)',
                        fontSize: 13,
                        lineHeight: 1.9,
                        color: 'var(--color-ink-soft)',
                        marginBottom: 8,
                      }}
                    >
                      {paragraph}
                    </p>
                  )
                })}
              </div>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'center' }}>
                <button className="px-btn px-btn--orange" onClick={onExportReport} disabled={isExportingReport}>
                  <Download size={14} />
                  {isExportingReport ? '导出中...' : '导出报告'}
                </button>
                <button className="px-btn px-btn--ghost" onClick={() => setShowChatComposer(true)}>
                  继续问答
                </button>
              </div>
            </div>
          )
        ) : canChatWithoutReport ? (
          <div className="chat-input-stack">
            <div className="chat-input-row">
              <textarea
                className="chat-input-textarea"
                placeholder="当前合同未发现明显不公平条款。你可以继续追问：押金怎么约定更稳妥？还有哪些签约注意点？"
                value={inputValue}
                onChange={(event) => setInputValue(event.target.value)}
                onKeyDown={handleKeyDown}
              />
              <button className="chat-input-send" onClick={handleSend} disabled={!inputValue.trim()}>
                <Send size={24} />
              </button>
            </div>
          </div>
        ) : isBreakpoint && review.breakpointMessage ? (
          <div
            style={{
              padding: '16px 20px',
              background: 'var(--color-orange-light)',
              border: '4px solid var(--color-orange)',
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                fontFamily: 'var(--font-pixel)',
                fontSize: 13,
                fontWeight: 700,
                color: 'var(--color-orange)',
              }}
            >
              <TriangleAlert size={18} />
              风险扫描完成，确认后生成完整报告
            </div>
            <div style={{ display: 'flex', gap: 12 }}>
              <button
                className="px-btn px-btn--green"
                onClick={onBreakpointConfirm}
                style={{ flex: 1, padding: '14px 0', fontSize: 14 }}
              >
                确认，生成完整报告
              </button>
              <button
                className="px-btn px-btn--ghost"
                onClick={onReset}
                style={{ padding: '14px 20px', fontSize: 13 }}
              >
                重新上传
              </button>
            </div>
          </div>
        ) : isOcrReady ? (
          <div className="chat-locked">
            <span style={{ fontSize: 22 }}>OCR</span>
            <span>图片文字已经提取完成，请先在右侧确认或修改文本，再开始合同分析。</span>
          </div>
        ) : (
          <div className="chat-locked">
            <span style={{ fontSize: 22 }}>Q&A</span>
            <span>
              {review.status === 'idle'
                ? '上传合同后开始分析，报告生成完成后可进行问答'
                : '审查进行中，报告生成后将开放问答'}
            </span>
          </div>
        )}
      </div>
    </section>
  )
}
