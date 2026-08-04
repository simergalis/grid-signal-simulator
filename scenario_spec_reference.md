# GridSignal — Scenario Upload Reference

A third party can create, inspect, and delete custom scenarios through the
GridSignal REST API.  This document covers everything needed to do so,
including the full field reference, validation rules, example payloads, and
the companion JSON Schema (`scenario_spec_schema.json`).

---

## Quick start

```bash
BASE_URL="https://<your-gridsignal-host>"

# 1. Create a scenario
curl -s -X POST "$BASE_URL/scenarios" \
  -H "Content-Type: application/json" \
  -d @my_scenario.json

# → {"scenario_id": "scen-abc123", "name": "My Scenario", "c_rate_warnings": []}

# 2. List all scenarios
curl -s "$BASE_URL/scenarios"

# 3. Fetch a scenario by ID
curl -s "$BASE_URL/scenarios/scen-abc123"

# 4. Update a scenario
curl -s -X PUT "$BASE_URL/scenarios/scen-abc123" \
  -H "Content-Type: application/json" \
  -d @my_scenario_v2.json

# 5. Delete a scenario
curl -s -X DELETE "$BASE_URL/scenarios/scen-abc123"
```

### Authentication

The `/scenarios` endpoints **do not require authentication** — they accept
requests from any origin without a session or API key.  Admin-only endpoints
(user management, bootstrap) are separate (`/api/admin/*`) and do require an
`X-Admin-Key` header.

---

## Endpoints

| Method | Path | Description | Success code |
|--------|------|-------------|-------------|
| `POST` | `/scenarios` | Create a new scenario | `201` |
| `GET` | `/scenarios` | List all scenarios (name + ID only) | `200` |
| `GET` | `/scenarios/{id}` | Full scenario detail + spec | `200` |
| `PUT` | `/scenarios/{id}` | Replace a scenario's spec | `200` |
| `DELETE` | `/scenarios/{id}` | Delete a scenario | `204` |

### Create response

```json
{
  "scenario_id": "scen-abc123",
  "name": "My scenario name",
  "c_rate_warnings": []
}
```

`c_rate_warnings` lists any BESS units whose C-rate falls outside the 0.25–4.0 C
physical range.  This is informational only — out-of-range values are accepted.

---

## Minimal valid payload

Only three fields are required.  Every other field has a default.

```json
{
  "name": "My first scenario",
  "bess_units": [
    {
      "asset_id": "bess-0",
      "rated_mw": 5.0,
      "usable_mwh": 2.5,
      "grid_forming": true
    }
  ],
  "turbine_units": [
    {
      "asset_id": "turbine-0",
      "rated_mw": 10.0
    }
  ]
}
```

---

## Realistic example — scripted workload

```json
{
  "name": "600-node ML training run",
  "description": "Enterprise GPU cluster ramping to 6.3 MW; BESS bridges early shortfall.",
  "bess_units": [
    {
      "asset_id": "bess-0",
      "rated_mw": 5.0,
      "usable_mwh": 2.0,
      "initial_soc_fraction": 0.95,
      "grid_forming": true
    }
  ],
  "turbine_units": [
    { "asset_id": "turbine-0", "rated_mw": 10.0, "r_asset_mw_per_s": 0.2 },
    { "asset_id": "turbine-1", "rated_mw": 10.0, "r_asset_mw_per_s": 0.2,
      "hot_standby": true }
  ],
  "workload_events": [
    {
      "event_id": "evt-start",
      "job_id": "job-1",
      "event_type": "starting",
      "timestamp": 0.0,
      "node_count": 600,
      "hardware_profile_id": "enterprise_8gpu_air"
    },
    {
      "event_id": "evt-end",
      "job_id": "job-1",
      "event_type": "job_end",
      "timestamp": 240.0
    }
  ],
  "dt_lead_seconds": 30.0,
  "solar_rated_mw": 2.0,
  "irradiance_steps": [[0.0, 1.0], [150.0, 0.4]],
  "end_sim_time": 300.0,
  "island_mode": true,
  "load_config": {
    "f_compute": 0.72,
    "p_comm_ratio": 0.55,
    "phase_coherence": 0.85
  },
  "assertions": [
    { "check": "no_insufficient_reserve_alert" }
  ]
}
```

---

## Field reference

