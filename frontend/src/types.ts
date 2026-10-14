// Shapes returned by the Problem 7 backend (backend/main.py). No fake data: every
// value the dashboard shows comes from these responses.

export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  status: string
  is_open: boolean
  is_resolved: boolean
}

export interface TicketsResponse {
  today: string
  tickets: Ticket[]
}

export type StepType =
  | 'task_received' | 'model_request' | 'tool_results' | 'model_response'
  | 'final_output' | 'guardrail' | 'error'

export interface AgentEvent {
  seq: number
  run_id: string
  timestamp: string
  ticket_id: number
  agent: AgentName
  depth: number
  chain: AgentName[]
  step: number
  step_type: StepType
  said: string
  tools_used: string[]
  delegated_to: AgentName[]
  inputs: unknown
  outputs: unknown
  usage: { model: string; input_tokens: number; output_tokens: number } | null
}

export interface ActiveRun {
  run_id: string
  ticket_id: number
  status: string
  started_at: string
}

export interface RunUsage {
  requests: number
  tool_calls: number
  input_tokens: number
  output_tokens: number
  delegations: number
}

export interface RecentRun {
  run_id: string
  ticket_id: number
  status: string
  reason?: string | null
  ticket_resolved?: boolean
  finished_at: string
  usage?: RunUsage
}

export interface EventsResponse {
  events: AgentEvent[]
  next_since: number
  total_events: number
  active_run: ActiveRun | null
  recent_runs: RecentRun[]
}

export interface Approval {
  id: string
  created_at: string
  run_id: string
  ticket_id: number
  proposed_by: AgentName
  type: 'payment' | 'purchase'
  payment_kind: 'rent' | 'invoice' | 'restock'
  ref_id: number
  amount: number
  account: string
  payee: string
  approval_required_from: 'staff' | 'owner'
  details: Record<string, unknown>
  status: 'pending' | 'approved' | 'cancelled_by_reset'
  approved_by: string | null
  approver_role: 'staff' | 'owner' | null
  approved_at: string | null
  payment_id: number | null
}

export interface Checking {
  today: string
  name: string
  balance: number
  date: string
}

export interface ApproveResult {
  approval: Approval
  payment: { id: number; kind: string; amount: number; approved_by: string }
  balance_before: number
  balance_after: number
  lease_next_due: string | null
  ticket_status: string
}

// Final answers inside final_output events (backend/models.py).
export interface Proposal {
  kind: string
  summary: string
  amount_usd: number | null
  requires_human_approval: boolean
  approver: string
  source_tool: string
}

export interface TicketDecision {
  ticket_id: number
  ticket_type: string
  status: 'ready_for_human_review' | 'needs_more_info' | 'blocked'
  summary: string
  key_facts: string[]
  recommended_actions: Proposal[]
  customer_reply_draft: string | null
  human_approvals_needed: string[]
  agents_consulted: AgentName[]
  risks: string[]
}

export interface SpecialistReport {
  agent: AgentName
  ticket_id: number
  answer: string
  facts: string[]
  proposals: Proposal[]
  risks: string[]
  unresolved: string[]
}
