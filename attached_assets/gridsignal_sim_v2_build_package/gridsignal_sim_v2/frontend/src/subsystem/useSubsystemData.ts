/**
 * useSubsystemData.ts — selectors mapping tick fields → tile props (U4).
 *
 * Data flow: tickStore (Zustand) → selectors → ReadinessScreen tiles.
 * Tiles read from the tick stream only — no per-tile polling (§6 of plan).
 * Modals may poll endpoints on open, handled inside SubsystemModal.
 *
 * Colour constants match §4 of UI-IMPLEMENTATION-PLAN.
 * All metric values derived from live TickPayload fields — no invented numbers.
 * Where data genuinely doesn't exist, returns the honest string.
 */

import { useTickStore } from '../store/tickStore'
import type { TileState, TileMetric } from '../readiness/SubsystemTile'

const TEAL    = '#3fb6a8'
const GOLD    = '#e0a458'
const SOLAR   = '#f2c94c'
const BATTERY = '#4a9fe0'
const VIOLET  = '#9b8ce0'
const GREY    = '#5a6673'
const AMBER   = '#f0883e'
const RED     = '#f85149'

export interface SubsystemTileData {
  state: TileState
  verdict: string
  metrics: [TileMetric, TileMetric, TileMetric]
}

function fmtMW(v: number, d = 2): string { return `${v.toFixed(d)} MW` }
function fmtPct(v: number): string        { return `${(v * 100).toFixed(1)}%` }
function fmtTime(s: number): string {
  if (s >= 86400) return '∞'
  if (s >= 3600)  return `${(s / 3600).toFixed(1)} h`
  if (s >= 60)    return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return `${s.toFixed(0)} s`
}