### `ScenarioSpec` — top level

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `name` | string | — | **yes** | Display name (non-empty) |
| `description` | string | `""` | no | Free-text description |
| `bess_units` | `BessUnitSpec[]` | — | **yes** | At least one BESS unit |
| `turbine_units` | `TurbineUnitSpec[]` | — | **yes** | At least one turbine |
| `workload_events` | `WorkloadEventSpec[]` | `[]` | no | Scripted GPU/solar events |
| `hardware_profile_id` | string | `"enterprise_8gpu_air"` | no | Default profile for events without an explicit one |
| `dt_lead_seconds` | float [0, 300] | `30.0` | no | Advance warning time for `starting` events (s). `solar_step` always uses 0. |
| `solar_rated_mw` | float ≥ 0 | `0.0` | no | Peak solar capacity (MW) |
| `irradiance_steps` | `[float, float][]` | `[[0.0, 1.0]]` | no | Zero-order-hold irradiance profile. Each entry is `[sim_time_s, fraction_0_to_1]`. |
| `island_mode` | bool | `true` | no | Run in islanded grid-forming mode |
| `pue_base` | float [1.0, 2.0] | `1.03` | no | Power Usage Effectiveness baseline |
| `end_sim_time` | float [60, 86400] | `300.0` | no | Simulation end time (s) |
| `dt_thermal_seconds` | float [0, 300] | `90.0` | no | Engine thermal delay before cooling ramp (s) |
| `plant_dt_thermal_seconds` | float\|null | `null` | no | Plant override for thermal delay; `null` = linked to engine value |
| `alpha_max` | float [0, 1] | `0.20` | no | Engine max cooling fraction |
| `plant_alpha_max` | float\|null | `null` | no | Plant override; `null` = linked |
| `tau_seconds` | float [1, 120] | `20.0` | no | Engine cooling time-constant (s) |
| `plant_tau_seconds` | float\|null | `null` | no | Plant override; `null` = linked |
| `anchor_reserve_pct` | float [0, 20] | `0.0` | no | Anchor reserve as % of grid-forming BESS rated MW. 0 = use 1.0 MW default. |
| `band_pct_calibrated` | float [0, 15] | `0.0` | no | Confidence band ±% for reserve check. 0 = disabled (point-estimate only). |
| `band_mult_uncalibrated` | float [1, 4] | `2.0` | no | Reserve-band multiplier for uncalibrated sites |
| `band_mult_unmapped_hw` | float [1, 4] | `1.5` | no | Reserve-band multiplier for unmapped hardware profiles |
| `calibrated` | bool | `false` | no | Treat site as calibrated (enables curtailment ladder) |
| `solar_origin_utc_hour` | int [0,23]\|null | `null` | no | Fix the UTC hour for solar forecast generation. Use `20` for 12:00 PST. |
| `assertions` | `AssertionSpec[]` | `[]` | no | Pass/fail checks evaluated at run end |
| `fabric_scenario_id` | string\|null | `null` | no | ID of an S1–S8 fabric stress scenario JSON (e.g. `"S2_checkpoint_hotspot"`) |
| `pre_staging_config` | `PreStagingConfigSpec`\|null | `null` | no | Thermal load-shifting pre-staging engine |
| `pms_config` | `PmsConfigSpec`\|null | `null` | no | Simulated Power Management System |
| `procurement_config` | `ProcurementConfigSpec`\|null | `null` | no | Grid procurement / non-firm import layer |
| `maintenance_config` | `MaintenanceConfigSpec`\|null | `null` | no | Prescriptive maintenance layer |
| `ramp_relaxation_config` | `RampRelaxationConfigSpec`\|null | `null` | no | Adaptive ramp relaxation engine |
| `kube_config` | `KubeConfigSpec`\|null | `null` | no | Autonomous Kubernetes gang-admission demand simulator (replaces `workload_events`) |
| `load_config` | `LoadProfileConfigSpec`\|null | `null` | no | Compute vs allreduce phase variation for scripted-event scenarios. Ignored when `kube_config` is set. |
| `cluster_gen_config` | `ClusterGenConfigSpec`\|null | `null` | no | LLM-driven cluster arrival timeline generator |
| `stressor_gen_config` | `StressorGenConfigSpec`\|null | `null` | no | LLM-driven fault/stressor timeline generator |
| `param_sampling_config` | `ParamSamplingConfigSpec`\|null | `null` | no | Per-run seeded physics-parameter sampling |
| `telemetry_corruption_config` | `TelemetryCorruptionConfigSpec`\|null | `null` | no | Pre-generated telemetry corruption schedule |
| `ambient_steps` | `[float,float,float][]` | `[]` | no | Pre-generated weather timeline. **Do not set** — populated automatically by the engine. |
| `generation_block` | `GenerationBlock`\|null | `null` | no | Generator metadata. **Do not set** — populated at run start. |

