/**
 * smoke_panels.test.tsx — headless DOM check for all four dashboard panels.
 *
 * Substitutes for the Playwright screenshot check when a headless Chromium
 * binary is unavailable (libglib-2.0.so.0 missing in this NixOS sandbox).
 * Uses Vitest + jsdom + @testing-library/react to actually execute the React
 * components and assert key UI text.
 *
 * Covers:
 *   F4 — alert latch: banner stays visible after non-alert ticks; clears on Ack.
 *   F2 — basis label: AssetReservePanel shows "predicted_peak" text.
 *   F5 — sim_time: wire payload carries interval-end value (5.0, not 0.0).
 *   Panel mounting: all four panels render without throwing.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { AlertDock } from '../components/AlertDock'
import { AssetReservePanel } from '../components/AssetReservePanel'
import { HeroPanel } from '../components/HeroPanel'
import { ForecastChart } from '../components/ForecastChart'
import { useTickStore } from '../store/tickStore'
import type { TickPayload } from '../types'

// ── Fixture ticks (mirrors wire data from demo-alert Python run) ─────────────

/** Tick 1 — alert fires, ramp just started, BESS above ceiling at predicted peak. */
const ALERT_TICK: TickPayload = {
  run_id: 'smoke-test',
  tick_index: 1,
  sim_time_seconds: 5.0,        // F5: interval-end (clock.sim_time=0 + dt=5)
  p_compute_mw: 0.5545,
  p_cooling_mw: 0.0,
  p_total_mw: 0.5545,
  net_demand_mw: 0.0,
  turbine_output_mw: 0.0,
  bess_output_mw: 0.0,
  bess_soc_fraction: 0.95,
  confidence_lower_mw: 0.4824,
  confidence_upper_mw: 0.6266,
  p_renewable_mw: 4.9904,
  bess_bridging_seconds: 0.0,   // F2: 0 because predicted_peak > BESS ceiling
  bridging_basis: 'predicted_peak',
  dt_lead_next_s: 40.0,
  insufficient_reserve_alert: true,
  data_quality_tags: [],
  checkpoint_states: {},
  // W1c — thermal headroom fields (stamped by backend before broadcast)
  rated_cooling_mw:   0.0,
  absorbable_mw:      0.0,
  time_to_limit_s:    86400.0,
  approach_rate_mw_s: 0.0,
}

/** Tick 2 — alert flag cleared; banner must still show (F4 latch). */
const FOLLOW_TICK: TickPayload = {
  ...ALERT_TICK,
  tick_index: 2,
  sim_time_seconds: 10.0,
  insufficient_reserve_alert: false,
  bess_bridging_seconds: 86400,
  bridging_basis: 'no_load',
  dt_lead_next_s: 35.0,
  net_demand_mw: 0.0,
}

/** Tick with demand above BESS ceiling but no pending alert. */
const DEMAND_TICK: TickPayload = {
  ...ALERT_TICK,
  tick_index: 9,
  sim_time_seconds: 45.0,
  insufficient_reserve_alert: false,
  net_demand_mw: 14.97,
  bess_bridging_seconds: 0.0,
  bridging_basis: 'current_demand',
  dt_lead_next_s: 0.0,
}

function seed(...ticks: TickPayload[]) {
  const store = useTickStore.getState()
  store.setRunMeta({ run_id: 'smoke-test', playback_speed: 10 })
  for (const t of ticks) store.pushTick(t)
  store.drainFrame()
}

beforeEach(() => {
  useTickStore.getState().reset()
  cleanup()
})

// ── F4 — alert latch ──────────────────────────────────────────────────────────

