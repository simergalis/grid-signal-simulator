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

  // W1c — thermal headroom (serialised by run loop before sink/broadcast).
  // Mirrors GET /thermal; guaranteed to agree because they share the same
  // _update_thermal_state() source and RunContext fields.
  rated_cooling_mw:   number  // rated capacity MW from factory config
  absorbable_mw:      number  // max(0, rated - current) before thermal limit
  time_to_limit_s:    number  // seconds until headroom = 0 (86400 = effectively ∞)
  approach_rate_mw_s: number  // MW/s rate of change (positive = load rising)

  // AE2 — per-unit turbine config (constant across ticks for a run).
  // Stamped from RunContext.turbine_unit_specs; empty array for contexts
  // without a spec (e.g. direct job-id path).  Drives the fleet modal.
  turbine_units: TurbineUnitSpec[]

  // Kubernetes demand agent metrics — null when kube_config is not active.
  // Non-null only on runs that have kube_config set in the ScenarioSpec.
  kube_metrics: KubeMetrics | null

  // Solar weather metadata — stamped from RunContext at each tick (constant
  // per run). Empty strings when solar is absent or run started via direct path.
  // "physics_estimate" when Mistral was unavailable; otherwise the Mistral label.
  solar_weather:    string
  solar_conditions: string
  // PROTO-32-AMB: ambient temperature — constant per run; 0.0 / 1.0 when absent.
  ambient_avg_c:       number  // average dry-bulb °C across the run window
  ambient_alpha_scale: number  // scale applied to site.alpha_max (>1 = hotter than nominal)

  // GT-1: §7.4 contingency coverage — quantitative N−1 gen-trip assessment.
  // null on legacy ticks that predate the engine (should not occur in normal runs).
  contingency_coverage: ContingencyCoverage | null

  // W2a: advisory telemetry — null when no AgentRegistry is active (LP-1 / no API keys).
  // Reflects proposals from ticks 0…t−1 (stamped before this tick's run_all()).
  advisory_telemetry: AdvisoryTelemetry | null

  // Phase 10: fabric model modal-view — null when FabricEngine not wired.
  // Six plant-plane fields + control decomposition + per-link utilisation map.
  fabric: FabricModalView | null

  // Phase 10 §12.10 — session transport instrument plane.
  // Monotonic nanosecond timestamp stamped by broadcast() in run_manager.py
  // immediately before the payload is sent over the WebSocket.  The frontend
  // echoes this value back to POST /api/session/observe-tick so the server
  // can compute the round-trip latency without clock-skew between client and
  // server monotonic clocks.
  //
  // Serialised as a STRING (not a number) to avoid JavaScript safe-integer
  // loss: monotonic_ns exceeds Number.MAX_SAFE_INTEGER (2^53) after ~104
  // days of host uptime.  Pass the raw string value straight through to the
  // POST body without numeric conversion.
  //
  // Absent on playback / headless test payloads.
  t_emit_ns?: string
}

/**
 * W2a §26 — live advisory agent telemetry stamped onto every tick payload.
 *
 * backend              : active LLM backend ("mistral" | "anthropic" | "deterministic") or null (LP-1)
 * agents_armed         : 6 if LLM configured + registry enabled, else 0
 * proposals_total      : cumulative proposals generated this run (all lifecycle states)
 * proposals_pending    : proposals currently awaiting human review
 * last_proposal_sim_time : sim_time of the most recent proposal; -1 if none yet
 * per_agent            : per-domain last proposal sim_time (-1 if that agent hasn't fired yet)
 */
export interface AdvisoryTelemetry {
  backend:                  string | null
  agents_armed:             number
  proposals_total:          number
  proposals_pending:        number
  last_proposal_sim_time:   number   // -1.0 = no proposals yet
  per_agent: {
    compute:     number
    storage:     number
    generation:  number
    renewable:   number
    thermal:     number
    calibration: number
  }
}

/**
 * GT-1 §7.4 — N−1 contingency coverage per tick.
 *
 * All intermediate results are preserved so display layers can inspect them
 * independently (TC-78: power and energy tests are separate).
 *
 * state:
 *   COVERED          — power ∧ energy ∧ closable
 *   COVERED_WITH_SHED — ¬closable, shed_required ≤ curtailable capacity
 *   CANNOT_CARRY     — shed_required exceeds curtailable capacity
 */
