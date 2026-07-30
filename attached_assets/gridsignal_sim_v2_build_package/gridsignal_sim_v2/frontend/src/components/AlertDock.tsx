/**
 * AlertDock.tsx — insufficient_reserve_alert banner + acknowledge button (§7.1 / §19.2).
 *
 * Visible only when insufficient_reserve_alert is true AND the alert has not
 * been locally acknowledged for the current tick_index.
 *
 * The Acknowledge button follows §2.3's "solid button = bounded reversible
 * action" affordance: pressing it is not destructive, and the banner re-appears
 * on a later tick_index if a new alert fires.
 *
 * STEP 7 BOUNDARY — local dismissal only:
 *   Acknowledging stores tick_index in the Zustand store (browser session only).
 *   POST /api/alerts/{id}/acknowledge — persistent server-side ack — is deferred
 *   to Step 8.  The button carries a visible note so the operator knows this is
 *   not a durable acknowledgment.
 */

import { useTickStore } from '../store/tickStore'

export function AlertDock() {
  const tick        = useTickStore(s => s.latestTick)
  const acked       = useTickStore(s => s.acknowledgedAlerts)
  const acknowledge = useTickStore(s => s.acknowledgeAlert)

  const alertActive   = tick?.insufficient_reserve_alert === true
  const alreadyAcked  = tick ? acked.has(tick.tick_index) : false
  const showAlert     = alertActive && !alreadyAcked

  if (!showAlert) {
    return (
      <section className="flex h-full flex-col items-center justify-center gap-1 p-4">
        <div className="font-mono text-xs text-muted">Alert dock</div>
        <div className="mt-2 rounded border border-border bg-surface px-3 py-1.5
                        font-mono text-xs text-muted">
          {tick ? 'No active alerts' : 'No active run'}
        </div>
      </section>
    )
  }

  return (
    <section className="flex h-full flex-col gap-3 p-4">
      <div className="font-mono text-xs uppercase tracking-wider text-muted">
        Alert dock
      </div>

      {/* Alert banner */}
      <div className="flex-1 rounded border border-warn/60 bg-warn/10 p-3 space-y-2">
        <div className="flex items-start gap-2">
          <span className="text-warn text-lg leading-none mt-0.5">⚠</span>
          <div className="space-y-0.5">
            <div className="font-mono text-sm font-semibold text-warn">
              Insufficient reserve
            </div>
            <div className="font-mono text-xs text-warn/70">
              Alert fired at tick #{tick?.tick_index ?? '—'}
              {' · '}
              sim time{' '}
              {tick
                ? `${tick.sim_time_seconds.toFixed(0)} s`
                : '—'}
            </div>
          </div>
        </div>

        <div className="font-mono text-xs text-muted leading-relaxed">
          BESS fleet cannot sustain the current shortfall for the full ramp-gap
          duration.  Stage additional turbine capacity or shed non-critical load.
        </div>
      </div>

      {/* Acknowledge — §2.3 solid button */}
      <div className="space-y-1">
        <button
          onClick={() => tick && acknowledge(tick.tick_index)}
          className="w-full rounded bg-warn px-4 py-2 font-mono text-sm font-semibold
                     text-canvas transition-colors hover:bg-warn/80 active:scale-95"
        >
          Acknowledge
        </button>
        <p className="font-mono text-[10px] text-muted text-center">
          Local dismissal only — persistent ack (POST /api/alerts/{'{id}'}/acknowledge)
          deferred to Step 8.
        </p>
      </div>
    </section>
  )
}
