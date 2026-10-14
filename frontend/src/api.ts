// Thin client for the Problem 7 backend. Base URL: http://localhost:8000
// (override with VITE_API_URL in frontend/.env.local if needed).
import type {
  ApproveResult, Approval, Checking, EventsResponse, TicketsResponse,
} from './types'

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(API_URL + path, init)
  } catch {
    throw new ApiError(0, `Can't reach the backend at ${API_URL}. Is uvicorn running?`)
  }
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = body?.detail
    const message = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map((d: { msg: string }) => d.msg).join('; ')
      : detail?.message ?? `HTTP ${res.status}`
    throw new ApiError(res.status, message)
  }
  return body as T
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })

export const api = {
  tickets: () => request<TicketsResponse>('/tickets'),
  checking: () => request<Checking>('/cash/checking'),
  approvals: (status?: string) =>
    request<{ approvals: Approval[] }>(`/approvals${status ? `?status=${status}` : ''}`),
  events: (params: { since?: number; runId?: string; ticketId?: number; limit?: number }) => {
    const q = new URLSearchParams()
    q.set('since', String(params.since ?? 0))
    q.set('limit', String(params.limit ?? 1000))
    if (params.runId) q.set('run_id', params.runId)
    if (params.ticketId) q.set('ticket_id', String(params.ticketId))
    return request<EventsResponse>(`/events?${q}`)
  },
  runTicket: (ticketId: number) =>
    post<{ run_id: string; ticket_id: number; status: string; started_at: string }>(`/tickets/${ticketId}/run`),
  approve: (id: string, approvedBy: string, role: 'staff' | 'owner') =>
    post<ApproveResult>(`/approvals/${id}/approve`, { approved_by: approvedBy, role, resolve_ticket: false }),
  reset: () => post<{ matches_original: boolean; pending_approvals_cancelled: number }>('/reset'),
}

/** All events for one ticket, paging through the audit trail. */
export async function allTicketEvents(ticketId: number) {
  const events = []
  let since = 0
  for (;;) {
    const page = await api.events({ since, ticketId, limit: 1000 })
    events.push(...page.events)
    if (page.next_since >= page.total_events || page.next_since === since) return { events, page }
    since = page.next_since
  }
}
