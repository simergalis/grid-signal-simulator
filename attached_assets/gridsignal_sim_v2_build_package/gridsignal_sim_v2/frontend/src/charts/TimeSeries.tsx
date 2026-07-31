/**
 * TimeSeries.tsx — multi-line time-series chart (U1 chart primitive).
 *
 * Uses Recharts where it fits (layout, interaction, SVG output).
 * Props in, chart out — no data fetching, no store access.
 *
 * dense=true reduces padding and label sizes for tile embedding.
 * The same component serves both the tile sparkline and the modal chart.
 */

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceLine,
  Tooltip,
  Area,
  AreaChart,
  ComposedChart,
} from 'recharts'

export interface TimeSeriesPoint {
  x: number
  y: number
}

export interface TimeSeriesSeries {
  label: string
  colour: string
  points: TimeSeriesPoint[]
  filled?: boolean   // renders a filled area under the line
}

export interface TimeSeriesMarker {
  x: number
  label: string
  colour?: string
}

export interface TimeSeriesCeiling {
  y: number
  label: string
  colour?: string
}

export interface TimeSeriesProps {
  series: TimeSeriesSeries[]
  yMax?: number
  markers?: TimeSeriesMarker[]
  ceiling?: TimeSeriesCeiling
  xLabel?: string
  dense?: boolean
  height?: number
}

/** Merge all series into a single [{x, s0, s1, ...}] array for Recharts. */
function mergeToRows(series: TimeSeriesSeries[]): Record<string, number>[] {
  const xs = new Set<number>()
  series.forEach(s => s.points.forEach(p => xs.add(p.x)))
  const sorted = Array.from(xs).sort((a, b) => a - b)
  return sorted.map(x => {
    const row: Record<string, number> = { x }
    series.forEach((s, i) => {
      const pt = s.points.find(p => p.x === x)
      if (pt !== undefined) row[`s${i}`] = pt.y
    })
    return row
  })
}

export function TimeSeries({
  series,
  yMax,
  markers = [],
  ceiling,
  xLabel,
  dense = false,
  height = 220,
}: TimeSeriesProps) {
  const data = mergeToRows(series)

  const mx = dense ? { top: 4, right: 8, bottom: 20, left: 28 }
               : { top: 8, right: 16, bottom: 32, left: 40 }
  const tickStyle = { fill: '#4b5764', fontSize: dense ? 8 : 9, fontFamily: 'JetBrains Mono, monospace' }
  const gridColour = '#1e2a36'

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={mx}>
          <CartesianGrid stroke={gridColour} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="x"
            tick={tickStyle}
            axisLine={false}
            tickLine={false}
            label={xLabel ? {
              value: xLabel,
              position: 'insideBottomRight',
              offset: -4,
              fill: '#4b5764',
              fontSize: dense ? 7 : 8,
            } : undefined}
          />
          <YAxis
            domain={yMax !== undefined ? [0, yMax] : ['auto', 'auto']}
            tick={tickStyle}
            axisLine={false}
            tickLine={false}
            width={dense ? 24 : 32}
          />

          {/* Ceiling reference line */}
          {ceiling && (
            <ReferenceLine
              y={ceiling.y}
              stroke={ceiling.colour ?? '#d9534f'}
              strokeDasharray="5 4"
              strokeWidth={1.2}
              label={{
                value: ceiling.label,
                position: 'insideTopRight',
                fill: ceiling.colour ?? '#d9534f',
                fontSize: dense ? 7 : 8,
              }}
            />
          )}

          {/* Event markers */}
          {markers.map((m, i) => (
            <ReferenceLine
              key={i}
              x={m.x}
              stroke={m.colour ?? '#7d8b9c'}
              strokeDasharray="2 4"
              strokeWidth={1}
              label={{
                value: m.label,
                position: 'insideTopRight',
                fill: m.colour ?? '#7d8b9c',
                fontSize: dense ? 7 : 8,
              }}
            />
          ))}

          {/* Series lines (and optional fill areas) */}
          {series.map((s, i) =>
            s.filled ? (
              <Area
                key={i}
                type="monotone"
                dataKey={`s${i}`}
                stroke={s.colour}
                strokeWidth={dense ? 1.5 : 2}
                fill={s.colour}
                fillOpacity={0.14}
                dot={false}
                isAnimationActive={false}
                name={s.label}
              />
            ) : (
              <Line
                key={i}
                type="monotone"
                dataKey={`s${i}`}
                stroke={s.colour}
                strokeWidth={dense ? 1.5 : 2}
                dot={false}
                isAnimationActive={false}
                name={s.label}
              />
            )
          )}

          {!dense && (
            <Tooltip
              contentStyle={{
                background: '#161b22',
                border: '1px solid #30363d',
                borderRadius: 4,
                fontSize: 10,
                fontFamily: 'JetBrains Mono, monospace',
                color: '#e6edf3',
              }}
              cursor={{ stroke: '#30363d', strokeWidth: 1 }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
