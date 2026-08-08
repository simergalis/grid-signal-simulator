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

  // Power terms (MW) — backward-compat wire keys preserved per GS-CHG-2026-08-08 §3.1
  p_compute_mw: number
  p_cooling_mw: number
  p_total_mw: number
  net_demand_mw: number       // p_total - p_renewable, clamped ≥ 0

  // GS-CHG-2026-08-08 Phase 2 — supply/served contract.
  // p_*_demand_mw  : wired to existing producer (same values as the compat fields above).
  // null fields    : no balance-solver producer in this release.
  // Null must render as "not modelled" in the UI, NOT as 0.00 or "—".
  p_compute_demand_mw:  number         // = p_compute_mw, producer: simulation_core
  p_compute_served_mw:  number | null  // no producer
  p_compute_unserved_mw: number | null // no producer
  p_cooling_demand_mw:  number         // = p_cooling_mw, producer: simulation_core
  p_cooling_served_mw:  number | null  // no producer
  p_cooling_unserved_mw: number | null // no producer
  p_demand_mw:          number         // = p_total_mw, producer: simulation_core
  p_served_mw:          number | null  // no producer
  p_unserved_mw:        number | null  // no producer
  p_generation_mw:      number          // GS-CHG-2026-08-08 successor Phase 1 — wired to simulation_core producer
  p_imbalance_mw:       number | null  // no producer
  turbine_output_mw: number
  bess_output_mw: number
  bess_setpoint_mw: number    // dispatch command before SoC/power clipping (B4 gate)
  bess_soc_fraction: number   // [0, 1]

  // Phase 4 (GS-DES-CFG-001 §Item-1): BESS fleet aggregates — broadcast per tick.
  // bess_rated_mw:   fleet aggregate rated power (Σ config.rated_mw across all units).
  //                  Config nameplate; NOT SOC-corrected.  Scale the output bar against this.
  // bess_usable_mwh: fleet aggregate usable energy (Σ config.usable_mwh across all units).
  //                  Source: config, NOT contingency_coverage.bess_usable_energy_mwh —
  //                  that figure is rewritten by SOC-corruption injection (run_manager.py:787–788)
  //                  and would put a fault value into a static spec row.
  // bess_unit_count: count of BESS units; lets a panel state whether an aggregate covers
  //                  one unit or several without reading a bess_units[] array.
  bess_rated_mw:   number  // FLEET aggregate — config nameplate rated power (MW)
  bess_usable_mwh: number  // FLEET aggregate — config usable energy (MWh), not fault-injected
  bess_unit_count: number  // count of BESS units in fleet

  // Phase 4 (GS-DES-CFG-001 §Item-1): thermal site parameters — broadcast per tick.
  // dt_thermal_seconds: thermal lag Δt_thermal (s) from SiteConfig — base, unscaled.
  // alpha_max:          base cooling fraction α_max from SiteConfig — base, unscaled.
  //                     Do NOT confuse with ambient_alpha_scale (already on wire):
  //                     that is the FACTOR applied to alpha_max during ambient stress.
  //                     Broadcast both so a panel can show the base AND the scaled product.
  dt_thermal_seconds: number  // base thermal lag Δt_thermal from SiteConfig (s)
  alpha_max:          number  // base cooling fraction α_max from SiteConfig (NOT × ambient_alpha_scale)
  // GS-DES-CFG-001 §Phase-6: two new wire fields.
  // bess_anchor_reserve_mw: anchor reserve on the grid-forming BESS unit (MW).
  //   IMPORTANT — LAYERING: the broadcast value is the CONFIGURED value on the
  //   grid-forming unit (BessConfig.p_anchor_reserve_mw), NOT the catalogue default.
  //   These legitimately differ when a scenario overrides p_anchor_reserve_mw:
  //   e.g. the San Diego demo broadcasts 2.0 MW while the catalogue locked value is 1.0 MW.
  //   This is by design — the broadcast reports what the plant is actually configured with.
  //   Falls back to the catalogue default when no grid-forming unit is present in the run.
  // design_peak_load_mw: declared design peak site load (MW) — NOT the observed run maximum.
  //   = peak_it_load_mw (node_count × kW × PUE_base / 1000) + rated_cooling_mw.
  //   0.0 when the factory cannot compute it (spec-path with no workload_events);
  //   frontend falls back to observed peak (labeled as such) when 0.
  bess_anchor_reserve_mw: number  // configured anchor reserve on grid-forming BESS (MW)
  design_peak_load_mw:    number  // declared design peak: peak IT load + rated cooling (MW)

  // Confidence band
  confidence_lower_mw: number
  confidence_upper_mw: number
  // Phase 11.1: queue-derived compute forecast (Section 4 formula).
  // Equals confidence.point_estimate_mw (bit-identical, test_F4 Python-level).
  // The header PREDICTED PEAK and Forecast Quality panel centre must both read
  // this field so the two displays agree (F4 criterion end-to-end).
  forecast_mw: number

  // Phase 13.2: balance decomposition — three independent channels.
  // sum(grid_exchange_mw + frequency_forcing_mw + asset_delivery_error_mw) == balance_residual_mw (D4).
  // grid_exchange_mw:          PCC flow; exactly 0 in islanded mode (D1). channel_source: derived.
  // frequency_forcing_mw:      dispatch-plan inertial pressure; 0 in grid-connected (D2). derived.
  //   Phase 13.3: THE ONLY swing-equation input. Frequency is driven by this channel alone.
  // asset_delivery_error_mw:   physical shortfall (turbine/BESS vs droop-adjusted setpoints); ~0 steady-state (D3).
  //   Phase 13.3: does NOT participate in the swing equation. Non-zero = delivery fault (diagnostic only).
  //   "Model error must not move frequency." Renamed from model_error_mw (Phase 13.2 addendum).
  grid_exchange_mw:          number
  frequency_forcing_mw:      number
  asset_delivery_error_mw:   number
  // Phase 13.4: setpoint/actual split.
  // model_error_mw: load-model bias observable (B1 — 0.0 in production runs).
  // binding_constraint: "bess_power_saturated" | null when BESS setpoint exceeds rated MW (B3).
  model_error_mw:            number
  binding_constraint:        string | null

  // Phase 13.3: live frequency measurement — 60 Hz nominal (WECC/SDG&E) ± swing-equation deviation.
  // Islanded: integrated each tick via frequency_forcing_mw (governor droop provides restoring force).
  // Grid-connected: held at site frequency_nominal_hz (grid is the reference; forcing term is 0).
  frequency_hz: number

  // §FP: Frequency protection outcome for this tick.
  // island_collapsed: true on the one tick where a protection threshold fires.
  //   The run manager halts after broadcasting this tick; no further ticks follow.
  // collapse_reason: which threshold fired.
  //   "island_collapse_uf" — frequency fell below island_collapse_hz (< 57.0 Hz on 60 Hz system).
  //   "island_collapse_of" — frequency rose above of_trip_hz (> 62.0 Hz on 60 Hz system).
  //   null on all non-collapsed ticks.
  // collapse_tick_index: tick_index at which the collapse was detected (null if not collapsed).
  // collapse_frequency_hz: frequency frozen at the trip threshold (null if not collapsed).
  island_collapsed:      boolean
  collapse_reason:       string | null
  collapse_tick_index:   number | null
  collapse_frequency_hz: number | null

  // Data quality
  data_quality_tags: string[]  // DataQualityTag values

  // Alerts
  insufficient_reserve_alert: boolean
  checkpoint_states: Record<string, string>

  // Step 7 additions — required by dashboard panels
  p_renewable_mw: number         // ForecastChart 4th trace
  // §INV-CURT: MW of solar curtailed this tick by frequency-response inverter logic.
  // Proportional between of_warning_hz (0%) and of_trip_hz (100%), islanded only.
  // 0 in grid-connected mode, when thresholds are unset, or when f ≤ of_warning_hz.
  p_renewable_curtailed_mw: number
  bess_bridging_seconds: number  // AssetReservePanel; 86400 = "full reserve"
  // Turbine ramp credit / peak shortfall — staging breakdown for AssetReservePanel.
  // Both are 0.0 when no STARTING ramp is in-flight (dt_lead_next_s === 0).
  // turbine_ramp_credit_mw: MW already covered by turbine ramp rate × dt_lead.
  // peak_shortfall_mw:      MW the BESS must bridge (delta_p − credit, ≥ 0).
  turbine_ramp_credit_mw: number
  peak_shortfall_mw: number
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

  // Phase C D-05: per-unit on-bus aggregates (renamed from units_synchronised_count /
  // synchronised_output_mw).
  // units_on_bus_count: A = {synchronised, unloading} — both states are breaker-closed
  //   and producing.  OFFLINE / STARTING / OUT_OF_SERVICE are never in A.
  // on_bus_output_mw: Σ_{i∈A} p_i — includes UNLOADING units so per-unit rows always
  //   sum to the fleet hero value.  Falls back to breaker_closed when state is absent.
  units_on_bus_count: number
  on_bus_output_mw: number

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

  // §7.4 solar bank telemetry — stamped each tick from the renewable snapshot.
  // p_expected_mw: what all banks should produce at current measured POA.
  // banks_reporting: count of banks NOT in no_comms state.
  p_expected_mw:   number  // rated × (POA_measured / 1000) × temp_derate, summed over banks
  banks_reporting: number  // banks with live telemetry (not no_comms)

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

  // Step 10 §8.1: pre-staging two-phase fields.
  pre_staging_shift_mw:   number  // MW gap reduced (discharge phase)
  pre_staging_precool_mw: number  // extra load drawn to charge thermal store

  // AB3: fields present on TickResult previously absent from the wire dict.
  unrecognised_profile_alerts: string[]   // profile ids the engine could not resolve
  curtailment_proposal_tiers:  string[]   // curtailment tiers proposed this tick
  pms_fast_shed_active:        boolean    // PMS fast shed in effect this tick
  pms_order_conflict:          string | null  // detected PMS order conflict
  scada_commands_issued:       number     // SCADA commands issued this tick (TC-68)

  // SD-1: site identity — stamped from run-time config each tick.
  site_lat:          number | null
  site_lon:          number | null
  site_utc_offset_h: number | null
  site_name:         string

  // Phase E+: commitment engine last-decision summary — drives fleet modal commitment rows.
  // Always present after Phase E+ backend; action="hold" is the safe-sentinel default.
  commitment_block?: {
    action:                string         // "commit" | "decommit" | "hold"
    target_unit_id:        string | null
    reason:                string
    blocked_by:            string         // non-empty when action was held by R5 guard
    // committed_rated_mw: Σ rated_mw for SYNCHRONISED units — SYNCHRONISED only.
    // UNLOADING excluded (pinned at MSL, no headroom). Distinct from on_bus_output_mw
    // which includes UNLOADING; the two fields answer different questions.
    committed_rated_mw:    number
    // reserve_floor_mw: p_demand + largest committed unit (N-1 floor, from CommitmentDecision).
    reserve_floor_mw:      number
    reserve_satisfied:     boolean
    utilisation:           number
    pending_start_unit_id: string | null
  } | null

  // Phase 11.3: dispatch truthfulness.
  gt_setpoint_mw:      number  // total dispatch requirement handed to turbine fleet
  // balance_residual_mw REMOVED — Branch B (Phase pre-work).
  // D4 is now asserted inline in evaluate_tick(); the value is not broadcast.
  // Read the three decomposition channels (grid_exchange_mw, frequency_forcing_mw,
  // asset_delivery_error_mw) instead — they sum to the removed field.

  // Phase 1b: loading-layer outputs (stamped each tick).
  // sub_msl_surplus_mw > 0 when P_fleet < Σ msl_i for SYNCHRONISED units;
  //   fleet holds at the floor; in islanded mode surplus enters frequency_forcing_mw.
  // ramp_capability_mw: fleet ramp over runtime lead horizon (dt_lead_next_s).
  //   Replaces the Phase 0.5 display-level cap in turbineFleet.ts.
  // d4_balance_defect_mw: power balance accounting check; 0.0 in normal operation.
  sub_msl_surplus_mw:    number
  ramp_capability_mw:    number
  d4_balance_defect_mw:  number

  // Phase 11.6: cooling thermal lag.
  compute_inlet_temp_c: number  // inlet air temp from lagged cooling output

  // §174: stochastic step timing (kube path only).
  step_phase: number   // fractional position within current ML training step [0,1]
  step_kind:  string   // "training" | "checkpoint"

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

