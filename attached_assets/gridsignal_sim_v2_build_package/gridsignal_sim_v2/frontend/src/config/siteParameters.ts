/**
 * siteParameters.ts — Pure derivation helpers for site-wide physics quantities.
 *
 * GS-DES-CFG-001 v1.0 — frontend/src/config/siteParameters.ts
 *
 * Contract
 * --------
 * None of these functions return a hard-coded numeric constant.
 * When the required data is unavailable, they return null.
 * Callers MUST render the "not instrumented" state — never substitute a default.
 * A hard-coded constant is a default that never admits it is one; returning
 * null makes missing data visible instead of plausible.
 *
 * Phase 6 interim source
 * ----------------------
 * peakSiteLoadMW() returns the observed peak of (p_compute_mw + p_cooling_mw)
 * over run history.  This is the interim replacement for the PEAK_LOAD_MW = 23.95
 * constant until design_peak_load_mw is added to ScenarioSpec and broadcast.
 *
 * It MUST be labelled "observed this run" wherever it is displayed — it understates
 * early in a run (before the site has reached its demand peak), so an N−1 verdict
 * computed against it reads optimistic until the site has seen its peak demand.
 * Label: "observed peak this run"  (not "design peak" or "peak load").
 *
 * CFG-5 deferred
 * ---------------
 * dt_lead is a split parameter (engine vs. plant may diverge deliberately).
 * The frontend shows the engine value from tick.dt_lead_next_s and labels it.
 * No split-parameter rendering is implemented in this release.
 */

import type { HistoryPoint } from '../types'
import type { TurbineUnitSpec } from '../types'

// ── Peak site load ─────────────────────────────────────────────────────────────

/**
 * Return the observed peak total load (compute + cooling) over run history.
 *
 * Returns null when no history is available.
 * Label as "observed peak this run" — NOT "design peak" or "peak site load".
 *
 * This is the Phase 6 interim source for N−1 adequacy calculations.
 * It understates early in a run; the N−1 verdict is optimistic until the
 * site has reached its actual demand peak.
 */
export function peakSiteLoadMW(history: HistoryPoint[]): number | null {
  if (history.length === 0) return null
  let peak = 0
  for (const h of history) {
    const total = (h.p_compute_mw ?? 0) + (h.p_cooling_mw ?? 0)
    if (total > peak) peak = total
  }
  return peak > 0 ? peak : null
}

// ── Generation — derived from tick payload ────────────────────────────────────

/**
 * Return the fleet's maximum rated output (sum of all unit rated_mw).
 *
 * Returns null when no units are available.
 */
export function installedFleetMW(units: TurbineUnitSpec[]): number | null {
  if (!units || units.length === 0) return null
  return units.reduce((s, u) => s + u.rated_mw, 0)
}

/**
 * Return the fleet ramp rate in MW/s (sum of per-unit r_asset_mw_per_s).
 *
 * Returns null when no units are available.
 * This is the aggregate nameplate ramp; the loading-layer-authoritative figure
 * for a running simulation is tick.ramp_capability_mw (Phase 1b).
 */
export function fleetRampMWs(units: TurbineUnitSpec[]): number | null {
  if (!units || units.length === 0) return null
  return units.reduce((s, u) => s + u.r_asset_mw_per_s, 0)
}

/**
 * Return the first unit's rated_mw (nameplate per unit).
 *
 * Returns null when no units are available.
 * Only meaningful for homogeneous fleets (same rated_mw per unit).
 */
export function unitRatedMW(units: TurbineUnitSpec[]): number | null {
  if (!units || units.length === 0) return null
  return units[0].rated_mw
}

/**
 * Return the first unit's r_asset_mw_per_s.
 *
 * Returns null when no units are available.
 */
export function unitRampMWs(units: TurbineUnitSpec[]): number | null {
  if (!units || units.length === 0) return null
  return units[0].r_asset_mw_per_s
}

/**
 * Return the largest single unit's rated_mw in the fleet.
 *
 * Returns null when no units are available.
 * Used for N-1 adequacy: the contingency loss size equals the largest unit.
 */
export function largestUnitMW(units: TurbineUnitSpec[]): number | null {
  if (!units || units.length === 0) return null
  return Math.max(...units.map(u => u.rated_mw))
}

// ── MW closeable in lead window ───────────────────────────────────────────────

/**
 * MW closeable by a single unit's ramp rate in the given lead window.
 *
 * This is the derivation for the generation panel's "ramp capability in lead
 * window" metric.  Uses the first unit's r_asset_mw_per_s and the runtime
 * lead horizon (tick.dt_lead_next_s), not a hardcoded 45 s constant.
 *
 * Returns null when units or horizonS are not available.
 */
export function rampCapabilityMW(
  units: TurbineUnitSpec[],
  horizonS: number,
): number | null {
  const ramp = unitRampMWs(units)
  if (ramp === null || horizonS <= 0) return null
  const rated = unitRatedMW(units)
  // Cap at rated output — the ramp integral is bounded by nameplate.
  return rated !== null ? Math.min(ramp * horizonS, rated) : ramp * horizonS
}

// ── BESS ─────────────────────────────────────────────────────────────────────

/**
 * Return the BESS rated power from a BessUnitSpec array.
 *
 * Returns null when no BESS units are available.
 * The grid-forming unit's rated_mw is the figure used for bridging
 * (before anchor reserve deduction).
 */
export function bessRatedMW(bessUnits: Array<{ rated_mw: number }>): number | null {
  if (!bessUnits || bessUnits.length === 0) return null
  // Use the first (and typically only) grid-forming unit.
  return bessUnits[0].rated_mw
}

/**
 * Return the BESS usable energy from a BessUnitSpec array.
 *
 * Returns null when no BESS units are available.
 */
export function bessUsableMWh(bessUnits: Array<{ usable_mwh: number }>): number | null {
  if (!bessUnits || bessUnits.length === 0) return null
  return bessUnits.reduce((s, u) => s + u.usable_mwh, 0)
}
