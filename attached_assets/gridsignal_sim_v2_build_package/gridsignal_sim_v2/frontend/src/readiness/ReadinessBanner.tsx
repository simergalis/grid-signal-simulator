/**
 * ReadinessBanner.tsx — overall verdict + four hero figures (U2).
 *
 * The four hero figures are the responsive anchor — they survive every breakpoint.
 * Values come from the live tick; when no tick is available, all show '—'.
 *
 * Responsive layout (§5):
 *   ≥ 768 px  → 4-across hero strip
 *   < 768 px  → 2 × 2 grid
 */

import { useTickStore } from '../store/tickStore'

function formatBridge(s: number): string {
  if (s >= 86400) return 'full reserve'
  if (s <= 0)     return '0 s'
  if (s >= 3600)  return `${(s / 3600).toFixed(1)} h`
  if (s >= 60)    return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return `${s.toFixed(0)} s`
}

function HeroFigure({
  label,
  value,
  sub,
  colour,
}: {
  label: string
  value: string
  sub?: string
  colour?: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="font-mono text-[9px] uppercase tracking-wider text-muted">{label}</div>
      <div
        className="font-mono text-2xl font-semibold tabular-nums leading-none"
        style={colour ? { color: colour } : { color: '#e6edf3' }}
      >
        {value}
      </div>
      {sub && (
        <div className="font-mono text-[9px] text-muted">{sub}</div>
      )}
    </div>
  )
}

export function ReadinessBanner() {
  const tick    = useTickStore(s => s.latestTick)
  const alert   = useTickStore(s => s.latchedAlert)
  const runMeta = useTickStore(s => s.runMeta)

  // Overall verdict — three states
  const overallState = !tick
    ? { label: 'NO RUN', colour: '#8b949e', desc: 'Start a scenario to see live readiness.' }
    : alert
    ? { label: 'ATTENTION', colour: '#f0883e', desc: 'Insufficient reserve — acknowledge before dispatching further jobs.' }
    : tick.bess_bridging_seconds > 0
    ? { label: 'ARMED', colour: '#3fb6a8', desc: 'All primary systems ready. Dispatch authority available.' }
    : { label: 'READY', colour: '#3fb6a8', desc: 'All primary systems ready. No active run.' }

  // Hero figures (must survive every breakpoint)
  const dispatchable = tick
    ? `${tick.turbine_output_mw.toFixed(1)} MW`
    : '—'

  const leadTime = tick
    ? tick.dt_lead_next_s > 0 ? `${tick.dt_lead_next_s.toFixed(0)} s` : '—'
    : '—'

  const bridge = tick ? formatBridge(tick.bess_bridging_seconds) : '—'

  // Subsystems with attention: DQ tags or alert
  const needingAttention = !tick ? '—'
    : (alert ? 1 : 0) + tick.data_quality_tags.length

  return (
    <div className="border-b border-border bg-surface px-6 py-4">
      {/* Verdict strip */}
      <div className="flex items-center gap-3 mb-4">
        <div
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: overallState.colour }}
        />
        <span
          className="font-mono text-sm font-bold tracking-wider uppercase"
          style={{ color: overallState.colour }}
        >
          {overallState.label}
        </span>
        <span className="font-mono text-xs text-muted">{overallState.desc}</span>
        {runMeta && (
          <span className="ml-auto font-mono text-[10px] text-muted">
            {runMeta.playback_speed <= 0 ? 'max speed' : `${runMeta.playback_speed}× accel`}
          </span>
        )}
      </div>

      {/* Hero figures — 4-across ≥ 768 px, 2×2 below */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-6">
        <HeroFigure
          label="Dispatchable"
          value={dispatchable}
          sub="turbine output MW"
          colour={tick ? '#e0a458' : undefined}
        />
        <HeroFigure
          label="Lead time"
          value={leadTime}
          sub="until next GPU at full TDP"
        />
        <HeroFigure
          label="Bridge duration"
          value={bridge}
          sub={tick?.bridging_basis === 'predicted_peak' ? 'basis: predicted peak' : undefined}
          colour={tick && tick.bess_bridging_seconds === 0 ? '#f85149' : '#4a9fe0'}
        />
        <HeroFigure
          label="Needs attention"
          value={needingAttention === '—' ? '—' : String(needingAttention)}
          sub="subsystems"
          colour={typeof needingAttention === 'number' && needingAttention > 0 ? '#f0883e' : undefined}
        />
      </div>
    </div>
  )
}
