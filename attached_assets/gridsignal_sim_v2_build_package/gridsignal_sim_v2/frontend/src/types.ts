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
}

export interface RunMeta {
  run_id: string
  playback_speed: number   // 0 = max-speed sentinel; >0 = simulated-s per real-s
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
