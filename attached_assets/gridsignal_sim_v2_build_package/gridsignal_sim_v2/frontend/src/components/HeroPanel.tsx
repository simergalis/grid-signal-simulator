/**
 * HeroPanel.tsx — four-cell hero row (§19.2 / Design Spec §8.4).
 *
 * Cell 1 — Δt_lead: seconds until next GPU reaches full TDP (countdown).
 * Cell 2 — Bridge:  how long the BESS fleet can sustain current shortfall,
 *                   with basis label; red when 0 and alert latched.
 * Cell 3 — Thermal: absorbable MW of cooling headroom + time to limit;
 *                   amber when headroom < 5 % of rated capacity.
 * Cell 4 — Alerts:  AlertDock inline (latched banner + Acknowledge button).
 *
 * C2: dt_lead_next_s is min() across in-flight ramps, not sum().
 * F2: bess_bridging_seconds uses "predicted_peak" basis when applicable.
 * W1c: absorbable_mw / time_to_limit_s come from the live tick payload
 *      (stamped by the run loop before broadcast — not polled from /thermal).
 */

import { useTickStore } from '../store/tickStore'
import { AlertDock }    from './AlertDock'

function formatCountdown(s: number): string {
  if (s <= 0) return '—'
  if (s >= 60) {
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${m}m ${sec}s`
  }
  return `${s.toFixed(1)}s`
}

function formatBridge(seconds: number): string {
  if (seconds >= 86400) return 'full reserve'
  if (seconds <= 0)     return '0 s'
  if (seconds >= 3600) return `${(seconds / 3600).toFixed(1)} h`
  if (seconds >= 60)   return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `${seconds.toFixed(0)} s`
}

function formatTimeToLimit(s: number): string {
  if (s >= 86400) return '∞'
  if (s >= 3600)  return `${(s / 3600).toFixed(1)} h`
  if (s >= 60)    return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return `${s.toFixed(0)} s`
}

const BASIS_LABEL: Record<string, string> = {
  predicted_peak:  'predicted peak shortfall',
  current_demand:  'current demand',
  no_load:         '',
}

// ── Cell wrapper ─────────────────────────────────────────────────────────────

function Cell({
  label,
  children,
  accent,
}: {
  label: string
  children: React.ReactNode
  accent?: 'amber' | 'red' | 'none'
}) {
  const border = accent === 'amber' ? 'border-l-2 border-l-warn' :
                 accent === 'red'   ? 'border-l-2 border-l-danger' : ''
  return (
    <div className={`flex flex-col justify-between p-4 ${border}`}>
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted mb-2">
        {label}
      </div>
      {children}
    </div>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export function HeroPanel() {
  const tick         = useTickStore(s => s.latestTick)
  const latchedAlert = useTickStore(s => s.latchedAlert)
  const isInterp     = useTickStore(s => s.isInterpolated)

  return (
    <section className="grid grid-cols-4 divide-x divide-border h-full min-h-[140px]">

      {/* ── Cell 1: Δt_lead ─────────────────────────────────────────────── */}
      <Cell label="Time to next full-TDP" accent="none">
        {tick ? (
          <div>
            <div className={`font-mono text-3xl font-semibold tabular-nums leading-none
              ${tick.dt_lead_next_s > 0 ? 'text-text' : 'text-muted'}`}
            >
              {formatCountdown(tick.dt_lead_next_s)}
            </div>
            <div className="mt-1 font-mono text-[10px] text-muted">
              {tick.dt_lead_next_s > 0
                ? (isInterp ? '~interpolated' : 'until next GPU at full TDP')
                : 'no active ramp'}
            </div>
          </div>
        ) : (
          <div className="font-mono text-sm text-muted">—</div>
        )}
      </Cell>

      {/* ── Cell 2: BESS bridging ────────────────────────────────────────── */}
      {(() => {
        const alertRed = latchedAlert !== null && tick?.bess_bridging_seconds === 0
        return (
          <Cell label="BESS bridging" accent={alertRed ? 'red' : 'none'}>
            {tick ? (
              <div>
                <div className={`font-mono text-3xl font-semibold tabular-nums leading-none
                  ${alertRed ? 'text-danger' : tick.bess_bridging_seconds >= 86400 ? 'text-success' : 'text-text'}`}
                >
                  {formatBridge(tick.bess_bridging_seconds)}
                </div>
                <div className="mt-1 font-mono text-[10px] text-muted">
                  {tick.bridging_basis !== 'no_load' && BASIS_LABEL[tick.bridging_basis]
                    ? `basis: ${BASIS_LABEL[tick.bridging_basis]}`
                    : ''}
                </div>
              </div>
            ) : (
              <div className="font-mono text-sm text-muted">—</div>
            )}
          </Cell>
        )
      })()}

      {/* ── Cell 3: Thermal headroom ─────────────────────────────────────── */}
      {(() => {
        const absorbable = tick?.absorbable_mw ?? 0
        const rated      = tick?.rated_cooling_mw ?? 0
        const fraction   = rated > 0 ? absorbable / rated : 1.0
        const lowHeadroom = tick !== null && rated > 0 && fraction < 0.05
        return (
          <Cell label="Thermal headroom" accent={lowHeadroom ? 'amber' : 'none'}>
            {tick ? (
              <div>
                <div className="flex items-baseline gap-2">
                  <span className={`font-mono text-3xl font-semibold tabular-nums leading-none
                    ${lowHeadroom ? 'text-warn' : 'text-text'}`}
                  >
                    {absorbable.toFixed(2)}
                  </span>
                  <span className="font-mono text-sm text-muted">MW</span>
                </div>
                <div className="mt-1 font-mono text-[10px] text-muted">
                  limit in {formatTimeToLimit(tick.time_to_limit_s)}
                  {lowHeadroom && (
                    <span className="ml-1 text-warn">· low headroom</span>
                  )}
                </div>
              </div>
            ) : (
              <div className="font-mono text-sm text-muted">—</div>
            )}
          </Cell>
        )
      })()}

      {/* ── Cell 4: Alert dock ───────────────────────────────────────────── */}
      <div className="overflow-auto">
        <AlertDock />
      </div>

    </section>
  )
}
