import type { AgentProgress } from "../types"

interface Props {
  agents: AgentProgress[]
}

const STATUS_LABELS: Record<string, string> = {
  started: "审查中...",
  completed: "已完成",
  degraded: "已降级",
}

export function AgentProgressPanel({ agents }: Props) {
  if (agents.length === 0) return null

  return (
    <div className="agent-progress-panel" style={{ padding: "12px", borderRadius: "8px", background: "rgba(0,0,0,0.03)" }}>
      <h4 style={{ margin: "0 0 8px", fontSize: "14px", fontWeight: 600 }}>Agent 审查进度</h4>
      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {agents.map((agent) => (
          <li key={agent.agent_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid rgba(0,0,0,0.06)", opacity: agent.status === "degraded" ? 0.6 : 1 }}>
            <span style={{ fontWeight: 500 }}>{agent.role}</span>
            <span style={{ fontSize: "13px", color: agent.status === "completed" ? "#22c55e" : agent.status === "degraded" ? "#f59e0b" : "#3b82f6" }}>
              {STATUS_LABELS[agent.status] || agent.status}
              {agent.status === "completed" && agent.completed > 0 && <span style={{ marginLeft: 6, opacity: 0.7 }}>({agent.completed})</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
