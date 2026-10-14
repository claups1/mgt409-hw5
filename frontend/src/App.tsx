import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, allTicketEvents, API_URL } from './api'
import { agentStates, delegationEdges, latestRun, money, summarize } from './agents'
import type { ActiveRun, AgentEvent, Approval, Checking, RecentRun, Ticket, TicketDecision } from './types'
import { TicketList } from './components/TicketList'
import { Constellation } from './components/Constellation'
import { ActivityFeed } from './components/ActivityFeed'
import { RunSummary } from './components/RunSummary'
import { ApprovalsPanel } from './components/ApprovalsPanel'
import { BalanceCard } from './components/BalanceCard'

interface Toast { id: number; text: string; tone: 'ok' | 'warn' }

const END = 1_000_000_000 // "since" past the end: returns no events, just totals and run status

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [today, setToday] = useState('')
  const [checking, setChecking] = useState<Checking | null>(null)
  const [history, setHistory] = useState<number[]>([])
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [shown, setShown] = useState<{ runId: string | null; events: AgentEvent[] }>({ runId: null, events: [] })
  const [activeRun, setActiveRun] = useState<ActiveRun | null>(null)
  const [runEvents, setRunEvents] = useState<AgentEvent[]>([])
  const [recentRuns, setRecentRuns] = useState<RecentRun[]>([])
  const [justResolved, setJustResolved] = useState<Set<number>>(new Set())
  const [tab, setTab] = useState<'live' | 'summary'>('live')
  const [online, setOnline] = useState(true)
  const [toasts, setToasts] = useState<Toast[]>([])
  const cursor = useRef(0)

  const toast = useCallback((text: string, tone: Toast['tone'] = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts(t => [...t, { id, text, tone }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 5000)
  }, [])

  const refresh = useCallback(async () => {
    try {
      const [t, c, a] = await Promise.all([api.tickets(), api.checking(), api.approvals()])
      setTickets(t.tickets)
      setToday(t.today)
      setChecking(c)
      setHistory(h => (h[h.length - 1] === c.balance ? h : [...h, c.balance].slice(-20)))
      setApprovals(a.approvals)
      setSelectedId(id => id ?? t.tickets[0]?.id ?? null)
      setOnline(true)
    } catch {
      setOnline(false)
    }
  }, [])

  const loadHistory = useCallback(async (ticketId: number) => {
    try {
      const { events } = await allTicketEvents(ticketId)
      setShown(latestRun(events))
    } catch {
      setOnline(false)
    }
  }, [])

  // first load: data, plus pick up a run that is already going
  useEffect(() => {
    refresh()
    api.events({ since: END, limit: 1 }).then(r => {
      setRecentRuns(r.recent_runs)
      if (r.active_run) {
        cursor.current = 0
        setActiveRun(r.active_run)
        setSelectedId(r.active_run.ticket_id)
      }
    }).catch(() => setOnline(false))
    const id = setInterval(refresh, 10_000)
    return () => clearInterval(id)
  }, [refresh])

  useEffect(() => {
    if (selectedId != null) loadHistory(selectedId)
  }, [selectedId, loadHistory])

  // live polling while a run is going
  useEffect(() => {
    if (!activeRun) return
    let stopped = false
    const poll = async () => {
      try {
        const r = await api.events({ since: cursor.current, runId: activeRun.run_id })
        if (stopped) return
        cursor.current = r.next_since
        if (r.events.length) setRunEvents(ev => [...ev, ...r.events])
        setRecentRuns(r.recent_runs)
        if (!r.active_run || r.active_run.run_id !== activeRun.run_id) {
          const done = r.recent_runs.find(x => x.run_id === activeRun.run_id)
          setActiveRun(null)
          await refresh()
          await loadHistory(activeRun.ticket_id)
          setTab('summary')
          if (done?.ticket_resolved) {
            setJustResolved(s => new Set(s).add(activeRun.ticket_id))
            setTimeout(() => setJustResolved(s => { const n = new Set(s); n.delete(activeRun.ticket_id); return n }), 4000)
            toast(`Ticket #${activeRun.ticket_id} resolved. The team finished its work.`)
          } else if (done) {
            toast(`Run on #${activeRun.ticket_id} ended: ${done.status}${done.reason ? ` (${done.reason})` : ''}`, 'warn')
          }
          return
        }
      } catch {
        setOnline(false)
      }
      if (!stopped) timer = setTimeout(poll, 900)
    }
    let timer = setTimeout(poll, 300)
    return () => { stopped = true; clearTimeout(timer) }
  }, [activeRun, refresh, loadHistory, toast])

  async function runTicket(id: number) {
    try {
      const totals = await api.events({ since: END, limit: 1 })
      cursor.current = totals.total_events
      setRunEvents([])
      const r = await api.runTicket(id)
      setSelectedId(id)
      setTab('live')
      setActiveRun({ run_id: r.run_id, ticket_id: r.ticket_id, status: r.status, started_at: r.started_at })
    } catch (e) {
      toast((e as Error).message, 'warn')
    }
  }

  async function approve(a: Approval, name: string, role: 'staff' | 'owner'): Promise<string | null> {
    try {
      const r = await api.approve(a.id, name.trim(), role)
      toast(`Paid ${money(a.amount)} to ${a.payee}. Checking is now ${money(r.balance_after)}.`)
      await refresh()
      return null
    } catch (e) {
      return (e as Error).message
    }
  }

  async function reset() {
    if (!confirm('Reset the shop database to its original data? Payments and resolved tickets will be undone.')) return
    try {
      const r = await api.reset()
      toast(r.matches_original ? 'Database restored to the original data.' : 'Reset finished but did not match.', r.matches_original ? 'ok' : 'warn')
      setHistory([])
      await refresh()
      if (selectedId != null) await loadHistory(selectedId)
    } catch (e) {
      toast((e as Error).message, 'warn')
    }
  }

  const runningHere = activeRun != null && activeRun.ticket_id === selectedId
  const events = runningHere ? runEvents : shown.events
  const states = useMemo(() => agentStates(events), [events])
  const edges = useMemo(() => delegationEdges(events), [events])
  const summaries = useMemo(() => summarize(events), [events])
  const decision = useMemo(() => {
    const f = events.find(e => e.step_type === 'final_output' && e.depth === 0 && e.agent === 'boss')
    return (f?.outputs as TicketDecision | undefined) ?? null
  }, [events])
  const selected = tickets.find(t => t.id === selectedId) ?? null
  const runInfo = recentRuns.find(r => r.run_id === shown.runId) ?? null
  const pending = approvals.filter(a => a.status === 'pending')
  const approved = approvals.filter(a => a.status === 'approved').reverse()

  return (
    <div className="app">
      <div className="aurora" aria-hidden="true"><span /><span /><span /></div>

      <header className="topbar glass">
        <div className="brand">
          <div className="logo">CC</div>
          <div>
            <div className="brand-name">Campus Customs</div>
            <div className="brand-sub">Agent Ops Desk</div>
          </div>
        </div>
        <div className="topbar-mid">
          {today && <span className="pill">Shop day · {new Date(today + 'T12:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}</span>}
          <span className={`pill ${online ? 'online' : 'offline'}`}><i />{online ? 'Backend connected' : `Backend offline (${API_URL})`}</span>
          {activeRun && <span className="pill live"><i />Live run · #{activeRun.ticket_id}</span>}
        </div>
        <button className="btn ghost" onClick={reset} disabled={!!activeRun}>Reset data</button>
      </header>

      <main className="grid">
        <TicketList tickets={tickets} selectedId={selectedId} activeRun={activeRun}
          justResolved={justResolved} onSelect={setSelectedId} onRun={runTicket} />

        <section className="glass panel activity" aria-labelledby="activity-title" tabIndex={-1}>
          <header className="panel-head">
            <h2 id="activity-title">
              Agent activity{selected && <span className="muted"> · #{selected.id} {selected.subject}</span>}
            </h2>
            <div className="tabs" role="tablist">
              <button role="tab" aria-selected={tab === 'live'} className={tab === 'live' ? 'on' : ''} onClick={() => setTab('live')}>
                {runningHere ? 'Live' : 'Activity'}
              </button>
              <button role="tab" aria-selected={tab === 'summary'} className={tab === 'summary' ? 'on' : ''} onClick={() => setTab('summary')}>
                Summary
              </button>
            </div>
          </header>
          <Constellation states={states} edges={edges} />
          <div className="activity-body">
            {tab === 'live'
              ? <ActivityFeed events={events} running={runningHere} />
              : <RunSummary summaries={summaries} decision={decision} run={runInfo} running={runningHere} />}
          </div>
        </section>

        <div className="side">
          <BalanceCard checking={checking} history={history} />
          <ApprovalsPanel pending={pending} approved={approved} onApprove={approve} />
        </div>
      </main>

      <div className="toasts" role="status">
        {toasts.map(t => <div key={t.id} className={`toast glass ${t.tone}`}>{t.text}</div>)}
      </div>
    </div>
  )
}
