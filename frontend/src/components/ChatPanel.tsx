import { useState } from 'react'
import type { ReviewState } from '../App'

interface ChatPanelProps {
  review: ReviewState
  onBreakpointConfirm: () => void
  onReset: () => void
  onSendMessage: (message: string) => void
}

export function ChatPanel({ review, onBreakpointConfirm, onReset, onSendMessage }: ChatPanelProps) {
  const [inputValue, setInputValue] = useState('')

  const handleSend = () => {
    if (inputValue.trim()) {
      onSendMessage(inputValue.trim())
      setInputValue('')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const isReviewing = review.status === 'reviewing'
  const isBreakpoint = review.status === 'breakpoint'
  const isComplete = review.status === 'complete'
  const hasContent = review.status !== 'idle'

  return (
    <section className="chat-panel">
      {/* Header */}
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
                  </span>
                </>
              ) : (
                <span>等待上传合同</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="chat-panel__messages">
        {/* Thinking Steps */}
        {hasContent && (
          <div className="thinking-steps">
            {review.thinkingSteps.map((step) => (
              <div
                key={step.id}
                className={`thinking-step ${
                  step.status === 'done' ? 'thinking-step--done' :
                  step.status === 'active' ? 'thinking-step--active' : ''
                }`}
              >
                {step.status === 'done' && (
                  <span className="material-symbols-outlined thinking-step__icon" style={{ color: 'var(--primary)' }}>
                    check_circle
                  </span>
                )}
                {step.status === 'active' && (
                  <div className="thinking-step__spinner" />
                )}
                {step.status === 'pending' && (
                  <span className="material-symbols-outlined thinking-step__icon">radio_button_unchecked</span>
                )}
                <span>{step.label}</span>
              </div>
            ))}
          </div>
        )}

        {/* AI Summary Bubble */}
        {(review.riskCards.length > 0 || isComplete) && (
          <div className="ai-bubble">
            {review.riskCards.length > 0 && (
              <>
                已为您识别到 <strong>{review.riskCards.length}处</strong> 潜在合规风险。
                {review.riskCards[0] && (
                  <> 其中关于「{review.riskCards[0].title}」的条款与法规存在冲突。</>
                )}
              </>
            )}
            {isComplete && review.finalReport.length === 0 && (
              <>审查完成，未发现明显风险点。</>
            )}
          </div>
        )}

        {/* Risk Cards */}
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
                  <strong>条款:</strong> {card.clause} — {card.issue}
                </p>
                <p className="risk-card__desc" style={{ marginTop: '4px', fontSize: '11px', color: 'var(--outline)' }}>
                  法律依据: {card.legalRef}
                </p>
                <div className="risk-card__actions">
                  <button className="risk-card__btn risk-card__btn--fix">自动修正</button>
                  <button className="risk-card__btn risk-card__btn--detail">查看法务意见</button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Breakpoint Card */}
        {isBreakpoint && review.breakpointMessage && (
          <div className="breakpoint-card">
            <h3 className="breakpoint-card__title">
              <span className="material-symbols-outlined">warning</span>
              需要确认
            </h3>
            <p className="breakpoint-card__message">{review.breakpointMessage}</p>
            <div className="breakpoint-card__summary">
              {review.riskCards.filter(c => c.level === 'high').length > 0 && (
                <span className="breakpoint-card__summary-tag">
                  {review.riskCards.filter(c => c.level === 'high').length}条高危
                </span>
              )}
              {review.riskCards.filter(c => c.level === 'medium').length > 0 && (
                <span className="breakpoint-card__summary-tag">
                  {review.riskCards.filter(c => c.level === 'medium').length}条提示
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

        {/* Streaming Indicator */}
        {isReviewing && review.riskCards.length === 0 && (
          <div className="streaming-indicator">
            <div className="streaming-indicator__dots">
              <span className="streaming-indicator__dot" />
              <span className="streaming-indicator__dot" />
              <span className="streaming-indicator__dot" />
            </div>
            <span>正在扫描风险项...</span>
          </div>
        )}

        {/* Final Report */}
        {review.finalReport.length > 0 && (
          <div className="final-report">
            {review.finalReport.map((para, i) => {
              if (para.startsWith('## ')) {
                return <h2 key={i} className="final-report__heading">{para.replace('## ', '')}</h2>
              }
              if (para.startsWith('### ')) {
                return <h3 key={i} className="final-report__heading" style={{ fontSize: '1rem', borderBottom: 'none' }}>{para.replace('### ', '')}</h3>
              }
              if (para.includes('**') && para.includes('（严重程度')) {
                const parts = para.split(/(\*\*[^*]+\*\*)/g)
                return (
                  <div key={i} style={{ marginBottom: 'var(--space-4)' }}>
                    {parts.map((part, j) => {
                      if (part.startsWith('**') && part.endsWith('**')) {
                        return <strong key={j}>{part.replace(/\*\*/g, '')}</strong>
                      }
                      return <span key={j}>{part}</span>
                    })}
                  </div>
                )
              }
              return <p key={i} className="final-report__text" style={{ marginBottom: 'var(--space-2)' }}>{para}</p>
            })}
          </div>
        )}
      </div>

      {/* Input */}
      <div className="chat-panel__input">
        <div className="chat-input">
          <textarea
            className="chat-input__textarea"
            placeholder="输入指令或提问..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button className="chat-input__send" onClick={handleSend}>
            <span className="material-symbols-outlined">send</span>
          </button>
        </div>
      </div>
    </section>
  )
}
