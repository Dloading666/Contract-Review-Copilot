// Shared TypeScript types for Contract Review Copilot

export interface ExtractedEntity {
  contract_type: string
  parties: { lessor: string; lessee: string }
  property: { address: string; area: string }
  rent: { monthly: number; currency: string; payment_cycle: string }
  deposit: { amount: number; conditions: string }
  lease_term: { start: string; end: string; duration_months: number }
  penalty_clause: string
}

export interface ClauseIssue {
  clause: string
  issue: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  risk_level: number
  legal_reference: string
}

export interface RoutingDecision {
  primary_source: 'pgvector' | 'duckduckgo'
  secondary_source: 'pgvector' | 'duckduckgo' | null
  reason: string
  local_context: string
  confidence: number
}

export interface BreakpointQuestion {
  needs_review: boolean
  question: string
  issues_count: number
  critical_count: number
  high_count: number
  medium_count: number
}

export interface SSEEvent {
  event: string
  data: unknown
}

export type ReviewPhase =
  | 'idle'
  | 'started'
  | 'extraction'
  | 'routing'
  | 'logic_review'
  | 'breakpoint'
  | 'aggregation'
  | 'complete'
  | 'error'
