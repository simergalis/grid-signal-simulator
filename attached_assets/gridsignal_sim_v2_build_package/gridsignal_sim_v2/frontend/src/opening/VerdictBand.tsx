/**
 * VerdictBand.tsx — Band 1 of the opening screen (V-2).
 *
 * Left: one computed claim about plant readiness — not equipment status.
 * Right: four hero figures, sourced from the live tick or static defaults.
 *
 * GT-1 / GT-2: Gen-trip cover tile now shows quantitative figures per §7.4.
 * GT-2: Dispatchable tile now excludes solar (§7.5); Renewable is a separate
 *        non-firm term displayed in place of Δt_lead (which is 0 in the at-rest
 *        state anyway).
 * GT-2 TC-84: state transitions are logged to console with timestamp and
 *        triggering plant-state figures.
 *
 * Static defaults (no tick):
 *   DISPATCHABLE  45.0 MW  — 4×7 MW online turbines + BESS 17 MW (18−1 anchor)
 *   RENEWABLE      ~5.0 MW — solar (non-firm)
 *   GEN-TRIP COVER  covered · awaiting run
 *   ATTENTION      —
 *
 * Running state (dt_lead_next_s > 0):
 *   Site Draw / Predicted Peak / Gen-trip cover (quantitative) / Reserve status
 *
 * At-rest (tick present, no active ramp):
 *   Dispatchable / Renewable / Gen-trip cover (quantitative) / Attention
 */

import { useEffect, useRef } from 'react'
import { useTickStore } from '../store/tickStore'
import type { ContingencyCoverage } from '../types'

interface FigureProps {
  label: string
  value: string
  colour?: string
  sub?: string
  /** Fixed px width — prevents layout shift when value flips between short and long strings. */
  colWidth: number
}

