/**
 * HeroPanel.tsx — Δt_lead countdown + predicted step (§19.2 / Design Spec §8.4).
 *
 * Primary display:  dt_lead_next_s counting down to the next GPU reaching
 *                   full TDP.  0 = no active ramp.
 * Secondary:        confidence band point estimate (midpoint of lower/upper)
 *                   ± half-band width in MW.  DQ-flagged when tags present.
 * Tertiary:         p_total_mw current reading.
 *
 * §8.4: "The number beside it is the predicted step in MW with its confidence
 * band."  The hero countdown is therefore Δt_lead, not p_total.
 *
 * C2 note: dt_lead_next_s is min() across in-flight ramp remaining times.
 * "No active ramp" (dt_lead_next_s == 0) is displayed distinctly so the
 * operator never confuses "ramp just reached full TDP" with "no jobs running".
 */

import { useTickStore } from '../store/tickStore'
import { DataQualityBadge } from './DataQualityBadge'

function formatCountdown(s: number): string {
  if (s <= 0) return '—'
  if (s >= 60) {
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${m}m ${sec}s`
  }
  return `${s.toFixed(1)}s`
}

export function HeroPanel() {
  const tick      = useTickStore(s => s.latestTick)
  const isInterp  = useTickStore(s => s.isInterpolated)

  if (!tick) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-muted">
        <div className="text-4xl">○</div>
        <div className="font-mono text-sm">no active run</div>
      </div>
    )
  }

  const dtLead    = tick.dt_lead_next_s
  const lower     = tick.confidence_lower_mw
  const upper     = tick.confidence_upper_mw
  const estimate  = (lower + upper) / 2
  const halfBand  = (upper - lower) / 2
  const tags      = tick.data_quality_tags
  const pTotal    = tick.p_total_mw
  const hasRamp   = dtLead > 0

  return (
    <section className="flex h-full flex-col justify-between p-4">
      <div className="space-y-1">
        <div className="font-mono text-xs uppercase tracking-wider text-muted">
          Time to next full-TDP event
        </div>

        {/* Hero number */}
        <div className={`font-mono text-5xl font-semibold tabular-nums leading-none
          ${hasRamp ? 'text-text' : 'text-muted'}`}
        >
          {formatCountdown(dtLead)}
        </div>

        {!hasRamp && (
          <div className="font-mono text-xs text-muted italic">no active ramp</div>
        )}
        {isInterp && hasRamp && (
          <div className="font-mono text-[10px] italic text-muted">~interpolated</div>
        )}
      </div>

      {/* Predicted step */}
      <div className="space-y-0.5">
        <div className="font-mono text-xs uppercase tracking-wider text-muted">
          Predicted next step
        </div>
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-2xl tabular-nums text-text">
            +{estimate.toFixed(2)} MW
          </span>
          <span className="font-mono text-sm text-muted">
            ±{halfBand.toFixed(2)} MW
          </span>
          {tags.length > 0 && (
            <span className="flex gap-1">
              {tags.map(t => <DataQualityBadge key={t} tag={t} />)}
            </span>
          )}
        </div>
      </div>

      {/* Current total */}
      <div className="space-y-0.5">
        <div className="font-mono text-xs uppercase tracking-wider text-muted">
          P_total now
        </div>
        <div className="font-mono text-xl tabular-nums text-text">
          {pTotal.toFixed(3)} MW
        </div>
      </div>
    </section>
  )
}
