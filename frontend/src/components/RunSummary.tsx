import type { RecentRun, SpecialistReport, TicketDecision } from '../types'
import { AGENT_BY_NAME, money, type AgentSummary } from '../agents'
import { AgentBadge, AgentIcon } from './AgentIcon'

const DECISION_LABEL: Record<TicketDecision['status'], string> = {
  ready_for_human_review: 'Ready for human review',
  needs_more_info: 'Needs more info',
  blocked: 'Blocked',
}

function BossDecision({ d }: { d: TicketDecision }) {
  return (
    <div className="decision glass-inner">
      <div className="decision-head">
        <AgentIcon agent="boss" size={18} />
        <h3>Boss's plan</h3>
        <span className={`status-pill ${d.status}`}>{DECISION_LABEL[d.status] ?? d.status}</span>
      </div>
      <p className="memo">{d.summary}</p>
      {d.recommended_actions.length > 0 && (
        <ul className="actions">
          {d.recommended_actions.map((a, i) => (
            <li key={i}>
              <span className={`kind kind-${a.kind}`}>{a.kind.replace('_', ' ')}</span>
              <span>{a.summary}</span>
              <span className="muted small nowrap">
                {a.amount_usd != null && <strong>{money(a.amount_usd)} · </strong>}
                {a.requires_human_approval ? `needs ${a.approver}` : 'no approval'}
              </span>
            </li>
          ))}
        </ul>
      )}
      {d.customer_reply_draft && (
        <div className="reply-draft">
          <div className="muted small">Customer reply draft (not sent)</div>
          <p>{d.customer_reply_draft}</p>
        </div>
      )}
      {d.risks.length > 0 && <p className="muted small">Risks: {d.risks.join(' · ')}</p>}
    </div>
  )
}

function AgentCard({ s }: { s: AgentSummary }) {
  const meta = AGENT_BY_NAME[s.agent]
  const report = s.agent === 'boss' ? null : (s.final as SpecialistReport | null)
  return (
    <article className="agent-card glass-inner" style={{ ['--agent' as string]: meta.color }}>
      <header>
        <AgentBadge agent={s.agent} />
        <span className="muted small">{s.steps} steps · {(s.inputTokens + s.outputTokens).toLocaleString()} tokens</span>
      </header>
      {s.askedBy.length > 0 && <p className="small muted">Asked by {s.askedBy.map(a => AGENT_BY_NAME[a].label).join(', ')}</p>}
      {s.tools.length > 0 && (
        <div className="chips">
          {s.tools.map(([t, n]) => <code key={t} className="chip">{t}{n > 1 ? ` ×${n}` : ''}</code>)}
        </div>
      )}
      {s.delegatedTo.length > 0 && (
        <p className="small">Handed work to {s.delegatedTo.map(a => AGENT_BY_NAME[a].label).join(', ')}</p>
      )}
      {report?.answer && <p className={`report-text voice-${meta.voice}`}>{report.answer}</p>}
      {s.agent === 'boss' && s.final && <p className="small muted">Wrote the final plan above.</p>}
    </article>
  )
}

interface Props {
  summaries: AgentSummary[]
  decision: TicketDecision | null
  run: RecentRun | null
  running: boolean
}

export function RunSummary({ summaries, decision, run, running }: Props) {
  if (running) return <div className="empty">The summary appears when the run finishes.</div>
  if (!summaries.length) return <div className="empty">Run the agent team to see what each agent did.</div>
  return (
    <div className="summary">
      {run && run.status !== 'ok' && <p className="warn">⚠ Run {run.status}{run.reason ? `: ${run.reason}` : ''}</p>}
      {decision && <BossDecision d={decision} />}
      <div className="agent-cards">
        {summaries.map(s => <AgentCard key={s.agent} s={s} />)}
      </div>
    </div>
  )
}