function HeroFigure({ label, value, colour, sub, colWidth }: FigureProps) {
  return (
    <div className="flex flex-col gap-0.5 flex-shrink-0" style={{ width: colWidth }}>
      <div className="font-mono text-[9px] uppercase tracking-wider text-muted">{label}</div>
      <div
        className="font-mono text-lg font-semibold tabular-nums leading-none whitespace-nowrap overflow-hidden"
        style={colour ? { color: colour } : { color: '#e6edf3' }}
      >
        {value}
      </div>
      {sub && <div className="font-mono text-[9px] text-muted mt-0.5 leading-tight">{sub}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Gen-trip cover: quantitative readout per §7.4
// ---------------------------------------------------------------------------

/**
 * Return a quantitative one-line value for the gen-trip cover tile.
 *
 * COVERED:           "covered · 6.9 MW · closes in 35 s"
 * COVERED_WITH_SHED: "3.1 MW shed · 41 s ride-through"
 * CANNOT_CARRY:      "22.6 MW uncov · 9 s ride-through"
 */
function genTripValue(cc: ContingencyCoverage | null | undefined): string {
  if (!cc) return 'awaiting data'
  const rt = cc.ride_through_s >= 86400 ? '∞' : `${Math.round(cc.ride_through_s)} s`
  if (cc.state === 'COVERED') {
    const close =
      cc.time_to_close_s >= 86400
        ? '∞'
        : `closes in ${Math.round(cc.time_to_close_s)} s`
    return `covered · ${cc.deficit_mw.toFixed(1)} MW · ${close}`
  }
  if (cc.state === 'COVERED_WITH_SHED') {
    return `${cc.shed_required_mw.toFixed(1)} MW shed · ${rt} ride-through`
  }
  // CANNOT_CARRY
  return `${cc.deficit_mw.toFixed(1)} MW uncov · ${rt} ride-through`
}

function genTripColour(cc: ContingencyCoverage | null | undefined): string {
  if (!cc) return '#4a9fe0'
  if (cc.state === 'COVERED') return '#3fb6a8'           // teal
  if (cc.state === 'COVERED_WITH_SHED') return '#f0883e' // amber
  return '#e05252'                                        // red
}

function genTripSub(cc: ContingencyCoverage | null | undefined): string | undefined {
  if (!cc) return undefined
  if (cc.state === 'COVERED') return 'N−1 gen-trip covered'
  if (cc.state === 'COVERED_WITH_SHED') return `shed ${cc.shed_required_mw.toFixed(1)} MW to cover`
  return 'insufficient generation + shed'
}

export function VerdictBand() {
  const tick  = useTickStore(s => s.latestTick)
  const alert = useTickStore(s => s.latchedAlert)

  const running  = tick !== null && tick.dt_lead_next_s > 0
  const hasAlert = alert !== null
  const hasRun   = tick !== null

  // ── TC-84: log state transitions ─────────────────────────────────────────
  const prevContingencyState = useRef<string | null>(null)
  useEffect(() => {
    const cc = tick?.contingency_coverage
    if (!cc) return
    const newState = cc.state
    if (prevContingencyState.current !== null && prevContingencyState.current !== newState) {
      console.log(
        `[VerdictBand] gen-trip cover transition: ${prevContingencyState.current} → ${newState}`,
        `| deficit=${cc.deficit_mw.toFixed(2)} MW`,
        `| headroom=${cc.headroom_surviving_mw.toFixed(2)} MW`,
        `| shed=${cc.shed_required_mw.toFixed(2)} MW`,
        `| t=${tick?.sim_time_seconds?.toFixed(0)} s`,
      )
    }
    prevContingencyState.current = newState
  }, [tick?.contingency_coverage?.state, tick?.sim_time_seconds])

  // ── Claim ────────────────────────────────────────────────────────────────

  const claimLabel = running ? 'RUN IN PROGRESS' : 'SYSTEM READINESS'

  let claimWord: string
  let claimSuffix: string
  let claimColour: string
  let subtitle: string

  if (hasAlert) {
    claimWord   = 'ATTENTION'
    claimSuffix = '— insufficient reserve, acknowledge before further dispatch'
    claimColour = '#f0883e'
    subtitle    = 'Reserve alert latched — check Battery (BESS) modal'
  } else if (running) {
    const secs = Math.max(0, Math.round(tick!.dt_lead_next_s))
    claimWord   = `${secs} s`
    claimSuffix = 'to full load — response already staged'
    claimColour = '#3fb6a8'
    subtitle    = 'turbine ramping · battery bridging the gap · nothing waited for a sensor'
  } else if (hasRun) {
    claimWord   = 'READY'
    claimSuffix = '— all systems armed and dispatchable'
    claimColour = '#3fb6a8'
    subtitle    = `confidence band nominal · ${
      tick!.data_quality_tags.length > 0
        ? `${tick!.data_quality_tags.length} DQ flag${tick!.data_quality_tags.length > 1 ? 's' : ''} active`
        : 'all calibration checks clear'
    }`
  } else {
    claimWord   = 'READY'
    claimSuffix = 'to stage a step-load'
    claimColour = '#3fb6a8'
    subtitle    = '8 of 9 subsystems nominal · forecast bands widened pending calibration'
  }

  // ── Hero figures ─────────────────────────────────────────────────────────

  let figures: FigureProps[]

  // Column widths (px) — fixed so no column ever shifts its neighbours when
  // the value string changes length.
  // Col 1: 140  Col 2: 104  Col 3: 204  Col 4: 140
  if (running && tick) {
    const cc = tick.contingency_coverage
    figures = [
      {
        label: 'Site Draw',
        value: `${tick.p_total_mw.toFixed(2)} MW`,
        colWidth: 140,
      },
      {
        label: 'Predicted Peak',
        value: `${tick.confidence_upper_mw.toFixed(2)} MW`,
        colour: '#e0a458',
        colWidth: 104,
      },
      {
        // GT-2: quantitative gen-trip readout per §7.4.
        // Three states, each with figures.  Colour follows state.
        label: 'Gen-trip cover',
        value: genTripValue(cc),
        colour: genTripColour(cc),
        sub: genTripSub(cc),
        colWidth: 204,
      },
      {
        label: 'Reserve',
        value: hasAlert ? 'insufficient' : 'sufficient',
        colour: hasAlert ? '#f0883e' : '#3fb6a8',
        colWidth: 140,
      },
    ]
  } else if (hasRun && tick) {
    const cc = tick.contingency_coverage
    const dqCount = tick.data_quality_tags.length + (hasAlert ? 1 : 0)
    // GT-2: §7.5 dispatchable excludes solar; renewable displayed separately.
    // Dispatchable = online turbine rated + anchor-adj BESS (from contingency_coverage).
    // Renewable replaces the Δt_lead tile (which is always 0 here anyway).
    const dispMw = cc?.dispatchable_mw ?? (tick.turbine_output_mw + tick.bess_output_mw)
    const renMw  = cc?.renewable_mw    ?? tick.p_renewable_mw
    figures = [
      {
        label: 'Dispatchable',
        value: `${dispMw.toFixed(1)} MW`,
        colour: '#e0a458',
        sub: 'turbine + BESS (anchor-adj)',
        colWidth: 140,
      },
      {
        // GT-2: separate Renewable term per §7.5 — non-firm, never credited toward coverage.
        label: 'Renewable',
        value: `${renMw.toFixed(1)} MW`,
        colour: '#3fb6a8',
        sub: 'non-firm · solar',
        colWidth: 104,
      },
      {
        // GT-2: same quantitative gen-trip readout as running branch.
        label: 'Gen-trip cover',
        value: genTripValue(cc),
        colour: genTripColour(cc),
        sub: genTripSub(cc),
        colWidth: 204,
      },
      {
        label: 'Attention',
        value: dqCount > 0 ? `${dqCount} subsystem` : '—',
        colour: dqCount > 0 ? '#f0883e' : undefined,
        colWidth: 140,
      },
    ]
  } else {
    // Static defaults — show configured site capacity before any run.
    // GT-3 fleet: 4×7 MW online + BESS 17 MW (18−1 anchor) = 45 MW dispatchable
    // Renewable: ~5 MW PROTO-7 solar (non-firm, displayed separately)
    figures = [
      { label: 'Dispatchable',   value: '45.0 MW',  colour: '#e0a458', sub: 'turbine + BESS (anchor-adj)', colWidth: 140 },
      { label: 'Renewable',      value: '~5.0 MW',  colour: '#3fb6a8', sub: 'non-firm · solar',             colWidth: 104 },
      { label: 'Gen-trip cover', value: 'N−1 ready', colour: '#4a9fe0',                                      colWidth: 204 },
      { label: 'Attention',      value: '1 subsystem', colour: '#f0883e',                                    colWidth: 140 },
    ]
  }

  return (
    <div
      className="flex items-center gap-4 px-6 border-b border-border flex-shrink-0 relative"
      style={{ background: '#111821', height: 100, overflow: 'hidden' }}
    >
      {/* Teal/amber left accent bar */}
      <div
        className="absolute left-0 top-0 bottom-0 w-[5px] rounded-l"
        style={{ background: claimColour }}
      />

      {/* ── Claim ────────────────────────────────────────────────────────── */}
      <div className="pl-4 flex-1 min-w-0 overflow-hidden">
        <div
          className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] mb-1"
          style={{ color: '#4b5764' }}
        >
          {claimLabel}
        </div>
        {/* No flex-wrap — suffix must never push to a second line. */}
        <div className="flex items-baseline gap-2 overflow-hidden">
          <span
            className="font-mono font-bold leading-none flex-shrink-0"
            style={{
              fontSize: 36,
              color: claimColour,
              letterSpacing: running ? '-0.03em' : '0.01em',
            }}
          >
            {claimWord}
          </span>
          <span className="font-sans text-base text-text/90 font-light leading-tight truncate">
            {claimSuffix}
          </span>
        </div>
        <div className="font-mono text-[10px] text-muted mt-1 leading-snug truncate">
          {subtitle}
        </div>
      </div>

      {/* ── Divider ──────────────────────────────────────────────────────── */}
      <div className="self-stretch w-px bg-border mx-2 flex-shrink-0" />

      {/* ── Hero figures ─────────────────────────────────────────────────── */}
      <div className="flex items-start gap-6 flex-shrink-0">
        {figures.map((f, i) => (
          <div key={i} className="flex items-start gap-6">
            {i > 0 && <div className="self-stretch w-px bg-border" />}
            <HeroFigure {...f} />
          </div>
        ))}
      </div>
    </div>
  )
}
