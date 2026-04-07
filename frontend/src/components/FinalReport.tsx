interface FinalReportProps {
  paragraphs: string[]
  isComplete: boolean
}

export function FinalReport({ paragraphs, isComplete }: FinalReportProps) {
  return (
    <div className="final-report">
      {isComplete && (
        <div style={{ color: 'var(--color-low)', marginBottom: '1rem', fontWeight: 600 }}>
          ✅ 审查完成
        </div>
      )}
      {paragraphs.map((p, i) => (
        <p key={i} className={!isComplete && i === paragraphs.length - 1 ? 'cursor' : ''}>
          {p}
        </p>
      ))}
    </div>
  )
}
