import type { AgentName } from '../types'
import { AGENTS, type AgentState } from '../agents'
import { AgentIcon } from './AgentIcon'

// Boss sits on top; the four specialists sit on an arc below. Lines light up the
// first time one agent hands work to another during the run.
const POS: Record<AgentName, { x: number; y: number }> = {
  boss: { x: 50, y: 13 },
  inventory: { x: 12, y: 42 },
  accounting: { x: 36, y: 62 },
  facilities: { x: 64, y: 62 },
  customer_service: { x: 88, y: 42 },
}

const STATUS_LABEL: Record<AgentState['status'], string> = {
  idle: 'Idle', thinking: 'Thinking', working: 'Using tools', 'handing-off': 'Delegating', done: 'Done', stopped: 'Stopped',
}

interface Props {
  states: Record<AgentName, AgentState>
  edges: Set<string>
}

export function Constellation({ states, edges }: Props) {
  const pairs: [AgentName, AgentName][] = []
  AGENTS.forEach((a, i) => AGENTS.slice(i + 1).forEach(b => pairs.push([a.name, b.name])))

  return (
    <div className="constellation" role="group" aria-label="Agent team">
      <svg className="links" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {pairs.map(([a, b]) => {
          const lit = edges.has(`${a}>${b}`) || edges.has(`${b}>${a}`)
          return (
            <line key={`${a}-${b}`} x1={POS[a].x} y1={POS[a].y} x2={POS[b].x} y2={POS[b].y}
              className={lit ? 'link lit' : 'link'} vectorEffect="non-scaling-stroke" />
          )
        })}
      </svg>
      {AGENTS.map(a => {
        const s = states[a.name]
        return (
          <div key={a.name} className={`node ${s.status}`} tabIndex={-1}
            style={{ left: `${POS[a.name].x}%`, top: `${POS[a.name].y}%`, ['--agent' as string]: a.color }}>
            <div className="node-orb"><AgentIcon agent={a.name} size={22} /></div>
            <div className="node-label">{a.label}</div>
            <div className="node-status">{STATUS_LABEL[s.status]}</div>
            <div className="node-action" title={s.action}>{s.status === 'idle' ? a.role : s.action}</div>
          </div>
        )
      })}
    </div>
  )
}
