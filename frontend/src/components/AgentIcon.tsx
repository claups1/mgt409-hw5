import type { AgentName } from '../types'
import { AGENT_BY_NAME } from '../agents'

// One simple line icon per agent, so each is recognisable at a glance (not just by colour).
const PATHS: Record<AgentName, string> = {
  boss: 'M4 17h16l-1.5-9-4.5 4-2-6-2 6-4.5-4L4 17Zm0 2h16',          // crown
  inventory: 'M4 8l8-4 8 4v8l-8 4-8-4V8Zm0 0l8 4 8-4M12 12v8',       // box
  accounting: 'M6 4h12v16H6V4Zm3 4h6M9 11h6M9 14h3M14 17h1',          // ledger
  facilities: 'M4 20V9l8-5 8 5v11M9 20v-6h6v6M4 20h16',               // storefront
  customer_service: 'M5 6h14v9H10l-4 3v-3H5V6Zm4 4h6',                // chat bubble
}

export function AgentIcon({ agent, size = 20 }: { agent: AgentName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true"
      stroke={AGENT_BY_NAME[agent].color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d={PATHS[agent]} />
    </svg>
  )
}

export function AgentBadge({ agent }: { agent: AgentName }) {
  const meta = AGENT_BY_NAME[agent]
  return (
    <span className="agent-badge" style={{ ['--agent' as string]: meta.color }}>
      <AgentIcon agent={agent} size={14} />
      {meta.label}
    </span>
  )
}
