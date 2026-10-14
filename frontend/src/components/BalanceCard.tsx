import { useEffect, useRef, useState } from 'react'
import type { Checking } from '../types'
import { money } from '../agents'

// The balance counts to its new value, and a payment makes the card pulse
// with a "−$amount" chip, so you can see the money leave.
export function BalanceCard({ checking, history }: { checking: Checking | null; history: number[] }) {
  const target = checking?.balance ?? null
  const [shown, setShown] = useState<number | null>(target)
  const [delta, setDelta] = useState<number | null>(null)
  const prev = useRef<number | null>(target)

  useEffect(() => {
    if (target == null) return
    const from = prev.current ?? target
    prev.current = target
    if (from === target) { setShown(target); return }
    setDelta(target - from)
    const start = performance.now()
    let frame = 0
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / 1100)
      const ease = 1 - Math.pow(1 - k, 3)
      setShown(from + (target - from) * ease)
      if (k < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    // Browsers pause animation frames in hidden tabs; always land on the real value.
    const settle = setTimeout(() => setShown(target), 1200)
    const clear = setTimeout(() => setDelta(null), 4000)
    return () => { cancelAnimationFrame(frame); clearTimeout(settle); clearTimeout(clear) }
  }, [target])

  const max = Math.max(...history, 1)
  const points = history.map((v, i) => `${history.length > 1 ? (i / (history.length - 1)) * 100 : 50},${30 - (v / max) * 26}`).join(' ')

  return (
    <section className={`glass balance ${delta != null ? (delta < 0 ? 'drop' : 'rise') : ''}`} aria-live="polite" tabIndex={-1}>
      <div className="balance-label">Checking balance</div>
      <div className="balance-value">{shown == null ? '—' : money(shown)}</div>
      {delta != null && <span className={`delta ${delta < 0 ? 'neg' : 'pos'}`}>{delta < 0 ? '−' : '+'}{money(Math.abs(delta))}</span>}
      <div className="balance-foot muted small">
        {checking ? <>cash_accounts · as of {checking.date}</> : 'Loading…'}
      </div>
      {history.length > 1 && (
        <svg className="spark" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true">
          <polyline points={points} />
        </svg>
      )}
    </section>
  )
}
