import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import {
  Send,
  CheckSquare,
  Loader,
  Wand2,
  ChevronDown,
  ChevronUp,
  TriangleAlert,
  FileText,
} from 'lucide-react'
import type { ReviewState, RiskCard } from '../App'

interface ChatPanelProps {
  review: ReviewState
  authToken?: string | null
  onBreakpointConfirm: () => void
  onReset: () => void
  onSendMessage: (message: string) => void
}

export function ChatPanel({ review, authToken, onBreakpointConfirm, onReset, onSendMessage }: ChatPanelProps) {
  const [inputValue, setInputValue] = useState('')
  const [expandedCard, setExpandedCard] = useState<string | null>(null)
  const [autoFixSuggestions, setAutoFixSuggestions] = useState<Record<string, string>>({})
  const [loadingFix, setLoadingFix] = useState<string | null>(null)
  const [elapsedTime, setElapsedTime] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (review.status === 'reviewing') {
      setElapsedTime(0)
      timerRef.current = setInterval(() => setElapsedTime(v => v + 1), 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [review.status])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [review.chatMessages, review.riskCards, review.finalReport])

  const formatTime = (s: number) => s < 60 ? `${s}秒` : `${Math.floor(s / 60)}分 ${s % 60}秒`

  const handleSend = () => {
    if (!inputValue.trim()) return
    onSendMessage(inputValue.trim())
    setInputValue('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
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
        body: JSON.stringify({ clause: card.clause, issue: card.issue, suggestion: card.suggestion, legal_ref: card.legalRef }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      setAutoFixSuggestions(prev => ({ ...prev, [card.id]: data.suggestion }))
    } catch {
      setAutoFixSuggestions(prev => ({
        ...prev,
        [card.id]: `建议将"${card.clause}"条款修改为符合《民法典》相关规定的表述。参考依据：${card.legalRef}。可优先采用这条建议：${card.suggestion}`,
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
      {/* Header */}
      <div className="chat-panel__header">
        <div className="chat-panel__avatar" style={{ background: 'none', border: 'none', padding: 0 }}>
          <img
            src="/doge.png"
            alt="Doge"
            style={{ width: 52, height: 52, border: '4px solid black', objectFit: 'contain', imageRendering: 'pixelated', background: 'white' }}
          />
        </div>
        <div>
          <div className="chat-panel__title">🐶 Doge 合规助手</div>
          <div className="chat-panel__status">
            {hasContent ? (
              <>
                <span className={`chat-panel__status-dot ${isReviewing ? 'chat-panel__status-dot--pulse' : ''}`} />
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

      {/* Messages */}
      <div className="chat-panel__messages">

        {/* Thinking steps */}
        {hasContent && (
          <motion.div
            className="thinking-steps"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {review.thinkingSteps.map(step => (
              <div
                key={step.id}
                className={`thinking-step ${
                  step.status === 'done' ? 'thinking-step--done' :
                  step.status === 'active' ? 'thinking-step--active' : ''
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

        {/* AI summary bubble */}
        {(review.riskCards.length > 0 || isComplete) && (
          <motion.div
            className="ai-bubble"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {review.riskCards.length > 0 && (
              <>
                已识别到 <strong>{review.riskCards.length} 处</strong> 潜在合规风险。
                {review.riskCards[0] && (
                  <> 其中「{review.riskCards[0].title}」建议优先处理。</>
                )}
              </>
            )}
            {isComplete && review.finalReport.length === 0 && (
              <>审查完成，暂未发现明显风险点。</>
            )}
          </motion.div>
        )}

        {/* Risk cards */}
        {review.riskCards.length > 0 && (
          <div className="risk-cards">
            {review.riskCards.map(card => (
              <motion.div
                key={card.id}
                className={`risk-card risk-card--${card.level}`}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
              >
                {/* Card header */}
                <div className="risk-card__header">
                  <span className={`risk-card__badge risk-card__badge--${card.level}`}>
                    {card.level === 'high' ? '⚠ 高风险' : '◈ 提示'}
                  </span>
                  {expandedCard === card.id
                    ? <ChevronUp size={20} />
                    : <ChevronDown size={20} />
                  }
                </div>

                {/* Card body */}
                <div className="risk-card__body">
                  <div className="risk-card__title">{card.title}</div>
                  <div className="risk-card__desc">
                    <strong>条款：</strong>{card.clause}
                  </div>
                  <div className="risk-card__desc">{card.issue}</div>
                  {card.legalRef && (
                    <div className="risk-card__legal">法律依据：{card.legalRef}</div>
                  )}
                </div>

                {/* Expanded detail */}
                <AnimatePresence>
                  {expandedCard === card.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      style={{ overflow: 'hidden' }}
                    >
                      <div className="risk-card__detail">
                        <strong>建议操作：</strong>{card.suggestion}
                      </div>
                      {autoFixSuggestions[card.id] && (
                        <div className="risk-card__fix">
                          <strong>AI 修正建议：</strong>
                          <p style={{ marginTop: 6, lineHeight: 1.7 }}>
                            {autoFixSuggestions[card.id]}
                          </p>
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Actions */}
                <div className="risk-card__actions">
                  <button
                    className="risk-card__action-btn risk-card__action-btn--fix"
                    onClick={() => handleAutoFix(card)}
                    disabled={loadingFix === card.id}
                  >
                    {loadingFix === card.id ? (
                      <><Loader size={14} /> 生成中...</>
                    ) : (
                      <><Wand2 size={14} /> 自动修正</>
                    )}
                  </button>
                  <button
                    className="risk-card__action-btn"
                    onClick={() => setExpandedCard(expandedCard === card.id ? null : card.id)}
                  >
                    {expandedCard === card.id ? (
                      <><ChevronUp size={14} /> 收起详情</>
                    ) : (
                      <><FileText size={14} /> 查看法务意见</>
                    )}
                  </button>
                </div>
              </motion.div>
            ))}
          </div>
        )}

        {/* Breakpoint summary (compact, confirm button is in the bottom bar) */}
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
                {review.riskCards.filter(c => c.level === 'high').length > 0 && (
                  <span className="breakpoint-card__tag breakpoint-card__tag--high">
                    {review.riskCards.filter(c => c.level === 'high').length} 条高危
                  </span>
                )}
                {review.riskCards.filter(c => c.level === 'medium').length > 0 && (
                  <span className="breakpoint-card__tag">
                    {review.riskCards.filter(c => c.level === 'medium').length} 条提示
                  </span>
                )}
              </div>
              <div style={{ marginTop: 10, fontSize: 12, color: 'var(--color-ink-muted)' }}>
                ↓ 点击下方「确认，生成完整报告」继续
              </div>
            </div>
          </motion.div>
        )}

        {/* Streaming indicator */}
        {isReviewing && review.riskCards.length === 0 && (
          <div className="streaming-indicator">
            <div className="streaming-dots">
              <span className="streaming-dot" />
              <span className="streaming-dot" />
              <span className="streaming-dot" />
            </div>
            <span>认真审查中，请耐心等待...</span>
            <span style={{ marginLeft: 'auto', fontSize: 8, color: 'var(--color-ink-muted)' }}>
              {formatTime(elapsedTime)}
            </span>
          </div>
        )}

        {/* Final report */}
        {review.finalReport.length > 0 && (
          <motion.div
            className="final-report"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="final-report__heading-strip">■ 合同审查报告</div>
            <div className="final-report__body">
              {review.finalReport.map((paragraph, index) => {
                if (paragraph.startsWith('## ')) {
                  return <h2 key={index} className="final-report__h2">{paragraph.replace('## ', '')}</h2>
                }
                if (paragraph.startsWith('### ')) {
                  return <h3 key={index} className="final-report__h3">{paragraph.replace('### ', '')}</h3>
                }
                return <p key={index} className="final-report__text">{paragraph}</p>
              })}
            </div>
          </motion.div>
        )}

        {/* Chat messages — only shown after report is complete */}
        {isComplete && review.finalReport.length > 0 && review.chatMessages.length > 0 && (
          <motion.div
            className="chat-messages"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            {review.chatMessages.map(msg => (
              <motion.div
                key={msg.id}
                className={`chat-msg ${msg.role === 'user' ? 'chat-msg--user' : ''}`}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <div className="chat-msg__label">
                  {msg.role === 'assistant' ? '🐶 助手' : '你'}
                </div>
                <div className="chat-msg__bubble">
                  {msg.content.split('\n').map((line, i) => (
                    <p key={`${msg.id}-${i}`}>{line}</p>
                  ))}
                </div>
              </motion.div>
            ))}
          </motion.div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Bottom action area */}
      <div className="chat-panel__input">
        {isComplete && review.finalReport.length > 0 ? (
          /* Chat input — available after report */
          <div className="chat-input-row">
            <textarea
              className="chat-input-textarea"
              placeholder="报告已生成，可以问我：押金风险在哪？这份合同怎么改？"
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <button
              className="chat-input-send"
              onClick={handleSend}
              disabled={!inputValue.trim()}
            >
              <Send size={24} />
            </button>
          </div>
        ) : isBreakpoint && review.breakpointMessage ? (
          /* Breakpoint confirm — always visible at bottom */
          <div style={{
            padding: '16px 20px',
            background: 'var(--color-orange-light)',
            border: '4px solid var(--color-orange)',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              fontFamily: 'var(--font-pixel)',
              fontSize: 13,
              fontWeight: 700,
              color: 'var(--color-orange)',
            }}>
              <TriangleAlert size={18} />
              风险扫描完成，确认后生成完整报告
            </div>
            <div style={{ display: 'flex', gap: 12 }}>
              <button
                className="px-btn px-btn--green"
                onClick={onBreakpointConfirm}
                style={{ flex: 1, padding: '14px 0', fontSize: 14 }}
              >
                ✓ 确认，生成完整报告
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
        ) : (
          /* Locked placeholder */
          <div className="chat-locked">
            <span style={{ fontSize: 22 }}>🔒</span>
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
