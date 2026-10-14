import { useEffect, useRef } from 'react'
import type { AgentEvent, SpecialistReport, TicketDecision } from '../types'
import { AGENT_BY_NAME, requestText, toolCalls } from '../agents'
import { AgentBadge } from './AgentIcon'

// One readable line per meaningful agent step. "model_request" steps are
// plumbing (the prompt going back to the model), so they are not shown.
function Line({ e }: { e: AgentEvent }) {
  const meta = AGENT_BY_NAME[e.agent]
  const time = new Date(e.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  let body: React.ReactNode = null
  let kind = e.step_type as string

  if (e.step_type === 'task_received') {
    const from = e.depth > 0 ? AGENT_BY_NAME[e.chain[e.chain.length - 2]].label : null
    body = <p className="said">{from && <span className="from">From {from}: </span>}{requestText(e)}</p>
  } else if (e.step_type === 'model_response') {
    const calls = toolCalls(e)
    const handoffs = calls.filter(c => c.tool.startsWith('ask_'))
    const tools = calls.filter(c => !c.tool.startsWith('ask_') && c.tool !== 'final_result')
    if (!handoffs.length && !tools.length) return null // the final answer shows below as final_output
    kind = handoffs.length ? 'handoff' : 'tools'
    body = (
      <>
        {e.said && <p className="said">{e.said}</p>}
        {tools.length > 0 && (
          <div className="chips">
            {tools.map((c, i) => (
              <code key={i} className="chip" title={JSON.stringify(c.args)}>{c.tool}</code>
            ))}
          </div>
        )}
        {handoffs.map((c, i) => (
          <p key={i} className="handoff-line">
            → <AgentBadge agent={c.tool.slice(4) as AgentEvent['agent']} />
            <span className="muted"> “{String(c.args.request ?? '')}”</span>
          </p>
        ))}
      </>
    )
  } else if (e.step_type === 'tool_results') {
    const names = e.tools_used.concat(e.delegated_to.map(d => `${AGENT_BY_NAME[d].label} replied`))
    if (!names.length) return null
    body = <p className="muted small">✓ Got results: {names.join(', ')}</p>
  } else if (e.step_type === 'final_output') {
    const out = e.outputs as Partial<TicketDecision & SpecialistReport>
    body = <blockquote className={`report voice-${meta.voice}`}>{out.summary ?? out.answer}</blockquote>
  } else if (e.step_type === 'guardrail' || e.step_type === 'error') {
    body = <p className="warn">⚠ {e.said}</p>
  } else {
    return null
  }

  return (
    <li className={`feed-line ${kind}`} style={{ ['--agent' as string]: meta.color, ['--depth' as string]: e.depth }}>
      <div className="feed-head">
        <AgentBadge agent={e.agent} />
        {e.depth > 0 && <span className="muted small">via {e.chain.slice(0, -1).map(a => AGENT_BY_NAME[a].label).join(' → ')}</span>}
        <span className="time muted small">{time}</span>
      </div>
      {body}
    </li>
  )
}

export function ActivityFeed({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => { // follow new lines inside the feed only (never scroll the page)
    if (running && box.current) box.current.scrollTo({ top: box.current.scrollHeight, behavior: 'smooth' })
  }, [events.length, running])

  if (!events.length) {
    return <div className="empty">No agent activity for this ticket yet. Press <strong>Run agent team</strong> to start.</div>
  }
  return (
    <div className="feed-scroll" ref={box}>
      <ol className="feed">
        {events.map(e => <Line key={e.seq} e={e} />)}
      </ol>
      {running && <div className="typing"><span /><span /><span /> agents working</div>}
    </div>
  )
}
