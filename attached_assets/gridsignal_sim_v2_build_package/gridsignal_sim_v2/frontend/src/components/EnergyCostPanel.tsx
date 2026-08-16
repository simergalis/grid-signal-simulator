/**
 * EnergyCostPanel.tsx — Run-level energy accounting summary.
 *
 * Displays total energy cost (USD) and the MWh breakdown by source:
 *   site demand · on-site generation · solar · BESS charging · grid import
 *
 * All fields come from the run result API response (GET /runs/{id}/result).
 * Renders a compact placeholder when fields are null (headless runs, or DB
 * fallback rows written before this feature was deployed).
 */

import type { RunResult } from '../types'

interface Props {
  result: RunResult
}

function fmt(mwh: number | null, decimals = 2): string {
  if (mwh === null) return '—'
  return mwh.toFixed(decimals)
}

function fmtCost(usd: number | null): string {
  if (usd === null) return '—'
  return `$${usd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

interface RowProps {
  label: string
  mwh: number | null
  accent?: boolean
  dim?: boolean
}

function EnergyRow({ label, mwh, accent = false, dim = false }: RowProps) {
  return (
    <div className={`flex items-baseline justify-between gap-2 py-0.5
                     ${dim ? 'opacity-50' : ''}`}>
      <span className={`text-[11px] ${accent ? 'text-text' : 'text-muted'}`}>
        {label}
      </span>
      <span className={`font-mono text-[11px] tabular-nums
                        ${accent ? 'text-text font-semibold' : 'text-muted'}`}>
        {fmt(mwh)}&thinsp;MWh
      </span>
    </div>
  )
}

export function EnergyCostPanel({ result }: Props) {
  const {
    total_energy_cost_usd:        costUsd,
    total_energy_demand_mwh:      demandMwh,
    total_energy_generation_mwh:  genMwh,
    total_energy_solar_mwh:       solarMwh,
    total_energy_bess_charge_mwh: bessChargeMwh,
    total_energy_grid_import_mwh: gridImportMwh,
  } = result

  const hasData = costUsd !== null && costUsd !== undefined

  return (
    <div className="rounded border border-border bg-surface px-3 py-2.5">

      {/* Total cost headline */}
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted">
          Total cost
        </span>
        <span className={`font-mono text-sm font-bold tabular-nums
                          ${hasData ? 'text-accent' : 'text-muted'}`}>
          {fmtCost(costUsd)}
        </span>
      </div>

      {/* Divider */}
      <div className="border-t border-border mb-2" />

      {/* MWh breakdown */}
      {hasData ? (
        <div className="flex flex-col">
          <EnergyRow label="Site demand"       mwh={demandMwh}      accent />
          <EnergyRow label="On-site generation" mwh={genMwh} />
          {(solarMwh ?? 0) > 0.001 && (
            <EnergyRow label="Solar PV"         mwh={solarMwh} />
          )}
          {(bessChargeMwh ?? 0) > 0.001 && (
            <EnergyRow label="BESS charging"    mwh={bessChargeMwh} />
          )}
          <div className="border-t border-border my-1" />
          <EnergyRow
            label="Grid import"
            mwh={gridImportMwh}
            accent={(gridImportMwh ?? 0) > 0.001}
            dim={(gridImportMwh ?? 0) <= 0.001}
          />
        </div>
      ) : (
        <p className="text-[11px] text-muted italic">
          Not available for this run.
        </p>
      )}
    </div>
  )
}
