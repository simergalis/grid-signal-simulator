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

Only `name` is required. Every fleet and runtime field has a default, so a
minimal scenario can be created with a name alone.

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
| `bess_units` | `BessUnitSpec[]` | `[]` | no | BESS fleet |
| `turbine_units` | `TurbineUnitSpec[]` | `[]` | no | Gas-turbine fleet |
| `fuel_cell_units` | `FuelCellUnitSpec[]` | `[]` | no | Block-addressable fuel-cell fleet (Addendum G-1). When set, this supersedes the legacy aggregate `fuel_cell_*` fields. |
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
| `fabric_scenario_id` | string\|null | `null` | no | ID of a fabric regression scenario JSON (e.g. `"regression-test-checkpoint-storage-hotspot"`) |
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

**Validation:** multiple units may have `grid_forming: true`; runtime operation,
not scenario shape, determines whether an island has a live forming source.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `asset_id` | string | — | **Required.** Unique identifier within the scenario |
| `rated_mw` | float > 0 | — | **Required.** Peak discharge power (MW) |
| `usable_mwh` | float > 0 | — | **Required.** Usable energy capacity (MWh) |
| `initial_soc_fraction` | float [0.1, 1.0] | `0.95` | State of charge at t=0 |
| `grid_forming` | bool | `false` | True = this unit may form the island while actually producing. Multiple units may be configured. |

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
| `p_min_stable_frac` | float [0, 1] | `0.40` | Minimum stable output as a fraction of `rated_mw` |
| `t_min_run_s` | float ≥ 0 | `1800.0` | Minimum stable run duration used when `min_run_enabled` is true |
| `min_run_enabled` | bool | `true` | Enables the minimum-run guard |
| `t_min_down_s` | float ≥ 0 | `900.0` | Minimum down/cooling duration used when `min_down_enabled` is true |
| `min_down_enabled` | bool | `true` | Enables the minimum-down guard |
| `cold_start_s` | float > 0 \| null | `null` | Cold-start duration override; `null` uses the catalogue value (900 s) |
| `warm_start_s` | float > 0 \| null | `null` | Warm-start duration override; `null` uses the catalogue value (600 s) |
| `hot_start_s` | float > 0 \| null | `null` | Hot-start duration override; `null` uses the catalogue value (300 s) |
| `thermal_state` | `"hot"` \| `"warm"` \| `"cold"` \| null | `"cold"` | Initial thermal classification |
| `power_factor` | float (0, 1] \| null | `null` | Per-unit power-factor override |
| `inertia_constant_s` | float > 0 \| null | `null` | Per-unit inertia-constant override (s) |
| `droop_r` | float [0, 1] \| null | `null` | Per-unit governor-droop override |
| `valve_actuation_tc_s` | float > 0 \| null | `null` | Per-unit valve-actuation time-constant override (s) |
| `fuel_to_power_tc_s` | float > 0 \| null | `null` | Per-unit fuel-to-power time-constant override (s) |
| `max_instantaneous_load_step_mw` | float > 0 \| null | `null` | Maximum instantaneous load step accepted by this unit (MW) |
| `authority_tier` | `"autonomous"` \| `"confirm"` \| `"human_only"` \| null | `"autonomous"` | Dispatch authority for this unit |

When any start-duration override is supplied, the effective durations must
satisfy `hot_start_s < warm_start_s < cold_start_s`; omitted values use the
catalogue defaults in that comparison.

---

### `FuelCellUnitSpec` (Addenda G-1, G-2, and G Stage 3 Option C)