---

### `BessUnitSpec`

**Validation:** at most one unit per scenario may have `grid_forming: true`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `asset_id` | string | — | **Required.** Unique identifier within the scenario |
| `rated_mw` | float > 0 | — | **Required.** Peak discharge power (MW) |
| `usable_mwh` | float > 0 | — | **Required.** Usable energy capacity (MWh) |
| `initial_soc_fraction` | float [0.1, 1.0] | `0.95` | State of charge at t=0 |
| `grid_forming` | bool | `false` | True = this unit is the island-frequency anchor. Only one unit may be `true`. |

C-rate = `rated_mw / usable_mwh`. Values outside 0.25–4.0 C are accepted with a warning.

---

### `TurbineUnitSpec`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `asset_id` | string | — | **Required.** Unique identifier |
| `rated_mw` | float > 0 | `10.0` | Rated output (MW) |
| `r_asset_mw_per_s` | float > 0 | `0.2` | Ramp rate (MW/s) |
| `run_hours_h` | float ≥ 0 \| null | `null` | Operating hours counter (display only) |
| `hot_standby` | bool | `false` | Commissioned but not synchronised; excluded from dispatch and contingency ramp |

---

### `WorkloadEventSpec`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `event_id` | string | auto UUID | Unique event identifier |
| `job_id` | string | `""` | Job identifier — links `starting` and `job_end` events |
| `event_type` | string | — | **Required.** One of: `"starting"`, `"job_end"`, `"solar_step"`, `"unit_trip"` |
| `timestamp` | float ≥ 0 | — | **Required.** Sim time (s) when the event fires |
| `node_count` | int ≥ 0 | `0` | GPU node count for `starting` events |
| `hardware_profile_id` | string | `"enterprise_8gpu_air"` | Hardware profile for power formula |
| `renewable_shortfall_mw` | float ≥ 0 | `0.0` | Drop magnitude for `solar_step` events (MW) |

**Event type semantics:**
- `starting` — GPU job ramp begins; turbine staging fires `dt_lead_seconds` ahead.
- `job_end` — GPU job ends; load drops.
- `solar_step` — Renewable curtailment; staging fires immediately (dt_lead=0).
- `unit_trip` — Forces a turbine offline immediately. Set `job_id` to the turbine's `asset_id`.

---

### `AssertionSpec` (pass/fail checks)

Each element is one of four check types, discriminated on `"check"`:

#### `no_insufficient_reserve_alert`
Passes if no tick fires an insufficient-reserve alert.
```json
{ "check": "no_insufficient_reserve_alert" }
```

#### `alert_fires`
Passes if at least one tick fires an insufficient-reserve alert.
```json
{ "check": "alert_fires" }
```

#### `max_p_total_mw`
Passes if peak total load stays at or below the threshold.
```json
{ "check": "max_p_total_mw", "threshold_mw": 8.0 }
```

#### `min_final_bess_soc`
Passes if the BESS SoC at the final retained tick meets the minimum.
```json
{ "check": "min_final_bess_soc", "threshold_fraction": 0.20 }
```

---

### `LoadProfileConfigSpec`

Controls compute vs allreduce phase variation (tick-to-tick power oscillation).
All defaults reproduce the spec document behaviour.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `f_compute` | float [0,1] | `0.72` | Fraction of step period in compute phase |
| `p_comm_ratio` | float [0,1] | `0.55` | Relative power during allreduce (fraction of compute-phase power) |
| `tau_gpu_s` | float > 0 | `0.06` | GPU power transition lag (s) |
| `phase_coherence` | float [0,1] | `0.85` | Fleet phase coherence (0 = random per-node, 1 = perfectly synchronised) |
| `noise_sigma_fraction` | float [0, 0.1] | `0.005` | Per-tick noise as fraction of base draw |

---

### `KubeConfigSpec`

