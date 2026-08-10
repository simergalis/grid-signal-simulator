/**
 * GenTripModal.tsx — Layman's explanation of the Gen-Trip Cover indicator.
 *
 * "Gen-trip" is jargon for a generator suddenly going offline.  This modal
 * translates the three-state readout (COVERED / COVERED_WITH_SHED /
 * CANNOT_CARRY) and its supporting figures into plain English so an operator
 * or non-technical stakeholder can understand what they are looking at.
 *
 * Follows the same accessibility pattern as SubsystemModal:
 *   · role="dialog" + aria-modal
 *   · Esc closes
 *   · focus trapped inside
 *   · focus restored to the triggering element on close
 *
 * Width: 640 px max (narrower than SubsystemModal; no chart needed here).
 */

import { useCallback, useEffect, useRef } from 'react'
import type { ContingencyCoverage } from '../types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(mw: number, dp = 1) {
  return `${mw.toFixed(dp)} MW`
}

function fmtTime(s: number): string {
  if (s >= 86400) return '—'
  if (s >= 60) return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`
  return `${Math.round(s)} s`
}

/** Colour that matches the tile in VerdictBand. */
function stateColour(cc: ContingencyCoverage | null | undefined): string {
  if (!cc) return '#4a9fe0'
  if (cc.state === 'COVERED') return '#3fb6a8'
  if (cc.state === 'COVERED_WITH_SHED') return '#f0883e'
  return '#e05252'
}

function stateWord(cc: ContingencyCoverage | null | undefined): string {
  if (!cc) return 'No data'
  if (cc.state === 'COVERED') return 'COVERED'
  if (cc.state === 'COVERED_WITH_SHED') return 'COVERED WITH LOAD SHED'
  return 'CANNOT CARRY'
}

// ---------------------------------------------------------------------------
// Plain-English content per state
// ---------------------------------------------------------------------------

interface StateContent {
  headline: string
  summary: string[]
  whatItMeans: string[]
}

function deriveContent(cc: ContingencyCoverage | null | undefined): StateContent {
  if (!cc) {
    return {
      headline: 'Waiting for live data',
      summary: [
        'The gen-trip assessment runs once per simulation tick.',
        'Start a run to see a live readout.',
      ],
      whatItMeans: [
        'Once the simulation is running, this panel will show how well the plant can absorb a sudden generator trip.',
      ],
    }
  }

  const deficitMw  = fmt(cc.deficit_mw)
  const headroomMw = fmt(cc.headroom_surviving_mw)
  const bessMw     = fmt(cc.bess_bridging_available_mw)
  const shedMw     = fmt(cc.shed_required_mw)
  const rtTime     = fmtTime(cc.ride_through_s)
  const closeTime  = cc.closable && cc.time_to_close_s < 86400
    ? fmtTime(cc.time_to_close_s)
    : null

  if (cc.state === 'COVERED') {
    return {
      headline: 'Your plant can handle the worst case right now.',
      summary: [
        `If the largest running generator suddenly tripped offline, it would instantly remove ${deficitMw} of supply.`,
        `The remaining generators already have ${headroomMw} of spare capacity above their current output — enough to absorb the full loss.`,
        `The battery bank can deliver ${bessMw} of bridging power immediately${closeTime ? `, buying the ${closeTime} needed for the generators to ramp up and close the gap on their own` : ''}.`,
        'No compute load would need to be interrupted.',
      ],
      whatItMeans: [
        'The plant is operating with full N−1 redundancy at this moment. Losing any one generator would be a bump, not a crisis.',
        'The battery kicks in instantly (within milliseconds), the generators ramp to fill the gap, and the battery returns to standby. The GPU fleet never notices.',
        'This status can change as load rises. Watch the tile as the ramp progresses.',
      ],
    }
  }

  if (cc.state === 'COVERED_WITH_SHED') {
    return {
      headline: `Your plant can cope, but it would need to pause ${shedMw} of compute load${cc.shed_equivalent_nodes != null ? ` — roughly ${cc.shed_equivalent_nodes} nodes` : ''}.`,
      summary: [
        `If the largest running generator tripped right now, it would remove ${deficitMw} of supply.`,
        `The remaining generators have only ${headroomMw} of spare headroom — not enough to cover the full gap by ramping alone.`,
        `The battery (${bessMw} available) would bridge the shortfall for up to ${rtTime} while the control system reduces compute load by ${shedMw}${cc.shed_equivalent_nodes != null ? ` (≈ ${cc.shed_equivalent_nodes} nodes)` : ''} to bring demand in line with available supply.`,
        'This is an automatic safety action — not a failure. The affected jobs pause and resume once generation recovers.',
      ],
      whatItMeans: [
        `A ${shedMw} reduction in compute${cc.shed_equivalent_nodes != null ? ` (≈ ${cc.shed_equivalent_nodes} nodes)` : ''} is equivalent to the lowest-priority workloads stepping back temporarily. No data is lost — training jobs checkpoint automatically.`,
        'The battery buys enough time for the curtailment system to act gracefully rather than having frequency collapse.',
        'This state is common when all turbines are near full load. It resolves if load drops, a turbine gains headroom, or the battery SoC is higher.',
      ],
    }
  }

  // CANNOT_CARRY
  return {
    headline: 'A single generator trip could not be absorbed without a full overload.',
    summary: [
      `If the largest running generator tripped right now, it would remove ${deficitMw} of supply.`,
      `Surviving generators have only ${headroomMw} of spare headroom, and the curtailment budget cannot close the remaining gap.`,
      `The battery can sustain the plant for about ${rtTime} before the situation becomes critical.`,
      'This is a warning — no generator has actually tripped. But safety margins are very thin.',
    ],
    whatItMeans: [
      'Operate with caution. Avoid adding new load until headroom improves — reduce compute demand or wait for a generator to gain headroom.',
      'The battery is your last line of defence. Check the Battery modal to confirm SoC is healthy.',
      'If a trip were to happen now, the automatic protection systems would still limit the damage — but recovery would not be clean.',
    ],
  }
}

// ---------------------------------------------------------------------------
// Metric rows
// ---------------------------------------------------------------------------

interface MetricRowProps {
  label: string
  value: string
  note?: string
  highlight?: string
}

function MetricRow({ label, value, note, highlight }: MetricRowProps) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 border-b border-border/50 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted">{label}</div>
        {note && <div className="font-mono text-[10px] text-muted/70 mt-0.5 leading-snug">{note}</div>}
      </div>
      <div
        className="font-mono text-sm font-semibold tabular-nums text-right shrink-0"
        style={highlight ? { color: highlight } : { color: '#e6edf3' }}
      >
        {value}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

export function GenTripModal({
  cc,
  onClose,
}: {
  cc: ContingencyCoverage | null | undefined
  onClose: () => void
}) {
  const colour    = stateColour(cc)
  const content   = deriveContent(cc)

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
        aria-label="Gen-Trip Cover — plain English explanation"
        className="relative flex flex-col w-full max-w-[92vw] xl:max-w-[640px] max-h-[90vh]
                   rounded-xl overflow-hidden border border-border bg-surface shadow-2xl"
        onKeyDown={handleKeyDown}
      >
        {/* Accent top bar — colour matches the tile */}
        <div className="absolute inset-x-0 top-0 h-[4px]" style={{ background: colour }} />

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between px-7 pt-7 pb-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h2 className="font-mono text-base font-bold tracking-wide text-text uppercase">
                Gen-Trip Cover
              </h2>
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: colour }} />
              <span
                className="font-mono text-[10px] font-bold tracking-wider uppercase"
                style={{ color: colour }}
              >
                {stateWord(cc)}
              </span>
            </div>
            <div className="font-mono text-[10px] text-muted">
              N−1 generator contingency assessment · updates every simulation tick
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

          {/* What is gen-trip cover? */}
          <div
            className="rounded-lg border px-4 py-4 space-y-2"
            style={{ borderColor: colour, background: '#16222e' }}
          >
            <div className="font-mono text-[9px] uppercase tracking-[0.14em]" style={{ color: '#4b5764' }}>
              WHAT IS GEN-TRIP COVER?
            </div>
            <p className="font-mono text-xs text-muted leading-relaxed">
              A "gen-trip" is when a generator suddenly goes offline — a fault, an emergency stop, or
              a breaker trip. The question this tile answers is: <span className="text-text">if that happened right now,
              could the rest of the plant hold the load?</span> The assessment runs every tick using live
              output figures, not nameplate ratings.
            </p>
          </div>

          {/* State explanation */}
          <div className="space-y-2">
            <div className="font-mono text-[9px] uppercase tracking-[0.14em]" style={{ color: '#4b5764' }}>
              RIGHT NOW — {stateWord(cc)}
            </div>
            <p
              className="font-mono text-sm font-semibold leading-snug"
              style={{ color: colour }}
            >
              {content.headline}
            </p>
            <div className="space-y-1 pt-1">
              {content.summary.map((line, i) => (
                <p key={i} className="font-mono text-xs text-muted leading-relaxed">
                  {line}
                </p>
              ))}
            </div>
          </div>

          <div className="h-px bg-border" />

          {/* Key figures */}
          {cc && (
            <div className="space-y-1">
              <div className="font-mono text-[9px] uppercase tracking-[0.14em] mb-2"
                   style={{ color: '#4b5764' }}>
                KEY FIGURES
              </div>
              <MetricRow
                label="Worst-case gap"
                note="Power the tripped generator is currently producing — the hole to fill"
                value={fmt(cc.deficit_mw)}
              />
              <MetricRow
                label="Surviving headroom"
                note="Extra room the remaining generators have above their current output"
                value={fmt(cc.headroom_surviving_mw)}
                highlight={cc.headroom_surviving_mw >= cc.deficit_mw ? '#3fb6a8' : '#f0883e'}
              />
              <MetricRow
                label="Battery bridge available"
                note="Power the battery can deliver immediately to cover the gap"
                value={fmt(cc.bess_bridging_available_mw)}
                highlight={cc.power_test_passes ? '#3fb6a8' : '#e05252'}
              />
              <MetricRow
                label="Battery ride-through"
                note="How long the battery can sustain the plant without generation closing the gap"
                value={cc.ride_through_s >= 86400 ? 'Full reserve' : fmtTime(cc.ride_through_s)}
              />
              {cc.closable && cc.time_to_close_s < 86400 && (
                <MetricRow
                  label="Generators close gap in"
                  note="Time for surviving generators to ramp up and fill the deficit on their own"
                  value={fmtTime(cc.time_to_close_s)}
                  highlight="#3fb6a8"
                />
              )}
              {cc.shed_required_mw > 0 && (
                <MetricRow
                  label="Load reduction needed"
                  note={`Compute power that would pause automatically to bring demand in line${cc.shed_equivalent_nodes != null ? ` — roughly ${cc.shed_equivalent_nodes} nodes at current power density` : ''}`}
                  value={`${fmt(cc.shed_required_mw)}${cc.shed_equivalent_nodes != null ? `  ≈ ${cc.shed_equivalent_nodes} nodes` : ''}`}
                  highlight="#f0883e"
                />
              )}
              <MetricRow
                label="Dispatchable capacity"
                note="Total firm capacity — online turbine ratings plus battery (excludes solar)"
                value={fmt(cc.dispatchable_mw)}
              />
              {cc.renewable_mw > 0 && (
                <MetricRow
                  label="Solar output (non-firm)"
                  note="Current solar generation — reduces load served by turbines, but cannot be relied on for N−1 cover"
                  value={fmt(cc.renewable_mw)}
                />
              )}
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
                  <div className="mt-1 w-1 h-1 rounded-full shrink-0" style={{ background: colour }} />
                  <p className="font-mono text-xs text-muted leading-relaxed">{line}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Three states legend */}
          <div className="rounded-lg border border-border/50 px-4 py-4 space-y-2.5">
            <div className="font-mono text-[9px] uppercase tracking-[0.14em]" style={{ color: '#4b5764' }}>
              THREE POSSIBLE STATES
            </div>
            {[
              {
                colour: '#3fb6a8',
                label: 'COVERED',
                desc: 'Generators + battery can absorb a trip with no load interruption.',
              },
              {
                colour: '#f0883e',
                label: 'COVERED WITH LOAD SHED',
                desc: 'Battery buys time; curtailment automatically pauses low-priority compute to stay in balance.',
              },
              {
                colour: '#e05252',
                label: 'CANNOT CARRY',
                desc: 'Even full curtailment cannot close the gap. Safety margins are very thin — reduce load.',
              },
            ].map(s => (
              <div key={s.label} className="flex items-start gap-2.5">
                <div className="mt-0.5 w-1.5 h-1.5 rounded-full shrink-0" style={{ background: s.colour }} />
                <div>
                  <span className="font-mono text-[10px] font-bold uppercase" style={{ color: s.colour }}>
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
            style={{ background: colour, color: '#0d1117' }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
