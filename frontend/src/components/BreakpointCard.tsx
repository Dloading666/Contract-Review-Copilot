import { BreakpointQuestion } from '../types'

interface BreakpointCardProps {
  data: BreakpointQuestion
  onConfirm: () => void
  onCancel: () => void
}

export function BreakpointCard({ data, onConfirm, onCancel }: BreakpointCardProps) {
  return (
    <div className="breakpoint-card">
      <h3>⚠️ 需要确认</h3>
      <p>{data.question}</p>
      <p>
        共检测到 {data.issues_count} 条风险：
        {data.critical_count > 0 && ` ${data.critical_count} 条高危`}
        {data.high_count > 0 && ` ${data.high_count} 条高风险`}
        {data.medium_count > 0 && ` ${data.medium_count} 条中风险`}
      </p>
      <div className="breakpoint-card-actions">
        <button className="btn-confirm" onClick={onConfirm}>
          确认继续
        </button>
        <button className="btn-cancel" onClick={onCancel}>
          重新上传
        </button>
      </div>
    </div>
  )
}
