/**
 * TickDetail.tsx — Key-value display for the tick under the playback cursor.
 *
 * Shows the most diagnostically useful fields from a TimeseriesRow.
 * Renders a DATA GAP badge when gap_before is true.
 */

import type { TimeseriesRow } from '../types'

function fmtTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return h > 0
    ? `${h}h${String(m).padStart(2, '0')}m${String(s).padStart(2, '0')}s`
    : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function fmt(v: number, decimals = 3): string {
  return v.toFixed(decimals)
}

interface Props {
  row: TimeseriesRow | null
}

export function TickDetail({ row }: Props) {
  if (!row) {
    return (
      <div className="flex h-full items-center justify-center text-muted font-mono text-xs">
        select a tick
      </div>
    )
  }

  const fields: [string, string][] = [
    ['sim_time',    fmtTime(row.sim_time_seconds)],
    ['tick_index',  String(row.tick_index)],
    ['P_total',     `${fmt(row.p_total_mw)} MW`],
    ['P_compute',   `${fmt(row.p_compute_mw)} MW`],
    ['P_cooling',   `${fmt(row.p_cooling_mw)} MW`],
    ['P_renewable', `${fmt(row.p_renewable_mw)} MW`],
    ['P_turbine',   `${fmt(row.turbine_output_mw)} MW`],
    ['P_bess',      `${fmt(row.bess_output_mw)} MW`],
    ['BESS SoC',    `${(row.bess_soc_fraction * 100).toFixed(1)} %`],
    ['net_demand',  `${fmt(row.net_demand_mw)} MW`],
    ['conf_band',   `${fmt(row.confidence_lower_mw)}–${fmt(row.confidence_upper_mw)} MW`],
    ['bridging',    `${row.bess_bridging_seconds >= 86400 ? '≥24 h' : fmtTime(row.bess_bridging_seconds)}`],
    ['basis',       row.bridging_basis],
    ['dt_lead',     `${fmt(row.dt_lead_next_s, 1)} s`],
  ]

  return (
    <div className="flex flex-col gap-1">
      {/* Gap badge */}
      {row.gap_before && (
        <div className="rounded border border-amber-600/60 bg-amber-900/20
                        px-2 py-0.5 text-[10px] font-mono text-amber-400">
          ▲ DATA GAP before this tick
        </div>
      )}

      {/* Alert badge */}
      {row.insufficient_reserve_alert && (
        <div className="rounded border border-red-600/60 bg-red-900/20
                        px-2 py-0.5 text-[10px] font-mono text-red-400">
          ⚡ INSUFFICIENT RESERVE ALERT
        </div>
      )}

      {/* Key-value table */}
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
        {fields.map(([k, v]) => (
          <div key={k} className="contents">
            <span className="font-mono text-[10px] text-muted text-right leading-5 truncate">
              {k}
            </span>
            <span className="font-mono text-[10px] text-text leading-5 truncate">
              {v}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