/**
 * Phase 10 §12.10 — session transport view from GET /api/session/transport.
 *
 * Reflects InstrumentPlane.modal_view() — all ms fields are null until the
 * ring buffer has at least one sample.
 *
 * samples.ws  : number of WS tick round-trip observations collected
 * samples.api : number of API round-trip observations collected
 */
export interface TransportView {
  measured:             boolean
  samples: {
    ws:  number
    api: number
  }
  ws_tick_latency_ms:    number | null   // p50
  ws_tick_p95_ms:        number | null   // p95
  ws_tick_p99_ms:        number | null   // p99
  api_roundtrip_ms:      number | null   // p50
  api_roundtrip_p95_ms:  number | null   // p95
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
  /** Phase 0 §0.1: prime-mover class — "frame" | "aero". Drives derived identity line. */
  gt_mode: string
  /** Phase 0 §0.2: commissioned but not synchronised to the AC bus (hot standby). */
  hot_standby: boolean
  /** Phase 0 §0.2: AC bus breaker closed (static spec, derived from hot_standby).
   *  Use isOnBus() in rendering code — it prefers the live `state` field (Phase 2)
   *  and falls back to this field for Phase 0 payloads without a state overlay. */
  breaker_closed: boolean
  /** Phase 0 §0.6: net output at no-load speed — distinct from MSL. */
  no_load_mw: number
  /** Phase 0 §0.6: minimum stable load (p_min_stable_frac × rated_mw). */
  msl_mw: number
  /** Phase 0 §0.2: synchro-check relay state.
   *  "permissive" — relay granted closure; unit is on the AC bus.
   *  "checking"   — relay active, matching V/f/θ before close (hot standby).
   *  "open"       — unit offline, not in sync sequence (Phase 1+). */
  sync_relay_state: string
  /** Phase C live state overlay — absent on Phase 0 payloads.
   *  "synchronised" | "unloading" → on bus (is_on_bus), delivering power.
   *  "starting" | "offline" | "out_of_service" → not on bus, zero output.
   *  Authoritative source for SYNC column and CURRENT MW distribution.
   *  Falls back to breaker_closed when absent. */
  state?: string
  /** Thermal state of the unit — "hot" | "warm" | "cold".
   *  Determines start-sequence duration.  Null when unit has never been started. */
  thermal_state?: string | null
  /** Phase 2 live overlay: algebraic MW output; non-zero for synchronised/unloading only. */
  output_mw?: number
  /** Phase 2 live: seconds remaining in start sequence — non-null only when state==="starting". */
  time_to_online_s?: number | null
  /** Phase 2 live: thermal-state-derived start phase label — non-null when starting. */
  start_phase?: string | null
  /** Phase 2 live: reason unit is out of service — null when not OOS. */
  out_of_service_reason?: string | null
  /** Phase E+: last setpoint commanded by the loading layer (before rate-clip). */
  setpoint_mw?: number
  /** Phase E+: unit has been within epsilon of setpoint for the levelled-off window. */
  levelled_off?: boolean
  /** Thermal start durations from TurbineConfig (CHOSEN, from catalogue). */
  hot_start_s?:  number
  warm_start_s?: number
  cold_start_s?: number
}

/** PMS wiring exposed in the Scenario Builder. */
export interface PmsConfigSpec {
  transition_mode: 'open_transition' | 'closed_transition'
}

/** Kubernetes GPU compute demand agent — drives stochastic load from gang-admission events. */
export interface KubeJobSpec {
  hardware_profile_id: string
  max_nodes: number   // peak cluster capacity (nodes)
  min_nodes: number   // idle-baseline nodes — cluster never fully drains
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
  /** Operator-facing "What this demonstrates" copy for the DemoBar. Empty = use hardcoded default. */
  demo_description?: string
  /** Default playback speed stored with the scenario. 0 = max-speed; >0 = sim-s per real-s. */
  default_playback_speed: number
  pms_config: PmsConfigSpec | null    // null = PMS disabled
  kube_job_spec?: KubeJobSpec | null  // null = no Kubernetes demand agent

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
