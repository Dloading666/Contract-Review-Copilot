import { useEffect, useRef, useState } from 'react'
import type { ReviewState, RiskCard } from '../App'

interface ChatPanelProps {
  review: ReviewState
  authToken?: string | null
  onBreakpointConfirm: () => void
  onReset: () => void
  onSendMessage: (message: string) => void
}

export function ChatPanel({
  review,
  authToken,
  onBreakpointConfirm,
  onReset,
  onSendMessage,
}: ChatPanelProps) {
  const [inputValue, setInputValue] = useState('')
  const [expandedCard, setExpandedCard] = useState<string | null>(null)
  const [autoFixSuggestions, setAutoFixSuggestions] = useState<Record<string, string>>({})
  const [loadingFix, setLoadingFix] = useState<string | null>(null)
  const [elapsedTime, setElapsedTime] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (review.status === 'reviewing') {
      setElapsedTime(0)
      timerRef.current = setInterval(() => {
        setElapsedTime((value) => value + 1)
      }, 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
      }
    }
  }, [review.status])

  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${seconds}秒`
    return `${Math.floor(seconds / 60)}分 ${seconds % 60}秒`
  }

  const handleSend = () => {
    if (!inputValue.trim()) return
    onSendMessage(inputValue.trim())
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

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()
      setAutoFixSuggestions((prev) => ({ ...prev, [card.id]: data.suggestion }))
    } catch {
      setAutoFixSuggestions((prev) => ({
        ...prev,
        [card.id]: `建议将“${card.clause}”条款修改为符合《民法典》相关规定的表述。参考依据：${card.legalRef}。可优先采用这条建议：${card.suggestion}`,
      }))
    } finally {
      setLoadingFix(null)
    }
  }

  const isReviewing = review.status === 'reviewing'
  const isBreakpoint = review.status === 'breakpoint'
  const isComplete = review.status === 'complete'
  const hasContent = review.status !== 'idle'

  return (
    <section className="chat-panel">
      <div className="chat-panel__header">
        <div className="chat-panel__header-content">
          <div className="chat-panel__avatar">
            <span className="material-symbols-outlined">auto_awesome</span>
          </div>
          <div>
            <h2 className="chat-panel__title">智审助手</h2>
            <div className="chat-panel__status">
              {hasContent ? (
                <>
                  <span className={`chat-panel__status-dot ${isReviewing ? 'animate-pulse' : ''}`} />
                  <span>
                    {isReviewing && '正在分析合同...'}
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
      </div>

      <div className="chat-panel__messages">
        {hasContent && (
          <div className="thinking-steps">
            {review.thinkingSteps.map((step) => (
              <div
                key={step.id}
                className={`thinking-step ${
                  step.status === 'done' ? 'thinking-step--done' : step.status === 'active' ? 'thinking-step--active' : ''
                }`}
              >
                {step.status === 'done' && (
                  <span className="material-symbols-outlined thinking-step__icon" style={{ color: 'var(--primary)' }}>
                    check_circle
                  </span>
                )}
                {step.status === 'active' && <div className="thinking-step__spinner" />}
                {step.status === 'pending' && (
                  <span className="material-symbols-outlined thinking-step__icon">radio_button_unchecked</span>
                )}
                <span>{step.label}</span>
              </div>
            ))}
          </div>
        )}

        {(review.riskCards.length > 0 || isComplete) && (
          <div className="ai-bubble">
            {review.riskCards.length > 0 && (
              <>
                已为您识别到 <strong>{review.riskCards.length}处</strong> 潜在合规风险。
                {review.riskCards[0] && <> 其中“{review.riskCards[0].title}”建议优先处理。</>}
              </>
            )}
            {isComplete && review.finalReport.length === 0 && <>审查完成，暂未发现明显风险点。</>}
          </div>
        )}

        {review.chatMessages.length > 0 && (
          <div className="assistant-chat">
            {review.chatMessages.map((message) => (
              <div
                key={message.id}
                className={`assistant-chat__message assistant-chat__message--${message.role}`}
              >
                <div className="assistant-chat__label">
                  {message.role === 'assistant' ? '助手' : '你'}
                </div>
                <div className="assistant-chat__bubble">
                  {message.content.split('\n').map((line, index) => (
                    <p key={`${message.id}-${index}`}>{line}</p>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {review.riskCards.length > 0 && (
          <div className="risk-cards">
            {review.riskCards.map((card) => (
              <div key={card.id} className={`risk-card risk-card--${card.level}`}>
                <div className="risk-card__header">
                  <span className={`risk-card__badge risk-card__badge--${card.level}`}>
                    {card.level === 'high' ? '高风险' : '提示'}
                  </span>
                  <span className="material-symbols-outlined risk-card__action-icon">open_in_new</span>
                </div>
                <h4 className="risk-card__title">{card.title}</h4>
                <p className="risk-card__desc">
                  <strong>条款:</strong> {card.clause} - {card.issue}
                </p>
                <p
                  className="risk-card__desc"
                  style={{ marginTop: '4px', fontSize: '11px', color: 'var(--outline)' }}
                >
                  法律依据: {card.legalRef}
                </p>

                {expandedCard === card.id && (
                  <div className="risk-card__detail">
                    <p className="risk-card__desc" style={{ marginTop: 8 }}>
                      <strong>建议操作:</strong> {card.suggestion}
                    </p>
                    {autoFixSuggestions[card.id] && (
                      <div className="risk-card__fix-suggestion">
                        <strong>修正建议:</strong>
                        <p style={{ marginTop: 4, fontSize: '0.8rem', color: 'var(--on-surface-variant)' }}>
                          {autoFixSuggestions[card.id]}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                <div className="risk-card__actions">
                  <button
                    className="risk-card__btn risk-card__btn--fix"
                    onClick={() => handleAutoFix(card)}
                    disabled={loadingFix === card.id}
                  >
                    {loadingFix === card.id ? '生成中...' : '自动修正'}
                  </button>
                  <button
                    className="risk-card__btn risk-card__btn--detail"
                    onClick={() => setExpandedCard(expandedCard === card.id ? null : card.id)}
                  >
                    {expandedCard === card.id ? '收起详情' : '查看法务意见'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {isBreakpoint && review.breakpointMessage && (
          <div className="breakpoint-card">
            <h3 className="breakpoint-card__title">
              <span className="material-symbols-outlined">warning</span>
              需要确认
            </h3>
            <p className="breakpoint-card__message">{review.breakpointMessage}</p>
            <div className="breakpoint-card__summary">
              {review.riskCards.filter((card) => card.level === 'high').length > 0 && (
                <span className="breakpoint-card__summary-tag">
                  {review.riskCards.filter((card) => card.level === 'high').length}条高危
                </span>
              )}
              {review.riskCards.filter((card) => card.level === 'medium').length > 0 && (
                <span className="breakpoint-card__summary-tag">
                  {review.riskCards.filter((card) => card.level === 'medium').length}条提示
                </span>
              )}
            </div>
            <div className="breakpoint-card__actions">
              <button className="breakpoint-card__btn breakpoint-card__btn--confirm" onClick={onBreakpointConfirm}>
                确认继续
              </button>
              <button className="breakpoint-card__btn breakpoint-card__btn--cancel" onClick={onReset}>
                重新上传
              </button>
            </div>
          </div>
        )}

        {isReviewing && review.riskCards.length === 0 && (
          <div className="streaming-indicator">
            <div className="streaming-indicator__dots">
              <span className="streaming-indicator__dot" />
              <span className="streaming-indicator__dot" />
              <span className="streaming-indicator__dot" />
            </div>
            <span>认真审查中，请耐心等待...</span>
            <span style={{ marginLeft: 'auto', fontSize: '12px', color: 'var(--outline)' }}>
              已用时 {formatTime(elapsedTime)}
            </span>
          </div>
        )}

        {review.finalReport.length > 0 && (
          <div className="final-report">
            {review.finalReport.map((paragraph, index) => {
              if (paragraph.startsWith('## ')) {
                return (
                  <h2 key={index} className="final-report__heading">
                    {paragraph.replace('## ', '')}
                  </h2>
                )
              }

              if (paragraph.startsWith('### ')) {
                return (
                  <h3
                    key={index}
                    className="final-report__heading"
                    style={{ fontSize: '1rem', borderBottom: 'none' }}
                  >
                    {paragraph.replace('### ', '')}
                  </h3>
                )
              }

              return (
                <p key={index} className="final-report__text" style={{ marginBottom: 'var(--space-2)' }}>
                  {paragraph}
                </p>
              )
            })}
          </div>
        )}
      </div>

      <div className="chat-panel__input">
        <div className="chat-input">
          <textarea
            className="chat-input__textarea"
            placeholder="输入问题，例如：押金风险在哪？这份合同怎么改？"
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button className="chat-input__send" onClick={handleSend} disabled={!inputValue.trim()}>
            <span className="material-symbols-outlined">send</span>
          </button>
        </div>
      </div>
    </section>
  )
}