export interface ContingencyCoverage {
  state: 'COVERED' | 'COVERED_WITH_SHED' | 'CANNOT_CARRY'
  tripped_unit_id: string | null   // asset_id of the hypothetically tripped unit
  deficit_mw: number               // current output of the tripped unit (TC-77: output, not nameplate)
  headroom_surviving_mw: number    // Σ(rated − output) for surviving synchronized units
  r_surviving_mw_per_s: number     // Σ ramp rate for surviving synchronized units (TC-83: standby excluded)
  bess_bridging_available_mw: number  // anchor-adjusted BESS power ceiling (TC-79)
  bess_usable_energy_mwh: number   // current SoC across all BESS units
  power_test_passes: boolean       // bess_bridging ≥ deficit (TC-78: independent of energy test)
  energy_test_passes: boolean      // soc_mwh ≥ E_required (TC-78: independent of power test)
  closable: boolean                // surviving headroom ≥ deficit
  time_to_close_s: number          // deficit / r_surviving; 86400 when not closable
  shed_required_mw: number         // max(0, deficit − headroom_surviving) (TC-80)
  ride_through_s: number           // soc_mwh × 3600 / deficit; 86400 when no deficit
  // §7.5 header-strip figures
  dispatchable_mw: number          // online turbine rated + anchor-adj BESS bridging (TC-82: solar excluded)
  renewable_mw: number             // solar output as separate non-firm term (TC-81, TC-82)
}

export interface KubeMetrics {
  utilization: number       // admitted_nodes / max_nodes (or min_nodes/max_nodes when idle)
  node_count: number        // max(min_nodes, admitted_nodes) — drives GPUModule
  power_cap_active: boolean // true when headroom < headroom_threshold_mw
  headroom_mw: number       // turbine_headroom + bess_headroom from previous tick
  active_jobs: number       // gang-admitted workloads currently running
  admitted_nodes: number    // sum of node_count across active jobs (pre min_nodes floor)
}

/**
 * Phase 10 — fabric model modal-view fields.
 *
 * Six plant-plane fields (mirrors FabricModel.TickResult.modal_view()):
 *   topology_nodes          : total link count across all fabrics
 *   congested_links         : links with u ≥ 0.85 for ≥ 2 ticks
 *   bandwidth_headroom_frac : (total_headroom / total_capacity)
 *   packet_loss             : weighted-average packet loss probability
 *   retransmit_rate         : weighted-average retransmit rate
 *   control_latency_ms      : total NFR-2 control path latency
 *
 * Plus:
 *   control     : decomposed latency terms + breach flag
 *   discrimination : phase-discrimination verdict block
 *   link_utilisation : map of link_id → u (for heat strip; omits links with u=0)
 */
export interface FabricControlPath {
  l_fabric_ms:     number
  l_gateway_ms:    number
  l_retransmit_ms: number
  l_asset_ack_ms:  number
  breached:        boolean
  dominant_term:   string
  budget_ms:       number
}

export interface FabricDiscrimination {
  verdict:                      string   // checkpoint_corroborated | no_corroboration | not_applicable | unavailable
  phase_discrimination_available: boolean
  capability_tier:              string
  compute_quiesced:             boolean
  storage_elephant_sustained:   boolean
  precedence_note:              string
}

export interface FabricModalView {
  topology_nodes:          number
  congested_links:         number
  bandwidth_headroom_frac: number
  packet_loss:             number
  retransmit_rate:         number
  control_latency_ms:      number
  control:                 FabricControlPath
  discrimination:          FabricDiscrimination
  link_utilisation:        Record<string, number>   // link_id → u
}

export interface RunMeta {
  run_id: string
  playback_speed: number   // 0 = max-speed sentinel; >0 = simulated-s per real-s
  soc_floor_pct?: number   // operator-configured BESS lower display bound (default 10)
  soc_ceil_pct?: number    // operator-configured BESS upper display bound (default 95)
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
  /** Operating hours — null/absent when not tracked. Fleet modal shows in RUN h column. */
  run_hours_h?: number | null
}

