/**
 * SubsystemTile.tsx — one tile component, nine instances (U2).
 *
 * Props in, click out. No data fetching, no store access.
 * The parent (ReadinessScreen) computes state/verdict/metrics from the tick.
 *
 * state colour discipline:
 *   READY / ARMED / ACTIVE → teal or accentColor
 *   ATTENTION              → amber (#f0883e)
 *   ISLANDED / ADVISORY    → grey (#5a6673)
 *   INACTIVE / OFFLINE     → grey
 *   —  (no tick)           → muted
 */

export type TileState =
  | 'READY'
  | 'ACTIVE'
  | 'ARMED'
  | 'ATTENTION'
  | 'ISLANDED'
  | 'ADVISORY'
  | 'INACTIVE'
  | 'OFFLINE'
  | '—'

const STATE_COLOUR: Record<TileState, string> = {
  READY:     '#3fb6a8',
  ACTIVE:    '#3fb6a8',
  ARMED:     '#3fb6a8',
  ATTENTION: '#f0883e',
  ISLANDED:  '#5a6673',
  ADVISORY:  '#5a6673',
  INACTIVE:  '#5a6673',
  OFFLINE:   '#f85149',
  '—':       '#30363d',
}

export interface TileMetric {
  label: string
  value: string
  colour?: string
}

export interface SubsystemTileProps {
  id: string
  name: string
  state: TileState
  accentColor: string
  verdict: string
  metrics: [TileMetric, TileMetric, TileMetric]
  onClick: (id: string) => void
}

export function SubsystemTile({
  id,
  name,
  state,
  accentColor,
  verdict,
  metrics,
  onClick,
}: SubsystemTileProps) {
  const stateDot = STATE_COLOUR[state]
  const isIdle   = state === '—'

  return (
    <button
      className={`
        relative flex flex-col text-left w-full h-full rounded-lg overflow-hidden
        border border-border bg-surface
        transition-colors hover:border-muted/60 focus:outline-none
        focus-visible:ring-1 focus-visible:ring-accent
      `}
      onClick={() => onClick(id)}
      data-subsystem-id={id}
    >
      {/* Accent top bar */}
      <div
        className="absolute inset-x-0 top-0 h-[3px]"
        style={{ background: isIdle ? '#30363d' : accentColor }}
      />

      {/* Content */}
      <div className="flex flex-col flex-1 p-4 pt-5">

        {/* Header: name + state badge */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <h3 className="font-mono text-xs font-semibold text-text leading-tight">
            {name}
          </h3>
          <div className="flex items-center gap-1 shrink-0">
            <div
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ background: stateDot }}
            />
            <span
              className="font-mono text-[9px] font-bold tracking-wider uppercase"
              style={{ color: stateDot }}
            >
              {state}
            </span>
          </div>
        </div>

        {/* Verdict — phrased against forecast demand, not equipment status */}
        <p className={`font-mono text-[10px] leading-relaxed mb-4 flex-1
          ${isIdle ? 'text-muted' : 'text-text/80'}`}
        >
          {verdict}
        </p>

        {/* Three key metrics */}
        <div className="space-y-1.5 border-t border-border pt-3">
          {metrics.map((m, i) => (
            <div key={i} className="flex items-baseline justify-between gap-2">
              <span className="font-mono text-[9px] text-muted truncate">
                {m.label}
              </span>
              <span
                className="font-mono text-[10px] tabular-nums shrink-0"
                style={m.colour ? { color: m.colour } : { color: '#e6edf3' }}
              >
                {m.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </button>
  )
}