Activates the autonomous Kubernetes gang-admission demand simulator.
When set, `workload_events` is ignored.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hardware_profile_id` | string | `"enterprise_8gpu_air"` | Hardware profile for all admissions |
| `max_nodes` | int ≥ 1 | `1900` | Maximum cluster size |
| `min_nodes` | int ≥ 1 | `200` | Idle baseline (cluster never fully drains) |
| `mean_interarrival_s` | float [5, 3600] | `60.0` | Mean sim-seconds between gang admissions |
| `mean_job_nodes` | int ≥ 1 | `200` | Mean gang size |
| `job_node_std` | float ≥ 0 | `80.0` | Std deviation of gang size |
| `min_job_nodes` | int ≥ 1 | `50` | Minimum nodes per admission |
| `mean_job_duration_s` | float ≥ 10 | `300.0` | Mean job duration (s) |
| `min_job_duration_s` | float ≥ 5 | `30.0` | Minimum job duration (s) |
| `reorder_window_s` | float [0, 60] | `10.0` | Informer reorder buffer (s) |
| `ntp_jitter_s` | float [0, 10] | `2.0` | ±NTP jitter on event timestamps (s) |
| `headroom_threshold_mw` | float ≥ 0 | `2.5` | Headroom below which new admissions are held |
| `rng_seed` | int\|null | `null` | RNG seed for deterministic replay |
| `step_config` | `StepTimingConfigSpec`\|null | `null` | Stochastic step timing |
| `load_config` | `LoadProfileConfigSpec`\|null | `null` | Within-step load profile |

---

### `PmsConfigSpec`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `shed_priority_order` | string[] | `[]` | Job IDs to shed first (highest priority first) |
| `transition_mode` | `"open_transition"` \| `"closed_transition"` | `"open_transition"` | Grid reconnect mode |
| `open_transition_gap_mw` | float ≥ 0 | `2.0` | Coverage gap during open-transition reconnect (MW) |
| `open_transition_duration_s` | float > 0 | `5.0` | Duration of open-transition gap (s) |
| `fast_shed_duration_s` | float > 0 | `30.0` | Fast-shed event duration (s) |

---

### `PreStagingConfigSpec`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_shift_mw` | float [0, 50] | `1.0` | Max load-shift (MW) |
| `inlet_temp_low_c` | float [10, 30] | `18.0` | Cooling inlet temperature lower bound (°C) |
| `inlet_temp_high_c` | float [15, 35] | `24.0` | Cooling inlet temperature upper bound (°C) |
| `cooling_gain_c_per_mw_s` | float > 0 | `0.05` | Cooling temperature gain rate |
| `warmup_rate_c_per_s` | float ≥ 0 | `0.002` | Passive warmup rate (°C/s) |
| `initial_temp_c` | float [10, 35] | `21.0` | Initial cooling inlet temperature (°C) |
| `bms_override` | bool | `false` | BMS override flag |
| `thermal_soc_initial_mwh` | float ≥ 0 | `0.0` | Pre-charged thermal energy at run start (MWh) |
| `eta` | float (0, 1] | `0.9` | Charge-phase efficiency |

---

### `ProcurementConfigSpec`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `firm_available_mw` | float ≥ 0 | `20.0` | Firm import capacity (MW) |
| `reserved_available_mw` | float ≥ 0 | `10.0` | Reserved import capacity (MW) |
| `non_firm_available_mw` | float ≥ 0 | `3.0` | Non-firm import capacity (MW) |
| `price_curve_seed` | int ≥ 0 | `42` | RNG seed for price curve |

---

### `MaintenanceConfigSpec`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `asset_id` | string | `"turbine-0"` | Turbine to monitor |
| `nameplate_ramp_mw_per_s` | float > 0 | `0.2` | Nameplate ramp rate |
| `effective_ramp_mw_per_s` | float > 0 | `0.15` | Effective (degraded) ramp rate |
| `reserve_threshold_mw` | float ≥ 0 | `1.0` | Reserve contribution threshold |

---

### `RampRelaxationConfigSpec`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `reserve_threshold_mw` | float ≥ 0 | `2.0` | Reserve threshold for relaxation check |
| `baseline_ramp_cap_mw` | float > 0 | `5.0` | Baseline ramp capability cap (MW) |
| `baseline_ramp_duration_s` | float > 0 | `75.0` | Baseline ramp duration (s) |
| `adaptive_ramp_duration_s` | float > 0 | `30.0` | Adaptive ramp duration (s) |

---

### `StepTimingConfigSpec`

