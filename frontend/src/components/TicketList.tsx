import type { ActiveRun, Ticket } from '../types'
import { TICKET_TYPE_LABEL } from '../agents'

interface Props {
  tickets: Ticket[]
  selectedId: number | null
  activeRun: ActiveRun | null
  justResolved: Set<number>
  onSelect: (id: number) => void
  onRun: (id: number) => void
}

const TYPE_GLYPH: Record<string, string> = { customer_order: '👕', rent_notice: '🏠', price_override: '🏷️' }

export function TicketList({ tickets, selectedId, activeRun, justResolved, onSelect, onRun }: Props) {
  return (
    <section className="glass panel tickets" aria-labelledby="tickets-title" tabIndex={-1}>
      <header className="panel-head">
        <h2 id="tickets-title">Tickets</h2>
        <span className="muted small">{tickets.filter(t => t.is_open).length} open</span>
      </header>
      <ul className="ticket-list">
        {tickets.map(t => {
          const running = activeRun?.ticket_id === t.id
          const classes = [
            'ticket',
            t.id === selectedId && 'selected',
            t.is_resolved && 'resolved',
            justResolved.has(t.id) && 'glow-up',
            running && 'running',
          ].filter(Boolean).join(' ')
          return (
            <li key={t.id}>
              <div className={classes} role="button" tabIndex={0} aria-pressed={t.id === selectedId}
                onClick={() => onSelect(t.id)}
                onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && onSelect(t.id)}>
                <div className="ticket-top">
                  <span className="ticket-glyph" aria-hidden="true">{TYPE_GLYPH[t.type] ?? '🎫'}</span>
                  <span className="ticket-id">#{t.id}</span>
                  <span className={`status-pill ${running ? 'running' : t.status}`}>
                    {running ? 'Agents working' : t.is_resolved ? 'Resolved' : 'Open'}
                  </span>
                </div>
                <div className="ticket-subject">{t.subject}</div>
                <div className="ticket-meta muted small">{TICKET_TYPE_LABEL[t.type] ?? t.type} · {t.requester}</div>
                {t.id === selectedId && (
                  <button className="btn primary run-btn"
                    disabled={!t.is_open || !!activeRun}
                    onClick={e => { e.stopPropagation(); onRun(t.id) }}>
                    {running ? <><span className="spinner" /> Running…</>
                      : t.is_resolved ? 'Resolved ✓'
                      : activeRun ? `Busy with #${activeRun.ticket_id}`
                      : 'Run agent team'}
                  </button>
                )}
                {t.is_resolved && t.id !== selectedId && <span className="stamp" aria-hidden="true">RESOLVED</span>}
              </div>
            </li>
          )
        })}
      </ul>
      {tickets.some(t => t.is_resolved) && (
        <p className="muted small hint">Resolved tickets can't run again. Use “Reset data” to start over.</p>
      )}
    </section>
  )
}
