/**
 * ForecastChart.tsx — live-updating power-forecast chart (§7.1 / §19.2).
 *
 * Recharts ComposedChart:
 *   Lines:  P_compute, P_cooling, P_total, P_renewable
 *   Area:   confidence band (lower → upper), shaded
 *   X-axis: sim_time_seconds, trailing HISTORY_MAX ticks
 *
 * Decimation indicator: when N > 1 ticks arrived in the last frame, the
 * chart shows all N points but displays "showing 1 of N" as a badge.
 * No interpolation when decimating — connecting dropped ticks would
 * fabricate a curve the simulation did not produce (§2.2).
 *
 * DQ flags: if data_quality_tags is non-empty on the latest tick, badges
 * appear in the chart legend next to the affected value labels.
 */

import {
  ComposedChart, Line, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts'
import { useTickStore } from '../store/tickStore'
import { DataQualityBadge } from './DataQualityBadge'

function fmtTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return h > 0 ? `${h}h${String(m).padStart(2,'0')}m` : `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
}

const COLOURS = {
  compute:    '#58a6ff',   // accent blue
  cooling:    '#f0883e',   // warm orange
  total:      '#e6edf3',   // text white
  renewable:  '#3fb950',   // green
  band:       '#58a6ff',   // same as compute, low opacity fill
}

export function ForecastChart() {
  const history       = useTickStore(s => s.history)
  const latestTick    = useTickStore(s => s.latestTick)
  const decimation    = useTickStore(s => s.decimationCount)
  const isInterp      = useTickStore(s => s.isInterpolated)

  const tags = latestTick?.data_quality_tags ?? []

  if (history.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-muted font-mono text-sm">
        waiting for data…
      </div>
    )
  }

  // Recharts needs plain objects with exactly the keys referenced in dataKey props.
  // Confidence band: use area between lower and upper.  Recharts Area with
  // a two-key datum renders a filled region between them.
  const data = history.map(h => ({
    t:         h.sim_time_seconds,
    compute:   h.p_compute_mw,
    cooling:   h.p_cooling_mw,
    total:     h.p_total_mw,
    renewable: h.p_renewable_mw,
    // Recharts Area expects [low, high] as a two-element array for a range area.
    band:      [h.confidence_lower_mw, h.confidence_upper_mw] as [number, number],
  }))

  return (
    <section className="flex h-full flex-col p-3 pb-1">
      {/* Header row */}
      <div className="mb-1 flex items-center justify-between">
        <span className="font-mono text-xs uppercase tracking-wider text-muted">
          Power forecast
        </span>
        <div className="flex items-center gap-2">
          {isInterp && (
            <span className="font-mono text-[10px] italic text-muted">~interp</span>
          )}
          {decimation > 1 && (
            <span className="rounded border border-warn/40 bg-warn/10 px-1.5 py-0.5
                             font-mono text-[10px] text-warn">
              1 of {decimation} ticks/frame
            </span>
          )}
          {tags.map(t => <DataQualityBadge key={t} tag={t} />)}
        </div>
      </div>

      {/* Chart */}
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
            <XAxis
              dataKey="t"
              tickFormatter={fmtTime}
              tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'monospace' }}
              stroke="#30363d"
            />
            <YAxis
              tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'monospace' }}
              tickFormatter={(v: number) => `${v.toFixed(1)}`}
              label={{ value: 'MW', angle: -90, position: 'insideLeft',
                       fill: '#8b949e', fontSize: 10 }}
              stroke="#30363d"
            />
            <Tooltip
              contentStyle={{ background: '#161b22', border: '1px solid #30363d',
                              fontFamily: 'monospace', fontSize: 11 }}
              labelFormatter={(v: number) => `t=${fmtTime(v)}`}
              formatter={(value: number | [number, number], name: string) => {
                if (Array.isArray(value)) return [`${value[0].toFixed(2)}–${value[1].toFixed(2)} MW`, 'conf. band']
                return [`${value.toFixed(3)} MW`, name]
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: 10, fontFamily: 'monospace', color: '#8b949e' }}
            />

            {/* Confidence band — rendered first so lines draw on top */}
            <Area
              dataKey="band"
              fill={COLOURS.band}
              fillOpacity={0.12}
              stroke="none"
              name="conf. band"
              legendType="none"
              isAnimationActive={false}
            />

            <Line dataKey="compute"   stroke={COLOURS.compute}   dot={false}
                  name="P_compute"    strokeWidth={1.5} isAnimationActive={false} />
            <Line dataKey="cooling"   stroke={COLOURS.cooling}   dot={false}
                  name="P_cooling"    strokeWidth={1.5} isAnimationActive={false} />
            <Line dataKey="total"     stroke={COLOURS.total}     dot={false}
                  name="P_total"      strokeWidth={2}   isAnimationActive={false} />
            <Line dataKey="renewable" stroke={COLOURS.renewable} dot={false}
                  name="P_renewable"  strokeWidth={1.5} isAnimationActive={false}
                  strokeDasharray="4 2" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