Controls stochastic step-event timing (used inside `KubeConfigSpec.step_config`).
All defaults reproduce the spec document behaviour.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `median_step_s` | float > 0 | `0.70` | Median inter-step gap (s) |
| `step_cv` | float [0,1] | `0.08` | Lognormal coefficient of variation |
| `tau_drift_s` | float > 0 | `300.0` | OU mean-reversion time (s) |
| `sigma_drift` | float ≥ 0 | `0.03` | OU diffusion magnitude |
| `p_straggler` | float [0,1] | `0.02` | Straggler injection probability |
| `straggler_scale` | float > 0 | `1.5` | Exponential straggler scale |
| `straggler_max` | float > 1 | `10.0` | Hard cap on straggler multiplier |
| `ckpt_interval_steps` | int ≥ 1 | `400` | Steps between checkpoint long-steps |
| `ckpt_jitter_steps` | int ≥ 0 | `40` | ±Uniform jitter on checkpoint interval |
| `ckpt_min_s` | float > 0 | `5.0` | Checkpoint step minimum duration (s) |
| `ckpt_max_s` | float > 0 | `30.0` | Checkpoint step maximum duration (s) |

---

### `ClusterGenConfigSpec`

LLM-driven cluster arrival generator. When set, the engine calls Mistral once
before the tick loop to generate a bursty, correlated workload timeline.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | string | `"plausible weekday on a 1900-node ML cluster"` | Natural-language prompt hint for the LLM |
| `hardware_profile_id` | string | `"enterprise_8gpu_air"` | Hardware profile for generated jobs |
| `max_nodes` | int ≥ 1 | `1900` | Maximum cluster size |
| `min_nodes` | int ≥ 1 | `200` | Idle baseline |
| `mean_interarrival_s` | float [5, 3600] | `60.0` | Mean arrival gap (s) |
| `mean_job_nodes` | int ≥ 1 | `200` | Mean job size |
| `job_node_std` | float ≥ 0 | `80.0` | Std deviation of job size |
| `min_job_nodes` | int ≥ 1 | `50` | Minimum job size |
| `mean_job_duration_s` | float ≥ 10 | `300.0` | Mean job duration (s) |
| `min_job_duration_s` | float ≥ 5 | `30.0` | Minimum job duration (s) |
| `rng_seed` | int\|null | `null` | RNG seed; `null` = time-seeded |
| `use_llm` | bool | `true` | `false` forces seeded-RNG fallback (no Mistral call) |

---

### `StressorGenConfigSpec`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | string | `"compound cloud-front and inverter-trip scenario"` | LLM prompt hint |
| `n_rng_events` | int [1, 20] | `3` | Number of stressor events to inject |
| `rng_seed` | int\|null | `null` | RNG seed |
| `use_llm` | bool | `true` | `false` forces seeded-RNG cloud-front fallback |

---

### `ParamSamplingConfigSpec`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `keys` | string[] | `["dt_thermal", "alpha_max", "tau"]` | Parameter keys to sample (from `gridsignal_parameters.json`) |
| `seed` | int\|null | `null` | RNG seed; `null` = time-seeded (non-reproducible) |
| `sample_plant_split` | bool | `true` | When true, split parameters draw independent plant and engine values |

---

### `TelemetryCorruptionConfigSpec`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `noise_sigma` | float [0, 0.5] | `0.0` | Multiplicative Gaussian noise 1-sigma (e.g. `0.05` = ±5%) |
| `dropout_prob` | float [0, 1) | `0.0` | Per-tick probability of record suppression |
| `max_stale` | int [0, 30] | `0` | Maximum staleness in ticks (0 = no staleness) |
| `seed` | int\|null | `null` | RNG seed |

---

## Hardware profiles

The currently supported `hardware_profile_id` value is:

| ID | Description |
|----|-------------|
| `enterprise_8gpu_air` | Standard 8-GPU air-cooled enterprise node (default) |

---

## Validation rules

1. `name` must be non-empty.
2. `bess_units` must have at least one entry.
3. `turbine_units` must have at least one entry.
4. At most **one** `BessUnitSpec` may have `grid_forming: true`.
5. `irradiance_steps` entries are zero-order-hold: `[sim_time_s, fraction]`. Fractions outside [0, 1] are accepted (e.g. cloud-front overshoot).
6. `kube_config` and `workload_events` are mutually exclusive in practice: when `kube_config` is set, `workload_events` is ignored by the engine.
7. `ambient_steps` and `generation_block` are engine-populated — do not set them in a submitted payload.

---

## Machine-readable schema

The companion file `scenario_spec_schema.json` is a fully-expanded JSON Schema
(Draft 2020-12) generated directly from the Pydantic `ScenarioSpec` model.
Feed it to any JSON Schema validator or code generator.

```bash
# Validate a payload against the schema (requires ajv-cli)
ajv validate -s scenario_spec_schema.json -d my_scenario.json
```
