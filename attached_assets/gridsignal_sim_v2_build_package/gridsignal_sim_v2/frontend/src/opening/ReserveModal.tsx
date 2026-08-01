/**
 * ReserveModal.tsx — Plain-English explanation of the Reserve indicator.
 *
 * "Reserve" answers one question: if the turbines needed a moment to ramp
 * up, can the battery bank cover the shortfall in the meantime?
 *
 * Two states:
 *   SUFFICIENT   — battery power ceiling ≥ predicted demand gap
 *   INSUFFICIENT — battery cannot cover the shortfall at this demand level
 *
 * Key data shown (from TickPayload):
 *   bess_bridging_seconds   — primary: how long the battery can hold
 *   bess_soc_fraction       — secondary: how much charge is left
 *   bess_output_mw          — what the battery is currently delivering
 *   net_demand_mw           — the gap turbines aren't covering yet
 *   bridging_basis          — whether the figure is based on predicted peak or live demand
 *   insufficient_reserve_alert — whether the alert is latched
 *
 * Accessibility follows the same pattern as GenTripModal / SubsystemModal:
 *   · role="dialog" + aria-modal
 *   · Esc closes
 *   · focus trapped inside
 *   · focus restored on close
 */

import { useCallback, useEffect, useRef } from 'react'
import type { TickPayload } from '../types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BRIDGING_FULL = 86400

function fmtBridge(s: number, basis: string): string {
  if (basis === 'no_load' || s >= BRIDGING_FULL) return 'full reserve — no load to bridge'
  if (s === 0) return '0 s — cannot bridge'
  if (s >= 3600) return `${(s / 3600).toFixed(1)} h`
  if (s >= 60)   return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`
  return `${Math.round(s)} s`
}

function fmtMw(mw: number): string {
  return `${mw.toFixed(2)} MW`
}

function socColour(soc: number): string {
  if (soc < 0.20) return '#e05252'
  if (soc < 0.40) return '#f0883e'
  return '#3fb6a8'
}

function basisLabel(basis: string): string {
  if (basis === 'no_load')       return 'No load active — battery at full standby'
  if (basis === 'predicted_peak') return 'Sized against the predicted demand peak (conservative)'
  return 'Sized against current live demand'
}

// ---------------------------------------------------------------------------
// State-specific content
// ---------------------------------------------------------------------------

interface Content {
  headline: string
  summary: string[]
  whatItMeans: string[]
}

function deriveContent(tick: TickPayload | null): Content {
  if (!tick) {
    return {
      headline: 'Waiting for live data',
      summary: ['Start a run to see the live reserve status.'],
      whatItMeans: ['Once running, this panel shows whether the battery can cover the gap between turbine output and load demand.'],
    }
  }

  const bridgeSecs = tick.bess_bridging_seconds
  const basis      = tick.bridging_basis
  const netDemand  = tick.net_demand_mw
  const soc        = tick.bess_soc_fraction
  const alert      = tick.insufficient_reserve_alert

  // No load case — fully at rest
  if (basis === 'no_load' || bridgeSecs >= BRIDGING_FULL) {
    return {
      headline: 'Full reserve — no demand to bridge.',
      summary: [
        'The turbines are currently covering all demand on their own, so the battery is sitting at full standby.',
        `The battery is ${Math.round(soc * 100)}% charged and ready to step in the moment a shortfall appears.`,
        'Reserve will show a bridge duration as soon as the step-load ramp begins.',
      ],
      whatItMeans: [
        'Nothing to act on. The battery is armed and healthy.',
        'When the load ramp starts, the reserve figure will change to show how many seconds (or minutes) the battery can sustain the plant alone.',
        'The battery does not discharge when the reserve status is "full" — it is held back for the moment it is needed.',
      ],
    }
  }

  if (alert || bridgeSecs === 0) {
    return {
      headline: 'The battery cannot bridge the full demand gap at this moment.',
      summary: [
        `The predicted demand gap is ${fmtMw(netDemand)}, but the battery's available power ceiling has been exceeded.`,
        'This typically happens when demand is rising faster than the turbines can ramp — the shortfall is momentarily larger than what the battery is rated to deliver.',
        `The battery is ${Math.round(soc * 100)}% charged. Charge level is not the issue — power delivery rate is.`,
        'The system has latched an alert. Acknowledge it once turbine output has recovered, or add staging headroom by reducing new dispatch requests.',
      ],
      whatItMeans: [
        'No immediate crisis — the turbines are still producing and the load is still served. The alert means the safety margin has gone to zero.',
        'If load keeps rising and turbines do not catch up, frequency stability falls to the grid-forming anchor alone (1 MW withheld reserve). That is a thin margin.',
        'To clear the alert: wait for turbines to ramp up, reduce compute demand, or acknowledge manually once the situation has stabilised.',
      ],
    }
  }

  // Normal sufficient state
  const bridgeStr = fmtBridge(bridgeSecs, basis)
  return {
    headline: `The battery can cover the shortfall for ${bridgeStr}.`,
    summary: [
      `Right now, turbines are not yet covering the full load. The gap is ${fmtMw(netDemand)}.`,
      `The battery steps in instantly and can sustain that gap for ${bridgeStr} before it needs the turbines to close the remaining distance.`,
      basis === 'predicted_peak'
        ? 'This figure is calculated against the forecast demand peak — the worst case for the ramp, not just the current moment.'
        : 'This figure is calculated against the current live demand.',
      `Battery charge is at ${Math.round(soc * 100)}%. The usable window is 10–95% of capacity (§3.3).`,
    ],
    whatItMeans: [
      'The turbines are ramping and the battery is bridging. Everything is working as designed.',
      `As long as turbines close the gap within ${bridgeStr}, the battery never hits its floor and reserve status stays green.`,
      'Watch the bridge duration as the ramp progresses — if turbines are slow, the figure will count down. That is the early-warning signal.',
    ],
  }
}

