/**
 * types.ts — shared TypeScript interfaces matching the WS tick payload
 * produced by runtime/run_manager.py:_tick_result_to_dict().
 *
 * Keep this file in sync with the Python serialiser.  The canonical field
 * list is the dict returned by _tick_result_to_dict(); anything not in
 * that dict (e.g. wall_stamp_utc) is intentionally absent here.
 */

export interface TickPayload {
  run_id: string
  tick_index: number
  sim_time_seconds: number

  // Power terms (MW)
  p_compute_mw: number
  p_cooling_mw: number
  p_total_mw: number
  net_demand_mw: number       // p_total - p_renewable, clamped ≥ 0
  turbine_output_mw: number
  bess_output_mw: number
  bess_soc_fraction: number   // [0, 1]

  // Confidence band
  confidence_lower_mw: number
  confidence_upper_mw: number

  // Data quality
  data_quality_tags: string[]  // DataQualityTag values

  // Alerts
  insufficient_reserve_alert: boolean
  checkpoint_states: Record<string, string>

  // Step 7 additions — required by dashboard panels
  p_renewable_mw: number         // ForecastChart 4th trace
  bess_bridging_seconds: number  // AssetReservePanel; 86400 = "full reserve"
  dt_lead_next_s: number         // HeroPanel countdown; 0 = no active ramp

  // F2 addition — which demand figure is binding for bess_bridging_seconds
  bridging_basis: 'predicted_peak' | 'current_demand' | 'no_load'
}

export interface RunMeta {
  run_id: string
  playback_speed: number   // 0 = max-speed sentinel; >0 = simulated-s per real-s
}

// ---------------------------------------------------------------------------
// Step 8: Scenario Builder types (aligned with api/schemas.py)
// ---------------------------------------------------------------------------

export interface WorkloadEventSpec {
  event_id: string
  job_id: string
  event_type: string                  // WorkloadEventType value
  timestamp: number
  node_count: number
  hardware_profile_id: string
  renewable_shortfall_mw: number
}

export interface BessUnitSpec {
  asset_id: string
  rated_mw: number
  usable_mwh: number
  initial_soc_fraction: number        // [0.1, 1.0]
  grid_forming: boolean
}

export interface TurbineUnitSpec {
  asset_id: string
  rated_mw: number
  r_asset_mw_per_s: number
}

export interface ScenarioSpec {
  name: string
  description: string
  workload_events: WorkloadEventSpec[]
  hardware_profile_id: string
  dt_lead_seconds: number             // [0, 300] s
  bess_units: BessUnitSpec[]
  turbine_units: TurbineUnitSpec[]
  solar_rated_mw: number
  irradiance_steps: [number, number][] // zero-order hold [(t, fraction), ...]
  island_mode: boolean
  pue_base: number                    // [1.0, 2.0]
  end_sim_time: number                // [60, 86400] s
}

export interface ScenarioSummary {
  scenario_id: string
  name: string
  description: string
  created_at: string
}

export interface ScenarioDetailResponse {
  scenario_id: string
  name: string
  description: string
  created_at: string
  spec: ScenarioSpec
  c_rate_warnings: string[]
}

export interface CreateScenarioResponse {
  scenario_id: string
  name: string
  c_rate_warnings: string[]
}

/** A point in the chart history ring-buffer. */
export type HistoryPoint = {
  sim_time_seconds: number
  p_compute_mw: number
  p_cooling_mw: number
  p_total_mw: number
  p_renewable_mw: number
  confidence_lower_mw: number
  confidence_upper_mw: number
}