Fuel-cell capacity is derived as `block_rated_mw * block_count`. Do **not**
submit an independent `rated_mw` field. `initial_running_blocks +
initial_hot_standby_blocks` must not exceed `block_count`;
`hot_standby_floor_blocks` must not exceed `block_count`; and, when
`hot_standby` is false, `hot_standby_floor_blocks` must be zero. Start times
must satisfy `hot_start_s ≤ warm_start_s ≤ cold_start_s`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `asset_id` | non-empty string | — | **Required.** Unique fuel-cell unit identifier |
| `block_rated_mw` | float > 0 | — | **Required.** Nameplate output of one block (MW) |
| `block_count` | int ≥ 1 | — | **Required.** Number of blocks in the unit |
| `initial_running_blocks` | int ≥ 0 | `0` | Blocks initially producing power |
| `initial_hot_standby_blocks` | int ≥ 0 \| null | `null` | When omitted, every non-running block starts in hot standby |
| `requested_commit_rate_blocks_per_s` | float > 0 | `1.0` | Requested block commitment rate. `commit_rate_blocks_per_s` is accepted as a legacy input alias. |
| `decommit_rate_blocks_per_s` | float > 0 | `1.0` | Block decommitment rate |
| `cold_start_s` | float > 0 | `28800.0` | Cold-start duration (s) |
| `warm_start_s` | float > 0 | `14400.0` | Warm-start duration (s) |
| `hot_start_s` | float > 0 | parameter catalog (`5.0`) | Hot-start duration (s) |
| `controlled_cooling_s` | float > 0 \| null | `null` | Optional controlled-cooling duration (s) |
| `hot_standby` | bool | `true` | Whether this unit supports hot standby |
| `min_stable_frac` | float [0, 1] | `0.5` | Minimum stable output fraction |
| `hot_standby_floor_blocks` | int ≥ 0 | `0` | Minimum blocks retained in hot standby |
| `dispatch_mechanism` | `"discrete_blocks"` \| `"modulating"` \| `"hybrid"` | `"hybrid"` | Dispatch behavior of the array |
| `readiness_dwell_s` | float ≥ 0 | `0.0` | Required dwell time before a block is considered ready (s) |
| `grid_forming` | bool | `false` | A running, actually-producing array may form an island; provenance `site_specific`. |
| `power_factor` | float (0,1] | `1.0` | Per-array PF; reactive output is `P × tan(acos(PF))`; provenance `site_specific`. |
| `reactive_capability_mvar` | float ≥ 0 \| null | `null` | Optional Q capability; omitted derives the rated-MW/PF nameplate capability; provenance `proposed`. |
| `ieee_1547_category` | `1`, `2`, or `3` | `3` | IEEE 1547-2018 abnormal-operation category; controls ROCOF trip at 0.5/2/3 Hz/s; provenance `site_specific`. |
| `electrical_groups` | array | `[]` | Named contiguous groups with block counts. Names must be unique and meaningful; counts must sum exactly to `block_count`. Empty means one implicit all-block group |
| `beginning_of_life_heat_rate_btu_per_kwh` | float > 0 | `5811.0` | Beginning-of-life HHV heat rate; provenance `vendor_published` |
| `end_of_life_heat_rate_btu_per_kwh` | float > 0 | `7127.0` | End-of-life HHV heat rate; provenance `vendor_published` |
| `degradation_fraction` | float [0, 1] | `0.5` | Linear BOL-to-EOL interpolation fraction; provenance `site_specific` |
| `part_load_heat_rate_multiplier` | float > 0 | `1.0` | Heat-rate multiplier; provenance `proposed` |
| `gas_heating_value_btu_per_scf` | float > 0 | `1030.0` | Site gas heating value; provenance `site_specific` |
| `hot_standby_fuel_fraction` | float ≥ 0 | `0.10` | Fraction of rated fuel input burned in hot standby; provenance `proposed` |
| `gas_price_usd_per_mmbtu` | float ≥ 0 \| null | `5.0` | Placeholder site gas price; explicit null suppresses monetary estimates |
| `fuel_system` | object \| null | `null` | Optional G-2 common-manifold fuel model. Omit for G-1 ideal/infinite-volume supply compatibility. Defaults when supplied: supply/minimum/trip pressure 15/12/9.5 psig, volume 920 ft³, regulator/delivery time constants 2/3 s, droop 0.05, distribution loss 0.5 psi, utilisation maximum 0.85; `maximum_supply_flow_scfm: null` means unlimited. With unlimited supply, regulator flow lags the pre-staged command directly; with a finite cap it uses `min(qmax, qcmd + qmax*droop*(Ps-P)/Ps)`. |
| `provenance` | object | `{}` | Per-field source labels: `vendor_published`, `derived`, `proposed`, or `site_specific` |

