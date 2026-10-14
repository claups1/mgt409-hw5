import { useState } from 'react'
import type { Approval } from '../types'
import { AGENT_BY_NAME, money } from '../agents'
import { AgentBadge } from './AgentIcon'

interface Props {
  pending: Approval[]
  approved: Approval[]
  onApprove: (a: Approval, name: string, role: 'staff' | 'owner') => Promise<string | null>
}

function describe(a: Approval): string {
  const d = a.details as Record<string, unknown>
  if (a.payment_kind === 'rent') return `Rent for lease ${a.ref_id}, due ${d.due_date}`
  if (a.payment_kind === 'invoice') return `Invoice #${a.ref_id}, due ${d.due_date}`
  return `Restock ${d.qty_to_order} × ${d.sku} size ${d.size}, arrives ~${d.earliest_arrival}`
}

function Card({ a, name, role, onApprove }: {
  a: Approval; name: string; role: 'staff' | 'owner'; onApprove: Props['onApprove']
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const d = a.details as Record<string, unknown>
  const cashAfter = (d.cash_after_this_payment as number | undefined)
  const afterAll = (d.cash_after_this_and_other_known_bills as number | undefined)
  const checks = d.checks as Record<string, boolean> | undefined
  const reserveShort = checks?.reserve_kept_after_other_known_bills === false // from propose_payment

  async function approve() {
    setBusy(true)
    setError(await onApprove(a, name, role))
    setBusy(false)
  }

  return (
    <li className="approval glass-inner" style={{ ['--agent' as string]: AGENT_BY_NAME[a.proposed_by].color }}>
      <div className="approval-top">
        <span className={`kind kind-${a.type}`}>{a.type}</span>
        <span className="muted small">#{a.ticket_id} · {a.id}</span>
      </div>
      <div className="approval-amount">{money(a.amount)}</div>
      <div className="approval-payee">to {a.payee}</div>
      <p className="small">{describe(a)}</p>
      {cashAfter != null && (
        <p className="small muted">
          Cash after: <strong>{money(cashAfter)}</strong>
          {afterAll != null && <> · after other known bills: <strong className={reserveShort ? 'neg' : ''}>{money(afterAll)}</strong>{reserveShort && ' (below reserve)'}</>}
        </p>
      )}
      {a.payment_kind === 'restock' && <p className="small muted">Estimate at catalog unit cost; stock arrives later.</p>}
      <div className="approval-foot">
        <span className="small">Prepared by <AgentBadge agent={a.proposed_by} /></span>
        <span className={`need need-${a.approval_required_from}`}>Needs {a.approval_required_from}</span>
      </div>
      <button className="btn approve" disabled={busy || !name.trim()} onClick={approve}>
        {busy ? <><span className="spinner" /> Approving…</> : `Approve & pay ${money(a.amount)}`}
      </button>
      {error && <p className="warn small">{error}</p>}
    </li>
  )
}

export function ApprovalsPanel({ pending, approved, onApprove }: Props) {
  const [name, setName] = useState(() => localStorage.getItem('approver-name') ?? '')
  const [role, setRole] = useState<'staff' | 'owner'>(
    () => (localStorage.getItem('approver-role') as 'staff' | 'owner') ?? 'staff',
  )
  const save = (n: string, r: 'staff' | 'owner') => {
    setName(n); setRole(r)
    localStorage.setItem('approver-name', n); localStorage.setItem('approver-role', r)
  }

  return (
    <section className="glass panel approvals" aria-labelledby="approvals-title" tabIndex={-1}>
      <header className="panel-head">
        <h2 id="approvals-title">Approvals</h2>
        {pending.length > 0 && <span className="count-badge">{pending.length}</span>}
      </header>
      <p className="muted small">Agents only prepare payments. Money moves when you approve.</p>
      <div className="approver">
        <input aria-label="Your name" placeholder="Your name" value={name} onChange={e => save(e.target.value, role)} />
        <div className="seg" role="radiogroup" aria-label="Your role">
          {(['staff', 'owner'] as const).map(r => (
            <button key={r} role="radio" aria-checked={role === r} className={role === r ? 'on' : ''}
              onClick={() => save(name, r)}>{r}</button>
          ))}
        </div>
      </div>
      {pending.length === 0 ? (
        <div className="empty small">Nothing waiting. Payments and purchases the agents prepare appear here.</div>
      ) : (
        <ul className="approval-list">
          {pending.map(a => <Card key={a.id} a={a} name={name} role={role} onApprove={onApprove} />)}
        </ul>
      )}
      {approved.length > 0 && (
        <details className="approved-log">
          <summary className="small muted">Approved ({approved.length})</summary>
          <ul>
            {approved.map(a => (
              <li key={a.id} className="small">
                ✓ {money(a.amount)} to {a.payee} · {a.approved_by} ({a.approver_role})
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
