/**
 * AlertDock.tsx — insufficient_reserve_alert banner + acknowledge button (§7.1 / §19.2).
 *
 * F4 — reads `latchedAlert` from the store (NOT latestTick.insufficient_reserve_alert).
 * The backend sets insufficient_reserve_alert=true on exactly one tick (the staging
 * tick); reading the raw flag would make the banner flash for one frame (~0.5 s at 10×)
 * and disappear before the operator can act.  The store latches on rising edge and only
 * clears on Acknowledge — see tickStore.ts for the latch design.
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
  const tick          = useTickStore(s => s.latestTick)
  const latchedAlert  = useTickStore(s => s.latchedAlert)
  const acknowledge   = useTickStore(s => s.acknowledgeAlert)

  const showAlert = latchedAlert !== null

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
              Alert fired at tick #{latchedAlert.tick_index}
              {' · '}
              sim time{' '}
              {latchedAlert.sim_time_seconds.toFixed(0)} s
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
          onClick={() => acknowledge(latchedAlert.tick_index)}
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
