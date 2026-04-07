interface AgentCardProps {
  title: string
  eventType: string
  status: 'loading' | 'done'
  accentColor?: string
  children: React.ReactNode
}

export function AgentCard({ title, eventType, status, children }: AgentCardProps) {
  return (
    <div className={`agent-card agent-card--${eventType}`}>
      <div className="agent-card-header">
        <span className={`status-dot status-dot--${status}`} />
        {title}
      </div>
      <div className="agent-card-content">{children}</div>
    </div>
  )
}