// ---------------------------------------------------------------------------
// Metric row component
// ---------------------------------------------------------------------------

function MetricRow({
  label,
  value,
  note,
  colour,
}: {
  label: string
  value: string
  note?: string
  colour?: string
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 border-b border-border/50 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted">{label}</div>
        {note && <div className="font-mono text-[10px] text-muted/70 mt-0.5 leading-snug">{note}</div>}
      </div>
      <div
        className="font-mono text-sm font-semibold tabular-nums text-right shrink-0"
        style={colour ? { color: colour } : { color: '#e6edf3' }}
      >
        {value}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SoC bar (inline, simplified)
// ---------------------------------------------------------------------------

function SocBar({ fraction }: { fraction: number }) {
  const pct = Math.max(0, Math.min(1, fraction)) * 100
  const col = socColour(fraction)
  return (
    <div className="space-y-1">
      <div className="flex justify-between font-mono text-[9px] text-muted">
        <span>10% (min usable)</span>
        <span>Battery charge</span>
        <span>95% (max usable)</span>
      </div>
      <div className="relative h-3 rounded overflow-hidden bg-surface border border-border">
        {/* Usable window shade */}
        <div className="absolute top-0 h-full bg-border/30" style={{ left: '10%', width: '85%' }} />
        {/* Fill */}
        <div
          className="absolute top-0 left-0 h-full transition-all duration-300"
          style={{ width: `${pct}%`, background: col }}
        />
      </div>
      <div className="text-right font-mono text-xs" style={{ color: col }}>
        {fraction.toFixed(1) === '0.0' ? `${(fraction * 100).toFixed(1)}%` : `${Math.round(fraction * 100)}%`}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

export function ReserveModal({
  tick,
  onClose,
}: {
  tick: TickPayload | null | undefined
  onClose: () => void
}) {
  const alert       = tick?.insufficient_reserve_alert ?? false
  const bridgeSecs  = tick?.bess_bridging_seconds ?? BRIDGING_FULL
  const basis       = tick?.bridging_basis ?? 'no_load'

  const insufficient = alert || bridgeSecs === 0
  const noLoad       = !tick || basis === 'no_load' || bridgeSecs >= BRIDGING_FULL

  const accentColour = insufficient ? '#e05252' : '#3fb6a8'
  const stateWord    = insufficient ? 'INSUFFICIENT' : 'SUFFICIENT'

  const content = deriveContent(tick ?? null)

  const dialogRef      = useRef<HTMLDivElement>(null)
  const closeBtnRef    = useRef<HTMLButtonElement>(null)
  const returnFocusRef = useRef<Element | null>(null)

  useEffect(() => {
    returnFocusRef.current = document.activeElement
    closeBtnRef.current?.focus()
  }, [])

  useEffect(() => {
    return () => {
      const el = returnFocusRef.current
      if (el && 'focus' in el) (el as HTMLElement).focus()
    }
  }, [])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
    if (e.key === 'Tab' && dialogRef.current) {
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      if (!focusable.length) { e.preventDefault(); return }
      const first = focusable[0]
      const last  = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus()
      }
    }
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Reserve — plain English explanation"
        className="relative flex flex-col w-full max-w-[92vw] xl:max-w-[620px] max-h-[90vh]
                   rounded-xl overflow-hidden border border-border bg-surface shadow-2xl"
        onKeyDown={handleKeyDown}
      >
        {/* Accent top bar */}
        <div className="absolute inset-x-0 top-0 h-[4px]" style={{ background: accentColour }} />

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between px-7 pt-7 pb-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h2 className="font-mono text-base font-bold tracking-wide text-text uppercase">
                Reserve
              </h2>
              <div className="w-2 h-2 rounded-full shrink-0" style={{ background: accentColour }} />
              <span className="font-mono text-[10px] font-bold tracking-wider uppercase"
                    style={{ color: accentColour }}>
                {stateWord}
              </span>
            </div>
            <div className="font-mono text-[10px] text-muted">
              Battery bridging capacity · updates every simulation tick
            </div>
          </div>
          <button
            ref={closeBtnRef}
            onClick={onClose}
            className="ml-4 shrink-0 text-muted hover:text-text text-lg leading-none px-1"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="h-px bg-border mx-7" />

        {/* ── Scrollable body ─────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-7 py-5 space-y-5">

          {/* What is reserve? */}
          <div className="rounded-lg border px-4 py-4 space-y-2"
               style={{ borderColor: accentColour, background: '#16222e' }}>
            <div className="font-mono text-[9px] uppercase tracking-[0.14em]"
                 style={{ color: '#4b5764' }}>
              WHAT IS RESERVE?
            </div>
            <p className="font-mono text-xs text-muted leading-relaxed">
              Turbines take time to ramp — they cannot go from zero to full power instantly.
              During that window, the battery bank steps in as a <span className="text-text">bridge</span>: it
              delivers power immediately while the turbines catch up.
              "Reserve sufficient" means the battery has enough <em>power capacity</em> to cover
              that gap. It is not just about how much charge is stored — it is about how fast the
              battery can deliver it.
            </p>
          </div>

          {/* State explanation */}
          <div className="space-y-2">
            <div className="font-mono text-[9px] uppercase tracking-[0.14em]"
                 style={{ color: '#4b5764' }}>
              RIGHT NOW — {stateWord}
            </div>
            <p className="font-mono text-sm font-semibold leading-snug"
               style={{ color: accentColour }}>
              {content.headline}
            </p>
            <div className="space-y-1 pt-1">
              {content.summary.map((line, i) => (
                <p key={i} className="font-mono text-xs text-muted leading-relaxed">{line}</p>
              ))}
            </div>
          </div>

          <div className="h-px bg-border" />

          {/* Key figures */}
          {tick && (
            <div className="space-y-1">
              <div className="font-mono text-[9px] uppercase tracking-[0.14em] mb-2"
                   style={{ color: '#4b5764' }}>
                KEY FIGURES
              </div>
              <MetricRow
                label="Bridge duration"
                note="How long the battery alone can cover the demand gap"
                value={fmtBridge(tick.bess_bridging_seconds, tick.bridging_basis)}
                colour={insufficient ? '#e05252' : noLoad ? undefined : '#3fb6a8'}
              />
              <MetricRow
                label="Calculation basis"
                note={basisLabel(tick.bridging_basis)}
                value={tick.bridging_basis === 'no_load' ? 'no load' : tick.bridging_basis.replace('_', ' ')}
              />
              <MetricRow
                label="Demand gap (net)"
                note="Power not yet covered by turbines — what the battery is bridging"
                value={fmtMw(tick.net_demand_mw)}
              />
              <MetricRow
                label="Battery output"
                note="What the battery is delivering right now"
                value={fmtMw(tick.bess_output_mw)}
                colour={tick.bess_output_mw > 0 ? '#4a9fe0' : undefined}
              />
              <MetricRow
                label="Anchor reserve (withheld)"
                note="1 MW permanently held back to regulate grid frequency — never available for bridging (§7.1.2)"
                value="1.0 MW"
                colour="#f0883e"
              />
              {/* SoC bar inline */}
              <div className="pt-1 pb-2">
                <div className="font-mono text-[10px] uppercase tracking-wider text-muted mb-2">
                  Battery charge level
                </div>
                <SocBar fraction={tick.bess_soc_fraction} />
              </div>
            </div>
          )}

          <div className="h-px bg-border" />

          {/* What it means for you */}
          <div>
            <div className="font-mono text-[9px] uppercase tracking-[0.14em] mb-3"
                 style={{ color: '#4b5764' }}>
              WHAT THIS MEANS FOR YOU
            </div>
            <div className="space-y-2">
              {content.whatItMeans.map((line, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <div className="mt-1 w-1 h-1 rounded-full shrink-0"
                       style={{ background: accentColour }} />
                  <p className="font-mono text-xs text-muted leading-relaxed">{line}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Two-state legend */}
          <div className="rounded-lg border border-border/50 px-4 py-4 space-y-2.5">
            <div className="font-mono text-[9px] uppercase tracking-[0.14em]"
                 style={{ color: '#4b5764' }}>
              TWO POSSIBLE STATES
            </div>
            {[
              {
                colour: '#3fb6a8',
                label: 'SUFFICIENT',
                desc: 'Battery power ceiling ≥ demand gap. The bridge holds for the stated duration.',
              },
              {
                colour: '#e05252',
                label: 'INSUFFICIENT',
                desc: 'Demand gap exceeds battery power ceiling. The battery cannot fully bridge the shortfall — turbines must carry more of the load.',
              },
            ].map(s => (
              <div key={s.label} className="flex items-start gap-2.5">
                <div className="mt-0.5 w-1.5 h-1.5 rounded-full shrink-0"
                     style={{ background: s.colour }} />
                <div>
                  <span className="font-mono text-[10px] font-bold uppercase"
                        style={{ color: s.colour }}>
                    {s.label}
                  </span>
                  <span className="font-mono text-[10px] text-muted ml-2">{s.desc}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Footer ─────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-end gap-3 px-7 py-4 border-t border-border">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded text-xs font-semibold font-mono transition-colors"
            style={{ background: accentColour, color: '#0d1117' }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