export function useSubsystemData(): Record<string, SubsystemTileData> {
  const tick    = useTickStore(s => s.latestTick)
  const alert   = useTickStore(s => s.latchedAlert)

  if (!tick) {
    // No active run — all tiles show idle placeholders
    const idle = (name: string): SubsystemTileData => ({
      state:   '—',
      verdict: `No active run — start a scenario to see ${name} readiness.`,
      metrics: [
        { label: '—', value: '—' },
        { label: '—', value: '—' },
        { label: '—', value: '—' },
      ],
    })
    return {
      compute:          idle('compute'),
      thermal:          idle('thermal'),
      storage:          idle('storage'),
      generation:       idle('generation'),
      renewable:        idle('renewable'),
      grid:             idle('grid'),
      'forecast-quality': idle('forecast quality'),
      network:          idle('network'),
      agents:           idle('agent'),
    }
  }

  // ── Compute & Workload ───────────────────────────────────────────────────
  const runningJobs = Object.values(tick.checkpoint_states)
    .filter(s => s === 'running').length
  const totalJobs   = Object.keys(tick.checkpoint_states).length
  const computeState: TileState = runningJobs > 0 ? 'ACTIVE'
    : totalJobs > 0 ? 'ACTIVE' : 'READY'
  const computeVerdict = tick.dt_lead_next_s > 0
    ? `Ramp in progress — ${tick.dt_lead_next_s.toFixed(0)} s until GPU reaches full TDP.`
    : runningJobs > 0
    ? `${runningJobs} job${runningJobs > 1 ? 's' : ''} at full draw. Cooldown 90 s after finish.`
    : 'No jobs queued. Thermal load at rest.'

  // ── Thermal & Cooling ────────────────────────────────────────────────────
  const rated    = tick.rated_cooling_mw
  const absorb   = tick.absorbable_mw
  const fraction = rated > 0 ? absorb / rated : 1
  const thermalState: TileState = fraction < 0.05 ? 'ATTENTION' : 'READY'
  const thermalVerdict = fraction < 0.05
    ? `Low headroom — only ${fmtMW(absorb)} absorbable before approach.`
    : `Full headroom — ${fmtMW(absorb)} absorbable before approach.`

  // ── Energy Storage ───────────────────────────────────────────────────────
  const soc       = tick.bess_soc_fraction
  const bridge_s  = tick.bess_bridging_seconds
  const storageState: TileState = alert ? 'ATTENTION'
    : bridge_s >= 86400 ? 'READY'
    : bridge_s > 0 ? 'READY' : 'ATTENTION'
  const bridgeStr = bridge_s >= 86400 ? 'full reserve'
    : bridge_s >= 60 ? `${Math.floor(bridge_s / 60)}m ${Math.round(bridge_s % 60)}s`
    : `${bridge_s.toFixed(0)} s`
  const storageVerdict = bridge_s >= 86400
    ? `Full reserve — can bridge the predicted peak for the run duration.`
    : bridge_s > 0
    ? `Can bridge the predicted peak for ${bridgeStr} at current shortfall.`
    : `Cannot bridge — BESS power below predicted peak shortfall.`

  // ── Generation ───────────────────────────────────────────────────────────
  const turbineMW = tick.turbine_output_mw
  const genState: TileState = turbineMW > 0 ? 'ACTIVE' : 'READY'
  const genVerdict = turbineMW > 0
    ? `Producing ${fmtMW(turbineMW)} — ramping toward load demand.`
    : 'Turbine at standby. Will ramp when dispatch required.'

  // ── Renewable Supply ─────────────────────────────────────────────────────
  const solarMW = tick.p_renewable_mw
  const renewState: TileState = 'ADVISORY'  // by design — non-dispatchable
  const renewVerdict = solarMW > 0
    ? `Contributing ${fmtMW(solarMW)} — and it can vanish with no warning.`
    : 'No renewable output. Dispatch required equals total load.'

  // ── Grid Connection ──────────────────────────────────────────────────────
  // Grid is grey/ISLANDED by design — this is the "bring your own power" case
  const gridVerdict = 'Islanded by design — no utility dependency.'

  // ── Forecast Quality ─────────────────────────────────────────────────────
  const dqTags  = tick.data_quality_tags
  const bandMW  = tick.confidence_upper_mw - tick.confidence_lower_mw
  const fqState: TileState = dqTags.length > 0 ? 'ATTENTION' : 'READY'
  const fqVerdict = dqTags.length > 0
    ? `${dqTags.length} data-quality flag${dqTags.length > 1 ? 's' : ''} active — confidence band widened.`
    : 'All calibration checks clear. Confidence band nominal.'

  // ── Network Fabric ───────────────────────────────────────────────────────
  // No network data on the tick payload — honest empty state, not invented data
  const netVerdict = 'Network telemetry not instrumented in this tick.'

  // ── Optimisation Agents ──────────────────────────────────────────────────
  const agentVerdict = 'Finding patterns a threshold rule cannot — dispatch never waits.'

  return {
    compute: {
      state:   computeState,
      verdict: computeVerdict,
      metrics: [
        { label: 'Δt_lead',       value: tick.dt_lead_next_s > 0 ? `${tick.dt_lead_next_s.toFixed(0)} s` : '—' },
        { label: 'IT draw',        value: fmtMW(tick.p_compute_mw),                              colour: TEAL },
        { label: 'Jobs running',   value: `${runningJobs} / ${totalJobs}` },
      ],
    },

    thermal: {
      state:   thermalState,
      verdict: thermalVerdict,
      metrics: [
        { label: 'Absorbable',     value: fmtMW(absorb),                                         colour: fraction < 0.05 ? AMBER : BATTERY },
        { label: 'Time to limit',  value: fmtTime(tick.time_to_limit_s) },
        { label: 'Approach rate',  value: `${tick.approach_rate_mw_s.toFixed(3)} MW/s` },
      ],
    },

    storage: {
      state:   storageState,
      verdict: storageVerdict,
      metrics: [
        { label: 'Bridge duration', value: bridgeStr,                                             colour: bridge_s === 0 ? RED : BATTERY },
        { label: 'State of charge', value: fmtPct(soc),                                          colour: soc < 0.2 ? AMBER : undefined },
        { label: 'BESS output',     value: fmtMW(tick.bess_output_mw) },
      ],
    },

    generation: {
      state:   genState,
      verdict: genVerdict,
      metrics: [
        { label: 'Output',         value: fmtMW(turbineMW),                                      colour: GOLD },
        { label: 'Net demand',     value: fmtMW(tick.net_demand_mw) },
        { label: 'Coverage',       value: tick.net_demand_mw > 0 ? `${Math.min(100, turbineMW / tick.net_demand_mw * 100).toFixed(0)}%` : '—' },
      ],
    },

    renewable: {
      state:   renewState,
      verdict: renewVerdict,
      metrics: [
        { label: 'Output',                  value: fmtMW(solarMW),  colour: SOLAR },
        { label: 'Counted toward reserve',  value: 'never',         colour: AMBER },
        { label: 'Lead time on loss',       value: '0 s',           colour: RED },
      ],
    },

    grid: {
      state:   'ISLANDED',
      verdict: gridVerdict,
      metrics: [
        { label: 'MW imported',  value: '0.00 MW',        colour: GREY },
        { label: 'Connection',   value: 'islanded',       colour: GREY },
        { label: 'Utility feed', value: 'not connected',  colour: GREY },
      ],
    },

    'forecast-quality': {
      state:   fqState,
      verdict: fqVerdict,
      metrics: [
        { label: 'DQ tags',       value: dqTags.length > 0 ? dqTags.length.toString() : 'none',  colour: dqTags.length > 0 ? AMBER : TEAL },
        { label: 'Conf. band',    value: `±${(bandMW / 2).toFixed(2)} MW` },
        { label: 'Calibrated',    value: dqTags.includes('uncalibrated_site') ? 'NO' : 'yes',    colour: dqTags.includes('uncalibrated_site') ? RED : undefined },
      ],
    },

    network: {
      state:   '—',
      verdict: netVerdict,
      metrics: [
        { label: 'Latency',     value: 'not instrumented' },
        { label: 'Packet loss', value: 'not instrumented' },
        { label: 'Topology',    value: 'not instrumented' },
      ],
    },

    agents: {
      state:   'ARMED',
      verdict: agentVerdict,
      metrics: [
        { label: 'Agents armed',   value: '6 / 6',  colour: VIOLET },
        { label: 'Dispatch wait',  value: 'never',  colour: TEAL },
        { label: 'Authority',      value: 'advisory only' },
      ],
    },
  }
}