In islanded mode a running fuel-cell block is a grid-forming source only when
its output is above the simulator epsilon. Fuel-cell reactive telemetry reports
achieved Q, apparent power, and loading; `island_reactive_balance_mvar` is only
the fuel-cell contribution because GridSignal does not model site-wide VAR
balance, voltage, or current. IEEE 1547-2018 ride-through telemetry identifies
the current continuous (58.8–61.2 Hz), mandatory (57.0–58.8 and 61.2–61.8 Hz),
or trip region. It trips producing blocks after `>62 Hz` for 0.16 s,
`>61.2 Hz` for 300 s, `<58.5 Hz` for 300 s, or `<56.5 Hz` for 0.16 s;
category ROCOF limits are 0.5, 2, and 3 Hz/s for categories 1, 2, and 3.

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
| `electrical_group_id` | string \| null | `null` | For a fuel-cell `unit_trip`, optionally targets one named electrical group |

**Event type semantics:**
- `starting` — GPU job ramp begins; turbine staging fires `dt_lead_seconds` ahead.
- `job_end` — GPU job ends; load drops.
- `solar_step` — Renewable curtailment; staging fires immediately (dt_lead=0).
- `unit_trip` — Forces a turbine or block-addressable fuel-cell unit offline immediately. Set `job_id` to its `asset_id`. For fuel cells, omit `electrical_group_id` to trip the whole array or provide a declared group name to trip only that contiguous board group. Tripped blocks enter `cold` with zero output.

---

### `AssertionSpec` (pass/fail checks)

Each element is one of the following check types, discriminated on `"check"`:

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
{ "check": "min_final_bess_soc", "threshold": 0.20 }
```

#### `pue_base_in_declared_range`
Passes when the runtime PUE base remains within the declared parameter range.
```json
{ "check": "pue_base_in_declared_range" }
```

#### `declining_fuel_cell_reserve_alert_fires`
Passes when a retained tick fires the fuel-cell block-array declining-reserve
alert. It is existential: missing evidence with timeseries gaps is inconclusive.
```json
{ "check": "declining_fuel_cell_reserve_alert_fires" }
```

#### `persistent_fuel_cell_deficit`
Passes when the commanded-minus-achieved fuel-cell deficit remains at the
expected value for a contiguous, timestamp-proven duration.
```json
{ "check": "persistent_fuel_cell_deficit", "expected_deficit_mw": 1.0, "duration_s": 60.0 }
```
`tick_seconds` defaults to `15.0` and `tolerance_mw` to `0.325`; duration is
proved from retained timestamps rather than the supplied cadence.

#### `peak_fuel_cell_array_output`
Passes when peak achieved block-array output is within the tolerance.
```json
{ "check": "peak_fuel_cell_array_output", "expected_mw": 3.25, "tolerance_mw": 0.325 }
```

#### `no_cold_warming_contingency_capacity`
Passes when cold and warming fuel-cell blocks contribute no contingency
capacity. `block_rated_mw` defaults to `0.325` and `tolerance_mw` to `1e-9`.
```json
{ "check": "no_cold_warming_contingency_capacity" }
```

#### `fuel_cell_commanded_and_achieved_reported`
Passes when every retained tick includes both fuel-cell command and achieved
output telemetry.
```json
{ "check": "fuel_cell_commanded_and_achieved_reported" }
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
4. Multiple BESS and fuel-cell arrays may be configured `grid_forming`. In
   islanded operation, a BESS former remains live while its inverter is
   energized and usable charge remains, including at zero net MW exchange. A
   fuel-cell former must have a running block producing real power. If neither
   remains, the run collapses with
   `island_collapse_no_grid_forming_source`.
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