/** PMS wiring exposed in the Scenario Builder. */
export interface PmsConfigSpec {
  transition_mode: 'open_transition' | 'closed_transition'
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
  pms_config: PmsConfigSpec | null    // null = PMS disabled

  // ── Physics parameters (gridsignal_parameters.json §2) ────────────────
  // Thermal response — split params have optional plant_ variants.
  // null/absent plant_ value = linked to engine value (default).
  dt_thermal_seconds?: number         // engine: thermal delay Δt_thermal (s)
  plant_dt_thermal_seconds?: number | null
  alpha_max?: number                  // engine: α_max cooling fraction
  plant_alpha_max?: number | null
  tau_seconds?: number                // engine: cooling time-constant τ (s)
  plant_tau_seconds?: number | null
  plant_pue_base?: number | null      // plant: PUE_base (engine = pue_base above)
  plant_dt_lead_seconds?: number | null  // plant: Δt_lead (engine = dt_lead_seconds)

  // Reserve check (INV-2)
  anchor_reserve_pct?: number         // % of BESS rated MW; 0 = use BessConfig default
  band_pct_calibrated?: number        // ±% of peak_shortfall; 0 = disabled
  band_mult_uncalibrated?: number     // × multiplier for uncalibrated sites
  band_mult_unmapped_hw?: number      // × multiplier for unmapped hardware

  // ── Site parameters ──────────────────────────────────────────────────────
  site_latitude?: number              // degrees N (default 32.72 = San Diego)
  site_utc_offset_h?: number          // UTC offset hours (default -8.0 = PST)
  ambient_temp_base_c?: number        // nighttime dry-bulb base °C (default 14.0)

  // ── Storage display bounds (display only — do not affect physics) ─────────
  soc_floor_pct?: number              // BESS usable SoC lower bound % (default 10)
  soc_ceil_pct?: number               // BESS usable SoC upper bound % (default 95)

  // ── Advisory agent tuning ─────────────────────────────────────────────────
  advisory_interval_s?: number        // advisory poll cadence in simulated seconds
  advisory_max_mw?: number            // TC-30 cap on any single proposal MW
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

// ---------------------------------------------------------------------------
// Step 9: Assertion specs + Results / playback types
// (must stay in sync with api/schemas.py and runtime/verdict.py)
// ---------------------------------------------------------------------------

export interface NoReserveAlertAssertion {
  check: 'no_insufficient_reserve_alert'
}
export interface AlertFiresAssertion {
  check: 'alert_fires'
}
export interface MaxPTotalAssertion {
  check: 'max_p_total_mw'
  threshold_mw: number
}
export interface MinFinalBessSocAssertion {
  check: 'min_final_bess_soc'
  threshold: number
}
export type AssertionSpec =
  | NoReserveAlertAssertion
  | AlertFiresAssertion
  | MaxPTotalAssertion
  | MinFinalBessSocAssertion

export interface AssertionResult {
  check: string
  status: 'PASS' | 'FAIL' | 'INCONCLUSIVE'
  detail: string
}

export interface RunResult {
  run_id: string
  scenario_id: string | null
  scenario_name: string
  completed_at: string       // ISO-8601
  overall: 'PASS' | 'FAIL' | 'INCONCLUSIVE'
  tick_count: number
  dropped_ticks: number
  gap_count: number
  assertions: AssertionResult[]
}

export interface TimeseriesRow {
  tick_index: number
  sim_time_seconds: number   // F5: interval-END; read from stored value, never re-derived
  p_compute_mw: number
  p_cooling_mw: number
  p_total_mw: number
  net_demand_mw: number
  turbine_output_mw: number
  bess_output_mw: number
  bess_soc_fraction: number  // [0, 1]
  confidence_lower_mw: number
  confidence_upper_mw: number
  insufficient_reserve_alert: boolean
  p_renewable_mw: number
  bess_bridging_seconds: number
  dt_lead_next_s: number
  bridging_basis: string
  gap_before: boolean        // true when tick_index jumps > 1 from the previous row
}

export interface TimeseriesResponse {
  run_id: string
  gap_count: number
  rows: TimeseriesRow[]
}
