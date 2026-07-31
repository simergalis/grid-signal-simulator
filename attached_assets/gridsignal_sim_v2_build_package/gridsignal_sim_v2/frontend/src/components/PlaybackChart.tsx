/**
 * PlaybackChart.tsx — Static recharts chart for completed-run playback.
 *
 * Data is the full ordered TimeseriesRow list from GET /runs/{id}/timeseries.
 *
 * Gap handling (§2.2 — no fabricated curves):
 *   - Synthetic null entries are inserted between gapped rows so Recharts
 *     renders a line break rather than connecting the discontinuity.
 *   - Gray ReferenceAreas mark the time spans covered by gaps.
 *   - connectNulls is left at its default (false) so nulls break the line.
 *
 * Cursor:
 *   A vertical ReferenceLine highlights the tick under the scrubber cursor.
 */

import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
} from 'recharts'
import type { TimeseriesRow } from '../types'

function fmtTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return h > 0
    ? `${h}h${String(m).padStart(2, '0')}m`
    : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const COLOURS = {
  compute:   '#58a6ff',   // accent blue
  cooling:   '#f0883e',   // warm orange
  total:     '#e6edf3',   // text white
  renewable: '#3fb950',   // green
  band:      '#58a6ff',   // same as compute, low opacity fill
}

interface ChartDatum {
  t:         number | null
  compute:   number | null
  cooling:   number | null
  total:     number | null
  renewable: number | null
  band:      [number, number] | null
  alert:     boolean
}

interface Props {
  rows:      TimeseriesRow[]
  cursorIdx: number
}

export function PlaybackChart({ rows, cursorIdx }: Props) {
  if (rows.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-muted font-mono text-xs">
        no timeseries data
      </div>
    )
  }

  // Build chart data with synthetic nulls at gaps.
  const data: ChartDatum[] = []
  const gapZones: { x1: number; x2: number }[] = []

  for (let i = 0; i < rows.length; i++) {
    const r = rows[i]
    if (r.gap_before && i > 0) {
      // Insert null to break the line.
      data.push({ t: null, compute: null, cooling: null, total: null, renewable: null, band: null, alert: false })
      // Record gap zone for the gray ReferenceArea.
      gapZones.push({ x1: rows[i - 1].sim_time_seconds, x2: r.sim_time_seconds })
    }
    data.push({
      t:         r.sim_time_seconds,
      compute:   r.p_compute_mw,
      cooling:   r.p_cooling_mw,
      total:     r.p_total_mw,
      renewable: r.p_renewable_mw,
      band:      [r.confidence_lower_mw, r.confidence_upper_mw],
      alert:     r.insufficient_reserve_alert,
    })
  }

  // Cursor position: sim_time_seconds of the row under the scrubber.
  const cursorTime = cursorIdx >= 0 && cursorIdx < rows.length
    ? rows[cursorIdx].sim_time_seconds
    : null

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
        <XAxis
          dataKey="t"
          type="number"
          domain={['dataMin', 'dataMax']}
          tickFormatter={v => typeof v === 'number' ? fmtTime(v) : ''}
          tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'monospace' }}
          stroke="#30363d"
          allowDataOverflow
        />
        <YAxis
          tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'monospace' }}
          tickFormatter={(v: number) => `${v.toFixed(1)}`}
          label={{ value: 'MW', angle: -90, position: 'insideLeft', fill: '#8b949e', fontSize: 10 }}
          stroke="#30363d"
        />
        <Tooltip
          contentStyle={{
            background: '#161b22',
            border: '1px solid #30363d',
            fontFamily: 'monospace',
            fontSize: 11,
          }}
          labelFormatter={v => typeof v === 'number' ? `t=${fmtTime(v)}` : ''}
          formatter={(value: unknown, name: string) => {
            if (value === null || value === undefined) return ['-', name]
            if (Array.isArray(value)) return [`${(value as number[])[0].toFixed(2)}–${(value as number[])[1].toFixed(2)} MW`, 'conf. band']
            return [`${(value as number).toFixed(3)} MW`, name]
          }}
        />
        <Legend wrapperStyle={{ fontSize: 10, fontFamily: 'monospace', color: '#8b949e' }} />

        {/* Gray reference areas for gap zones */}
        {gapZones.map((z, i) => (
          <ReferenceArea
            key={i}
            x1={z.x1}
            x2={z.x2}
            fill="#8b949e"
            fillOpacity={0.12}
            label={{ value: 'gap', position: 'insideTop', fill: '#8b949e', fontSize: 9 }}
          />
        ))}

        {/* Cursor reference line */}
        {cursorTime !== null && (
          <ReferenceLine
            x={cursorTime}
            stroke="#58a6ff"
            strokeWidth={1.5}
            strokeDasharray="4 2"
          />
        )}

        {/* Confidence band — rendered first so lines draw on top */}
        <Area
          dataKey="band"
          fill={COLOURS.band}
          fillOpacity={0.12}
          stroke="none"
          name="conf. band"
          legendType="none"
          isAnimationActive={false}
          connectNulls={false}
        />

        <Line
          dataKey="compute"
          stroke={COLOURS.compute}
          dot={false}
          name="P_compute"
          strokeWidth={1.5}
          isAnimationActive={false}
          connectNulls={false}
        />
        <Line
          dataKey="cooling"
          stroke={COLOURS.cooling}
          dot={false}
          name="P_cooling"
          strokeWidth={1.5}
          isAnimationActive={false}
          connectNulls={false}
        />
        <Line
          dataKey="total"
          stroke={COLOURS.total}
          dot={false}
          name="P_total"
          strokeWidth={2}
          isAnimationActive={false}
          connectNulls={false}
        />
        <Line
          dataKey="renewable"
          stroke={COLOURS.renewable}
          dot={false}
          name="P_renewable"
          strokeWidth={1.5}
          isAnimationActive={false}
          connectNulls={false}
          strokeDasharray="4 2"
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
