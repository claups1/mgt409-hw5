// Agent identities and helpers that turn raw audit events into what the UI shows.
import type { AgentEvent, AgentName, SpecialistReport, TicketDecision } from './types'

export interface AgentMeta {
  name: AgentName
  label: string
  role: string
  color: string // muted accent used for the avatar, feed rail, and constellation node
  voice: 'memo' | 'ledger' | 'field' | 'notice' | 'chat'
}

export const AGENTS: AgentMeta[] = [
  { name: 'boss', label: 'Boss', role: 'Coordinates the team and writes the plan', color: '#8b9cf7', voice: 'memo' },
  { name: 'inventory', label: 'Inventory', role: 'Stock, vendors, restocks', color: '#3fb8a9', voice: 'field' },
  { name: 'accounting', label: 'Accounting', role: 'Cash, invoices, payments, margins', color: '#d6a54a', voice: 'ledger' },
  { name: 'facilities', label: 'Facilities', role: 'Lease, rent, the shop space', color: '#a58bdf', voice: 'notice' },
  { name: 'customer_service', label: 'Customer Service', role: 'Customer replies', color: '#5aa6e0', voice: 'chat' },
]

export const AGENT_BY_NAME = Object.fromEntries(AGENTS.map(a => [a.name, a])) as Record<AgentName, AgentMeta>

export const money = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export const TICKET_TYPE_LABEL: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price override',
}

/** Delegated prompts look like "Boss asked you about ticket 102:\n\n<request>\n\nAnswer only..." */
export function requestText(e: AgentEvent): string {
  if (e.depth === 0) return 'New ticket arrived. Investigating and deciding who to involve.'
  const parts = e.said.split('\n\n')
  return parts.length >= 2 ? parts[1] : e.said
}

interface ToolCall { tool: string; args: Record<string, unknown> }
export const toolCalls = (e: AgentEvent): ToolCall[] => (Array.isArray(e.inputs) ? (e.inputs as ToolCall[]) : [])

export type AgentStatus = 'idle' | 'thinking' | 'working' | 'handing-off' | 'done' | 'stopped'

export interface AgentState {
  status: AgentStatus
  action: string
  steps: number
}

/** What each agent is doing right now, from the latest events of one run. */
export function agentStates(events: AgentEvent[]): Record<AgentName, AgentState> {
  const states = Object.fromEntries(
    AGENTS.map(a => [a.name, { status: 'idle', action: 'Standing by', steps: 0 } as AgentState]),
  ) as Record<AgentName, AgentState>
  for (const e of events) {
    const s = states[e.agent]
    s.steps += 1
    if (e.step_type === 'task_received') Object.assign(s, { status: 'thinking', action: 'Picked up a request' })
    else if (e.step_type === 'model_request') Object.assign(s, { status: 'thinking', action: 'Thinking…' })
    else if (e.step_type === 'model_response') {
      if (e.delegated_to.length)
        Object.assign(s, { status: 'handing-off', action: `Asking ${e.delegated_to.map(n => AGENT_BY_NAME[n].label).join(' & ')}` })
      else if (e.tools_used.length) Object.assign(s, { status: 'working', action: `Checking ${e.tools_used.join(', ')}` })
      else Object.assign(s, { status: 'thinking', action: 'Writing the answer' })
    } else if (e.step_type === 'tool_results') Object.assign(s, { status: 'thinking', action: 'Reading results' })
    else if (e.step_type === 'final_output') Object.assign(s, { status: 'done', action: 'Reported back' })
    else Object.assign(s, { status: 'stopped', action: e.said || 'Stopped by a guardrail' })
  }
  return states
}

/** Hand-offs seen in a run, as "from>to" keys for the constellation. */
export function delegationEdges(events: AgentEvent[]): Set<string> {
  const edges = new Set<string>()
  for (const e of events) for (const to of e.delegated_to) if (e.step_type === 'model_response') edges.add(`${e.agent}>${to}`)
  return edges
}

export interface AgentSummary {
  agent: AgentName
  steps: number
  tools: [string, number][]
  delegatedTo: AgentName[]
  askedBy: AgentName[]
  final: SpecialistReport | TicketDecision | null
  inputTokens: number
  outputTokens: number
}

/** Per-agent summary of one run (only agents that took part). */
export function summarize(events: AgentEvent[]): AgentSummary[] {
  const by = new Map<AgentName, AgentSummary>()
  for (const e of events) {
    let s = by.get(e.agent)
    if (!s) {
      s = { agent: e.agent, steps: 0, tools: [], delegatedTo: [], askedBy: [], final: null, inputTokens: 0, outputTokens: 0 }
      by.set(e.agent, s)
    }
    s.steps += 1
    if (e.step_type === 'task_received' && e.depth > 0) {
      const from = e.chain[e.chain.length - 2]
      if (from && !s.askedBy.includes(from)) s.askedBy.push(from)
    }
    if (e.step_type === 'model_response') {
      for (const t of e.tools_used) {
        const hit = s.tools.find(x => x[0] === t)
        if (hit) hit[1] += 1
        else s.tools.push([t, 1])
      }
      for (const d of e.delegated_to) if (!s.delegatedTo.includes(d)) s.delegatedTo.push(d)
      if (e.usage) { s.inputTokens += e.usage.input_tokens; s.outputTokens += e.usage.output_tokens }
    }
    if (e.step_type === 'final_output' && e.outputs) s.final = e.outputs as SpecialistReport | TicketDecision
  }
  const order = AGENTS.map(a => a.name)
  return [...by.values()].sort((a, b) => order.indexOf(a.agent) - order.indexOf(b.agent))
}

/** Split a ticket's events into runs and return the most recent run's events. */
export function latestRun(events: AgentEvent[]): { runId: string | null; events: AgentEvent[] } {
  if (!events.length) return { runId: null, events: [] }
  const runId = events.reduce((a, b) => (b.seq > a.seq ? b : a)).run_id
  return { runId, events: events.filter(e => e.run_id === runId) }
}
