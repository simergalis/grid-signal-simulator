/**
 * VerdictBand.tsx — Band 1 of the opening screen (V-2).
 *
 * Left: one computed claim about plant readiness — not equipment status.
 * Right: four hero figures, sourced from the live tick or static defaults.
 *
 * The "ⓘ How it works" button lives in GridSignalHeader, not here.
 *
 * Static defaults (no tick):
 *   DISPATCHABLE  48.0 MW  — turbine (25) + BESS (18) + solar (5) rated
 *   LEAD TIME     30–60 s  — configured dt_lead window for demo scenario
 *   BRIDGE        full reserve  — BESS at 95 % SoC, no load yet
 *   ATTENTION     1 subsystem   — uncalibrated_site DQ flag always present
 *
 * Running state (dt_lead_next_s > 0):
 *   Site draw / Predicted peak / Bridge duration / Reserve status
 *
 * Alert latched:
 *   Claim turns amber, suffix describes the reserve shortfall.
 */

import { useTickStore } from '../store/tickStore'

interface FigureProps {
  label: string
  value: string
  colour?: string
  sub?: string
}

function HeroFigure({ label, value, colour, sub }: FigureProps) {
  return (
    <div className="flex flex-col gap-0.5 min-w-[88px]">
      <div className="font-mono text-[9px] uppercase tracking-wider text-muted">{label}</div>
      <div
        className="font-mono text-lg font-semibold tabular-nums leading-none"
        style={colour ? { color: colour } : { color: '#e6edf3' }}
      >
        {value}
      </div>
      {sub && <div className="font-mono text-[9px] text-muted mt-0.5 leading-tight">{sub}</div>}
    </div>
  )
}

function formatBridge(s: number): string {
  if (s >= 86400) return 'full reserve'
  if (s <= 0) return '0 s'
  if (s >= 3600) return `${(s / 3600).toFixed(1)} h`
  if (s >= 60) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return `${s.toFixed(0)} s`
}

export function VerdictBand() {
  const tick  = useTickStore(s => s.latestTick)
  const alert = useTickStore(s => s.latchedAlert)

  const running  = tick !== null && tick.dt_lead_next_s > 0
  const hasAlert = alert !== null
  const hasRun   = tick !== null

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
    claimSuffix = 'to stage a load event'
    claimColour = '#3fb6a8'
    subtitle    = '8 of 9 subsystems nominal · forecast bands widened pending calibration'
  }

  // ── Hero figures ─────────────────────────────────────────────────────────

  let figures: FigureProps[]

  if (running && tick) {
    figures = [
      {
        label: 'Site Draw',
        value: `${tick.p_total_mw.toFixed(2)} MW`,
      },
      {
        label: 'Predicted Peak',
        value: `${tick.confidence_upper_mw.toFixed(2)} MW`,
        colour: '#e0a458',
      },
      {
        label: 'Bridge',
        value: formatBridge(tick.bess_bridging_seconds),
        colour: '#4a9fe0',
        sub: tick.bridging_basis === 'predicted_peak' ? 'basis: predicted peak' : undefined,
      },
      {
        label: 'Reserve',
        value: hasAlert ? 'insufficient' : 'sufficient',
        colour: hasAlert ? '#f0883e' : '#3fb6a8',
      },
    ]
  } else if (hasRun && tick) {
    const dqCount = tick.data_quality_tags.length + (hasAlert ? 1 : 0)
    figures = [
      {
        label: 'Dispatchable',
        value: `${(tick.turbine_output_mw + tick.p_renewable_mw).toFixed(1)} MW`,
        colour: '#e0a458',
        sub: 'turbine + solar',
      },
      {
        label: 'Lead Time',
        value: tick.dt_lead_next_s > 0 ? `${tick.dt_lead_next_s.toFixed(0)} s` : '—',
        colour: '#3fb6a8',
      },
      {
        label: 'Bridge',
        value: formatBridge(tick.bess_bridging_seconds),
        colour: '#4a9fe0',
      },
      {
        label: 'Attention',
        value: dqCount > 0 ? `${dqCount} subsystem` : '—',
        colour: dqCount > 0 ? '#f0883e' : undefined,
      },
    ]
  } else {
    // Static defaults — show configured site capacity before any run
    figures = [
      { label: 'Dispatchable', value: '48.0 MW',      colour: '#e0a458', sub: 'turbine + BESS + solar' },
      { label: 'Lead Time',    value: '30–60 s',       colour: '#3fb6a8' },
      { label: 'Bridge',       value: 'full reserve',  colour: '#4a9fe0' },
      { label: 'Attention',    value: '1 subsystem',   colour: '#f0883e' },
    ]
  }

  return (
    <div
      className="flex items-center gap-4 px-6 py-4 border-b border-border flex-shrink-0 relative"
      style={{ background: '#111821', minHeight: 100 }}
    >
      {/* Teal/amber left accent bar */}
      <div
        className="absolute left-0 top-0 bottom-0 w-[5px] rounded-l"
        style={{ background: claimColour }}
      />

      {/* ── Claim ────────────────────────────────────────────────────────── */}
      <div className="pl-4 flex-1 min-w-0">
        <div
          className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] mb-1"
          style={{ color: '#4b5764' }}
        >
          {claimLabel}
        </div>
        <div className="flex items-baseline gap-2 flex-wrap">
          <span
            className="font-mono font-bold leading-none"
            style={{
              fontSize: running ? 36 : 32,
              color: claimColour,
              letterSpacing: running ? '-0.03em' : '0.01em',
            }}
          >
            {claimWord}
          </span>
          <span className="font-sans text-base text-text/90 font-light leading-tight">
            {claimSuffix}
          </span>
        </div>
        <div className="font-mono text-[10px] text-muted mt-1 leading-snug">
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
