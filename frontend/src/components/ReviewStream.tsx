import { useStreamingReview } from '../hooks/useStreamingReview'
import { AgentCard } from './AgentCard'
import { BreakpointCard } from './BreakpointCard'
import { FinalReport } from './FinalReport'

interface ReviewStreamProps {
  sessionId: string
  contractText: string
  onReset: () => void
}

export function ReviewStream({ sessionId, contractText, onReset }: ReviewStreamProps) {
  const {
    phase,
    extractedEntities,
    routingDecision,
    issues,
    breakpointData,
    reportParagraphs,
    error,
    confirm,
    isStreaming,
  } = useStreamingReview(sessionId, contractText)

  return (
    <div className="review-stream">
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem' }}>
        <button className="reset-button" onClick={onReset}>
          重新上传
        </button>
      </div>

      {error && <div className="error-message">错误: {error}</div>}

      {phase !== 'idle' && (
        <AgentCard title="实体抽取" eventType="extraction" status={extractedEntities ? 'done' : 'loading'}>
          {extractedEntities ? (
            <pre style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', overflow: 'auto' }}>
              {JSON.stringify(extractedEntities, null, 2)}
            </pre>
          ) : (
            <span style={{ color: 'var(--color-text-secondary)' }}>抽取中...</span>
          )}
        </AgentCard>
      )}

      {phase !== 'idle' && (
        <AgentCard title="路由决策" eventType="routing" status={routingDecision ? 'done' : 'loading'}>
          {routingDecision ? (
            <div>
              <p>主数据源: <strong>{routingDecision.primary_source}</strong></p>
              <p style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>{routingDecision.reason}</p>
            </div>
          ) : (
            <span style={{ color: 'var(--color-text-secondary)' }}>路由决策中...</span>
          )}
        </AgentCard>
      )}

      {issues.length > 0 && issues.map((issue, i) => (
        <AgentCard key={i} title={`风险条款 ${i + 1}`} eventType="logic_review" status="done">
          <p>
            <strong className={`risk-badge risk-badge--${issue.level}`}>
              {issue.level.toUpperCase()}
            </strong>
          </p>
          <p><strong>条款:</strong> {issue.clause}</p>
          <p><strong>问题:</strong> {issue.issue}</p>
          <p style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>法律依据: {issue.legal_reference}</p>
        </AgentCard>
      ))}

      {phase === 'breakpoint' && breakpointData && (
        <BreakpointCard data={breakpointData} onConfirm={confirm} onCancel={onReset} />
      )}

      {(phase === 'aggregation' || phase === 'complete') && (
        <AgentCard title="生成避坑指南" eventType="aggregation" status={phase === 'complete' ? 'done' : 'loading'}>
          <FinalReport paragraphs={reportParagraphs} isComplete={phase === 'complete'} />
        </AgentCard>
      )}

      {isStreaming && phase !== 'complete' && (
        <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--color-text-secondary)' }}>
          思考中<span style={{ animation: 'blink 1s infinite' }}>...</span>
        </div>
      )}
    </div>
  )
}
