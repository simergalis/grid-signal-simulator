/**
 * AssetReservePanel.tsx — BESS bridging seconds, SoC bar, turbine output (§19.4).
 *
 * §19.4: "the organizing question is how much time the battery buys, not
 * its state of charge."  The primary number is therefore bess_bridging_seconds,
 * not bess_soc_fraction — SoC is secondary context.
 *
 * C1 note: bess_bridging_seconds is computed by evaluate_tick() via
 * BessModule.max_sustainable_seconds() — the same function the
 * insufficient-reserve alert uses.  The panel and the alert can never
 * show different bridging durations because they are arithmetically identical.
 *
 * 86400 s is the JSON cap for math.inf (net_demand_mw == 0 → full reserve).
 * Displayed as "full reserve — no dispatch required" in that case.
 *
 * Usable SoC range: 10–95% (§3.3).  SoC bar shades the usable window.
 */

import { useTickStore } from '../store/tickStore'
import { DataQualityBadge } from './DataQualityBadge'

const SOC_MIN = 0.10   // §3.3 usable lower bound
const SOC_MAX = 0.95   // §3.3 usable upper bound
const BRIDGING_FULL_RESERVE = 86400  // server cap for math.inf

function formatBridging(seconds: number, basis: string): string {
  if (basis === 'no_load' || seconds >= BRIDGING_FULL_RESERVE)
    return 'full reserve'
  if (seconds === 0) return '0 s — cannot bridge'
  if (seconds >= 3600) return `${(seconds / 3600).toFixed(1)} h`
  if (seconds >= 60)   return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `${seconds.toFixed(0)} s`
}

function BasisLabel({ basis }: { basis: string }) {
  if (basis === 'no_load') return null
  const isPredicted = basis === 'predicted_peak'
  return (
    <div className={`font-mono text-[10px] ${isPredicted ? 'text-warn/80' : 'text-muted'}`}>
      basis: {isPredicted ? 'predicted peak shortfall' : 'current demand'}
    </div>
  )
}

interface SocBarProps {
  fraction: number
}

function SocBar({ fraction }: SocBarProps) {
  const pct     = Math.max(0, Math.min(1, fraction)) * 100
  const usable  = (SOC_MAX - SOC_MIN) * 100
  const socColor = fraction < SOC_MIN + 0.05
    ? 'bg-danger'
    : fraction < 0.35
      ? 'bg-warn'
      : 'bg-ok'

  return (
    <div className="relative h-3 w-full rounded-sm overflow-hidden bg-surface border border-border">
      {/* Usable window indicator */}
      <div
        className="absolute top-0 h-full bg-border/40"
        style={{ left: `${SOC_MIN * 100}%`, width: `${usable}%` }}
      />
      {/* SoC fill */}
      <div
        className={`absolute top-0 left-0 h-full transition-all duration-200 ${socColor}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

export function AssetReservePanel() {
  const tick   = useTickStore(s => s.latestTick)
  const tags   = tick?.data_quality_tags ?? []

  if (!tick) {
    return (
      <div className="flex h-full items-center justify-center text-muted font-mono text-sm">
        no active run
      </div>
    )
  }

  const basis        = tick.bridging_basis
  const bridgingStr  = formatBridging(tick.bess_bridging_seconds, basis)
  // cannotBridge: zero bridging when there IS a real (or predicted) demand to serve.
  // Uses binding_demand > 0 rather than net_demand_mw > 0 so that the "cannot bridge"
  // state appears correctly at t=0 when basis="predicted_peak" and demand is still 0.
  const bindingDemand = basis === 'no_load' ? 0 : 1   // >0 when basis is not no_load
  const cannotBridge = tick.bess_bridging_seconds === 0 && bindingDemand > 0
  const socPct       = (tick.bess_soc_fraction * 100).toFixed(1)

  return (
    <section className="flex h-full flex-col justify-between p-4 gap-3">
      <div className="font-mono text-xs uppercase tracking-wider text-muted">
        Asset reserve
      </div>

      {/* BESS bridging seconds — primary (§19.4) */}
      <div className="space-y-1">
        <div className="font-mono text-xs text-muted">BESS bridging capacity</div>
        <div className={`font-mono text-3xl font-semibold tabular-nums leading-none
          ${cannotBridge ? 'text-danger' : 'text-text'}`}
        >
          {bridgingStr}
        </div>
        {cannotBridge && (
          <div className="font-mono text-xs text-danger">
            above power ceiling — cannot bridge at{' '}
            {basis === 'predicted_peak' ? 'predicted peak shortfall' : 'current demand'}
          </div>
        )}
        <BasisLabel basis={basis} />
        {tags.length > 0 && (
          <div className="flex gap-1 flex-wrap">
            {tags.map(t => <DataQualityBadge key={t} tag={t} />)}
          </div>
        )}
      </div>

      {/* SoC — secondary context */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between font-mono text-xs text-muted">
          <span>State of charge</span>
          <span className="text-text">{socPct} %</span>
        </div>
        <SocBar fraction={tick.bess_soc_fraction} />
        <div className="flex justify-between font-mono text-[9px] text-muted">
          <span>10%</span>
          <span>usable range (§3.3)</span>
          <span>95%</span>
        </div>
      </div>

      {/* Turbine output */}
      <div className="space-y-0.5">
        <div className="font-mono text-xs text-muted">Turbine output</div>
        <div className="font-mono text-lg tabular-nums text-text">
          {tick.turbine_output_mw.toFixed(3)} MW
        </div>
        <div className="font-mono text-[10px] text-muted">
          BESS output: {tick.bess_output_mw.toFixed(3)} MW ·
          net demand: {tick.net_demand_mw.toFixed(3)} MW
        </div>
      </div>
    </section>
  )
}