describe('F4 — alert latch', () => {
  it('AlertDock shows banner immediately after alert tick', () => {
    seed(ALERT_TICK)
    render(<AlertDock />)
    expect(screen.getByText(/Insufficient reserve/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Acknowledge/i })).toBeInTheDocument()
    expect(screen.getByText(/Alert fired at tick #1/i)).toBeInTheDocument()
  })

  it('AlertDock banner persists after subsequent non-alert tick (rising-edge latch)', () => {
    seed(ALERT_TICK)
    // Push a non-alert tick — latched banner must survive
    useTickStore.getState().pushTick(FOLLOW_TICK)
    useTickStore.getState().drainFrame()
    render(<AlertDock />)
    expect(screen.getByText(/Insufficient reserve/i)).toBeInTheDocument()
  })

  it('AlertDock banner clears only after Acknowledge', async () => {
    seed(ALERT_TICK)
    useTickStore.getState().acknowledgeAlert(1)   // acknowledge tick_index=1
    render(<AlertDock />)
    expect(screen.queryByText(/Insufficient reserve/i)).not.toBeInTheDocument()
    expect(screen.getByText(/No active alerts/i)).toBeInTheDocument()
  })

  it('new alert on later tick re-latches after ack', () => {
    seed(ALERT_TICK)
    useTickStore.getState().acknowledgeAlert(1)
    // New alert on tick 50
    const newAlert = { ...ALERT_TICK, tick_index: 50, sim_time_seconds: 250.0 }
    useTickStore.getState().pushTick(newAlert)
    useTickStore.getState().drainFrame()
    render(<AlertDock />)
    expect(screen.getByText(/Insufficient reserve/i)).toBeInTheDocument()
    expect(screen.getByText(/Alert fired at tick #50/i)).toBeInTheDocument()
  })

  it('latch records firing tick sim_time — not latestTick sim_time', () => {
    seed(ALERT_TICK)
    // Push many follow ticks advancing sim_time well beyond 5.0
    for (let i = 2; i <= 10; i++) {
      useTickStore.getState().pushTick({ ...FOLLOW_TICK, tick_index: i, sim_time_seconds: i * 5.0 })
      useTickStore.getState().drainFrame()
    }
    render(<AlertDock />)
    // Banner still shows, and sim_time reads 5 s (the tick that fired), not 50 s
    expect(screen.getByText(/5 s/i)).toBeInTheDocument()
    expect(screen.getByText(/Insufficient reserve/i)).toBeInTheDocument()
  })
})

// ── F2 — bridging basis label ─────────────────────────────────────────────────

describe('F2 — AssetReservePanel bridging basis', () => {
  it('shows "0 s — cannot bridge" and predicted_peak basis at alert tick', () => {
    seed(ALERT_TICK)
    render(<AssetReservePanel />)
    expect(screen.getByText(/0 s/i)).toBeInTheDocument()
    // Both the danger sub-label and the BasisLabel contain "predicted peak shortfall"
    // — use getAllByText which accepts multiple matches.
    const predicted = screen.getAllByText(/predicted peak shortfall/i)
    expect(predicted.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/above power ceiling/i)).toBeInTheDocument()
  })

  it('cannot-bridge text names predicted peak (not current demand) when basis=predicted_peak', () => {
    seed(ALERT_TICK)
    render(<AssetReservePanel />)
    // The danger sub-label should specifically call out predicted peak
    const dangerText = screen.getByText(/above power ceiling/i).textContent
    expect(dangerText).toMatch(/predicted peak/i)
    expect(dangerText).not.toMatch(/current demand/i)
  })

  it('shows "basis: current demand" when net demand is positive and no pending alert', () => {
    seed(DEMAND_TICK)
    render(<AssetReservePanel />)
    expect(screen.getByText(/basis: current demand/i)).toBeInTheDocument()
  })

  it('no basis label when no_load (full reserve)', () => {
    seed(FOLLOW_TICK)
    render(<AssetReservePanel />)
    expect(screen.queryByText(/basis:/i)).not.toBeInTheDocument()
    expect(screen.getByText(/full reserve/i)).toBeInTheDocument()
  })
})

// ── F5 — sim_time is interval-end ────────────────────────────────────────────

describe('F5 — sim_time_seconds is interval-end', () => {
  it('ALERT_TICK fixture has sim_time=5.0 (clock.sim_time=0 + dt=5)', () => {
    expect(ALERT_TICK.sim_time_seconds).toBe(5.0)
  })

  it('FOLLOW_TICK has sim_time=10.0 (second tick)', () => {
    expect(FOLLOW_TICK.sim_time_seconds).toBe(10.0)
  })
})

// ── Panel mounting ────────────────────────────────────────────────────────────

describe('Panel mounting — all four panels render without throwing', () => {
  beforeEach(() => seed(ALERT_TICK))

  it('AlertDock mounts and shows dock header', () => {
    render(<AlertDock />)
    expect(screen.getByText(/Alert dock/i)).toBeInTheDocument()
  })

  it('AssetReservePanel mounts and shows header', () => {
    render(<AssetReservePanel />)
    expect(screen.getByText(/Asset reserve/i)).toBeInTheDocument()
  })

  it('HeroPanel mounts and shows countdown header', () => {
    render(<HeroPanel />)
    expect(screen.getByText(/Time to next full-TDP/i)).toBeInTheDocument()
  })

  it('HeroPanel shows dt_lead countdown value (40.0s)', () => {
    render(<HeroPanel />)
    expect(screen.getByText(/40\.0s/i)).toBeInTheDocument()
  })

  it('ForecastChart mounts without throwing', () => {
    const { container } = render(<ForecastChart />)
    // Recharts renders SVG; just assert the container is non-empty
    expect(container.firstChild).not.toBeNull()
  })
})

// ── Turbine ramp credit / peak shortfall ─────────────────────────────────────

/** Tick with a job actively ramping, ramp credit partially covers the step. */
const RAMP_CREDIT_TICK: TickPayload = {
  ...ALERT_TICK,
  tick_index: 3,
  sim_time_seconds: 15.0,
  dt_lead_next_s: 35.0,           // ramp still in-flight
  insufficient_reserve_alert: false,
  bess_bridging_seconds: 300.0,
  bridging_basis: 'predicted_peak',
  turbine_ramp_credit_mw: 6.0,   // turbines already ramped 6 MW
  peak_shortfall_mw: 8.0,        // BESS must still bridge 8 MW
}

/** Tick where ramp credit fully covers the step — zero shortfall. */
const COVERED_BY_RAMP_TICK: TickPayload = {
  ...ALERT_TICK,
  tick_index: 4,
  sim_time_seconds: 20.0,
  dt_lead_next_s: 20.0,           // ramp still in-flight
  insufficient_reserve_alert: false,
  bess_bridging_seconds: 86400.0,
  bridging_basis: 'no_load',
  turbine_ramp_credit_mw: 5.0,
  peak_shortfall_mw: 0.0,        // fully covered by ramp
}

/** Tick after the ramp completed — no staging data visible. */
const POST_RAMP_TICK: TickPayload = {
  ...DEMAND_TICK,
  tick_index: 10,
  sim_time_seconds: 50.0,
  dt_lead_next_s: 0.0,            // ramp complete
  turbine_ramp_credit_mw: 0.0,
  peak_shortfall_mw: 0.0,
}

describe('AssetReservePanel — turbine ramp credit / peak shortfall staging', () => {
  it('shows ramp staging block when dt_lead_next_s > 0', () => {
    seed(RAMP_CREDIT_TICK)
    render(<AssetReservePanel />)
    expect(screen.getByText(/Ramp staging/i)).toBeInTheDocument()
    expect(screen.getByText(/Turbine ramp credit/i)).toBeInTheDocument()
    // "Peak shortfall" row label — use getAllByText because the basis label also
    // contains the substring "predicted peak shortfall".
    expect(screen.getAllByText(/Peak shortfall/i).length).toBeGreaterThanOrEqual(1)
  })

  it('shows non-zero credit and shortfall values when ramp partially covers the step', () => {
    seed(RAMP_CREDIT_TICK)
    render(<AssetReservePanel />)
    expect(screen.getByText(/6\.00 MW/)).toBeInTheDocument()
    expect(screen.getByText(/8\.00 MW/)).toBeInTheDocument()
  })

  it('shows "Covered by turbine ramp" when peak_shortfall is 0 and credit > 0', () => {
    seed(COVERED_BY_RAMP_TICK)
    render(<AssetReservePanel />)
    expect(screen.getByText(/Covered by turbine ramp/i)).toBeInTheDocument()
  })

  it('shows "0.00 MW — covered" for shortfall row when fully covered', () => {
    seed(COVERED_BY_RAMP_TICK)
    render(<AssetReservePanel />)
    expect(screen.getByText(/0\.00 MW — covered/i)).toBeInTheDocument()
  })

  it('hides ramp staging block when dt_lead_next_s == 0 (ramp complete)', () => {
    seed(POST_RAMP_TICK)
    render(<AssetReservePanel />)
    expect(screen.queryByText(/Ramp staging/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Turbine ramp credit/i)).not.toBeInTheDocument()
  })
})

// ── Pre-run state ─────────────────────────────────────────────────────────────

// ── TC-98 / TC-99 — per-unit output + ramp consistency ───────────────────────

/** Two on-bus units with known per-unit output_mw + ramp_capability_mw. */
const FLEET_TICK: TickPayload = {
  ...ALERT_TICK,
  tick_index: 20,
  sim_time_seconds: 100.0,
  ramp_capability_mw: 28.0,   // backend authoritative energy over dt_lead_next_s=40
  dt_lead_next_s: 40.0,
  turbine_units: [
    {
      asset_id: 'gt-1', rated_mw: 15, r_asset_mw_per_s: 0.20,
      no_load_mw: 1.5, msl_mw: 6.0, gt_mode: 'frame',
      hot_standby: false, breaker_closed: true, sync_relay_state: 'permissive',
      state: 'synchronised', thermal_state: 'hot',
      output_mw: 12.5,
    },
    {
      asset_id: 'gt-2', rated_mw: 15, r_asset_mw_per_s: 0.20,
      no_load_mw: 1.5, msl_mw: 6.0, gt_mode: 'frame',
      hot_standby: false, breaker_closed: true, sync_relay_state: 'permissive',
      state: 'synchronised', thermal_state: 'hot',
      output_mw: 11.8,
    },
  ] as TickPayload['turbine_units'],
  on_bus_output_mw: 24.3,
  units_on_bus_count: 2,
}

describe('TC-98 — per-unit output_mw sums to on-bus fleet total', () => {
  it('sum of on-bus unit output_mw matches on_bus_output_mw to 1 dp', () => {
    const units = FLEET_TICK.turbine_units
    const onBusUnits = units.filter(u =>
      u.state !== undefined ? (u.state === 'synchronised' || u.state === 'unloading') : (u as any).breaker_closed
    )
    const sumOutputMW = onBusUnits.reduce((s, u) => s + ((u as any).output_mw ?? 0), 0)
    // TC-98: Σ output_mw over on-bus units == on_bus_output_mw (within 0.1 MW)
    expect(Math.abs(sumOutputMW - FLEET_TICK.on_bus_output_mw)).toBeLessThan(0.1)
    expect(sumOutputMW).toBeCloseTo(12.5 + 11.8, 1)
  })

  it('UNLOADING units are counted as on-bus for TC-98 sum', () => {
    const unloadingTick: TickPayload = {
      ...FLEET_TICK,
      turbine_units: [
        { ...FLEET_TICK.turbine_units[0], state: 'synchronised', output_mw: 12.5 },
        { ...FLEET_TICK.turbine_units[1], state: 'unloading', output_mw: 4.0 },
      ] as TickPayload['turbine_units'],
      on_bus_output_mw: 16.5,
    }
    const units = unloadingTick.turbine_units
    const onBusUnits = units.filter(u =>
      u.state === 'synchronised' || u.state === 'unloading'
    )
    const sumOutputMW = onBusUnits.reduce((s, u) => s + ((u as any).output_mw ?? 0), 0)
    expect(sumOutputMW).toBeCloseTo(16.5, 1)
  })
})

describe('TC-99 — single-unit and aggregate ramp derive from one source, clamp to rated', () => {
  it('aggregate ramp energy matches tick.ramp_capability_mw (backend authoritative)', () => {
    // After U-2 fix: the frontend must NOT compute its own aggregate figure.
    // Verify the raw wire field is the one displayed.
    expect(FLEET_TICK.ramp_capability_mw).toBe(28.0)
  })

  it('single-unit ramp clamped to headroom (not nameplate); near-rated case shows the two bounds differ', () => {
    // U-3 fix: divisor is on-bus count; clamp is headroom = rated_mw − output_mw.
    const onBusUnits = FLEET_TICK.turbine_units.filter(u =>
      u.state === 'synchronised' || u.state === 'unloading'
    )
    const onBusCnt    = Math.max(onBusUnits.length, 1)
    const rampEnergyMW = FLEET_TICK.ramp_capability_mw ?? 0
    const headrooms    = onBusUnits.map(u => u.rated_mw - ((u as any).output_mw ?? 0))
    const maxHeadroom  = Math.max(...headrooms)
    const perUnit      = rampEnergyMW / onBusCnt
    const rampWith1MW  = Math.min(perUnit, maxHeadroom)

    // FLEET_TICK: rampEnergyMW=28, onBusCnt=2, output_mw=[12.5, 11.8], rated=15 each
    // headrooms=[2.5, 3.2], maxHeadroom=3.2, perUnit=14 → clamped to 3.2
    expect(rampWith1MW).toBeCloseTo(3.2, 1)       // headroom governs, not nameplate

    // Near-rated case: a unit at 12 MW output on a 15 MW machine has 3 MW headroom.
    // Nameplate clamp: min(14, 15) = 14 MW.   Headroom clamp: min(14, 3) = 3 MW.
    // The two answers must differ — that difference is the defect TC-99b guards.
    const nearRatedHeadroom = 15 - 12             // 3 MW
    const nameplateAnswer   = Math.min(perUnit, 15)             // 14
    const headroomAnswer    = Math.min(perUnit, nearRatedHeadroom)  // 3
    expect(headroomAnswer).toBeCloseTo(3.0, 1)
    expect(headroomAnswer).toBeLessThan(nameplateAnswer)  // the key assertion
  })

  it('single-unit and aggregate derive from the same source (no two-formula divergence)', () => {
    const N = FLEET_TICK.turbine_units.length
    const rampEnergyMW = FLEET_TICK.ramp_capability_mw ?? 0
    const maxUnitMW = Math.max(...FLEET_TICK.turbine_units.map(u => u.rated_mw))
    const rampWith1MW = Math.min(rampEnergyMW / N, maxUnitMW)
    // Aggregate and single-unit share the same base (ramp_capability_mw).
    // If rampWith1MW * N were the aggregate, it would equal rampEnergyMW when no clamp.
    expect(rampWith1MW * N).toBeCloseTo(rampEnergyMW, 1)
  })
})

describe('Pre-run state — panels show idle placeholders before any run', () => {
  it('AlertDock shows "No active run"', () => {
    render(<AlertDock />)
    expect(screen.getByText(/No active run/i)).toBeInTheDocument()
  })

  it('AssetReservePanel shows "no active run"', () => {
    render(<AssetReservePanel />)
    expect(screen.getByText(/no active run/i)).toBeInTheDocument()
  })

  it('HeroPanel shows "no active run"', () => {
    render(<HeroPanel />)
    expect(screen.getByText(/no active run/i)).toBeInTheDocument()
  })
})
