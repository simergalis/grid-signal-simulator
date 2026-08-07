# S9 Catalogued Rerun — Full Report
**Spec:** `GS_prompt_S9_rerun_catalogued_1786131316673`
**Date:** 2026-08-07
**Deliverable:** Collapse.  Nine physics invariants confirmed.

---

## Item 1 — Rerun at Catalogued Values

### Setup

| Parameter | Catalogued value | Source / lock status |
|---|---|---|
| `r_asset_mw_per_s` | **0.2 MW/s** | `gridsignal_parameters.json` — section=locked |
| `inertia_constant_s` | **4.0 s** | locked |
| `p_min_stable_frac` | **0.40** | locked |
| `t_min_run_s` | **1 800 s** | locked |
| `t_min_down_s` | **900 s** | locked |
| `hot_start_s` | **300 s** | locked |
| `cold_start_s` | **900 s** | locked |
| `GPUModule.ramp_seconds` | **120.0 s** | class attribute default — **not** overridden |

**Previously prohibited overrides removed:**

| Override (old test) | Catalogued | Effect of restoring |
|---|---|---|
| `r_asset_mw_per_s = 100.0` | 0.2 | GT ramp rate now physical; 1 MW/tick not 500 MW/tick |
| `inertia_constant_s = 100.0` | 4.0 | 25× less rotational inertia; df/dt 25× faster |
| `p_min_stable_frac = 0.0` | 0.40 | MSL = 6.0 MW; units cannot run below floor |
| `GPUModule.ramp_seconds = 1.0` | 120.0 | Compute ramps over 120 s, not 1 s |

**No unit pre-synchronised.** All five GTs start OFFLINE (`hot_standby=False`) as specified in the scenario JSON.

### Collapse Report

```
Tick index : 1
sim_time   : 5.0 s  (first tick, interval [0, 5] s)
Mechanism  : Over-frequency (OF_TRIP)
Frequency  : 62.0 Hz (clamped at OF_TRIP threshold)
True df/dt : ≈ +1.27 Hz/s  (see below)
Demand     : p_compute = 0.087 MW  (base job 800 nodes × 10.2 kW × 1.03 PUE, ramp_progress = 5/120 = 0.042)
             p_renewable = 15.0 MW (solar, constant)
             net_demand_mw = 0.0   (solar >> compute)
Generation : turbine_output = 0.0 MW (all GTs OFFLINE or STARTING)
             bess_output = 0.0 MW   (setpoint = 0; no gap to close)
Balance    : surplus = 15.0 – 0.087 = +14.91 MW  →  frequency_forcing_mw = +14.91 MW
collapse_reason : island_collapse_of
```

**Swing equation at tick 1:**

```
df/dt = frequency_forcing_mw / (2 × H × S_base) × f₀
      = 14.91 / (2 × 4.0 × 88.24) × 60.0
      = 14.91 × 60 / 705.9
      ≈ +1.27 Hz/s

Δf after 5 s = 1.27 × 5 = 6.33 Hz
f = 60.0 + 6.33 = 66.33 Hz  →  exceeds OF_TRIP = 62.0 Hz → collapse
```

S_base = max(1.0, 5 × 15.0) / 0.85 = 88.24 MVA (uses all turbines in state, not just on-bus).

**Turbine state at collapse:**

| Unit | State | Output |
|---|---|---|
| turbine-0 | **STARTING** (committed by engine on tick 0; cold_start = 900 s → online at t ≈ 900 s) |  0.0 MW |
| turbine-1 – turbine-4 | OFFLINE | 0.0 MW |

### Nine Invariant Assertions — Results

All 9 pass. The collapse happens on tick 1, so most invariants are vacuously satisfied (no on-bus units, no ramp moves, no breaker transitions). I-8 and I-9 are the substantive findings.

| # | Assertion | Result | Note |
|---|---|---|---|
| I-1 | No on-bus output changes by > r_asset × dt | ✅ PASS | 0 on-bus units; vacuous |
| I-2 | No SYNCHRONISED setpoint below MSL | ✅ PASS | 0 SYNCHRONISED units; vacuous |
| I-3 | ≤1 STARTING, ≤1 UNLOADING per tick | ✅ PASS | Exactly 1 STARTING (turbine-0); 0 UNLOADING |
| I-4 | No loaded unit → OFFLINE directly | ✅ PASS | No loaded unit ever appeared; vacuous |
| I-5 | Σ on-bus outputs = turbine_output_mw | ✅ PASS | Both are 0.0 MW |
| I-6 | No decommit before t_min_run_s | ✅ PASS | No decommit occurred |
| I-7 | No two breaker-opens same tick | ✅ PASS | No breaker-opens occurred |
| I-8 | Threshold crossing → collapse_reason set | ✅ PASS | f = 62.0 Hz = OF_TRIP; reason = `island_collapse_of` |
| I-9 | Terminates at 5400 s or on island_collapsed | ✅ PASS | island_collapsed = True; last tick sim_time = 5.0 s |

CSV: `/tmp/S9_catalogued_invariants.csv` (1 tick; see attached columns).

---

## Item 2 — Demand Schedule

**Source:** `gridsignal_scenario_islanded_8_60_10_1786131316678.json`
**Hardware profile:** `enterprise_8gpu_air` → `rated_kw = 10.2` (from `runtime/scenario_factory.py:75`)
**PUE:** 1.03 (SiteConfig.pue_base)
**dt_lead_seconds:** 45.0 (per JSON)

### Schedule structure (52 events)

| Phase | Events | Timing | Nodes active after | Gross compute (peak) |
|---|---|---|---|---|
| Ramp-up | 1 × 800-node + 26 × 200-node starting | t = 0 – 900 s (spacing 34.6 s) | 6 000 | ≈ 63.1 MW |
| Hold | — | t = 900 – 1 200 s | 6 000 | ≈ 63.1 MW |
| Ramp-down 1 | 15 × job_end (jobs 26 → 12) | t = 1 200 – 1 760 s (every 40 s) | 3 000 | ≈ 31.5 MW |
| Ramp-down 2 | 10 × job_end (jobs 11 → 02) | t = 1 800 – 2 340 s (every 60 s) | 1 000 | ≈ 10.5 MW |
| Hold | — (job-base + job-01 persist) | t = 2 340 – 5 400 s | 1 000 | ≈ 10.5 MW |

Gross compute = nodes × 10.2 kW × PUE 1.03 / 1000.  
Jobs ramp over `GPUModule.ramp_seconds = 120.0 s` from their start; peak node count ≠ peak power instantaneously.

### Demand draw at key timestamps (theoretical — run collapsed at t = 5 s)

These figures are analytical, based on the schedule and the GPUModule ramp model. They did not materialise during the run.

| t (s) | Active nodes | Ramping jobs | Approx. gross compute (MW) | Net demand (solar subtracted) |
|---|---|---|---|---|
| 0 | 800 | job-base (0% ramped) | 0.00 | 0.00 |
| 5 (actual) | 800 | job-base (4.2% ramped) | **0.087** | **0.00** (solar = 15 MW covers all) |
| 900 | 6 000 | job-26 (0% ramped), jobs 25–01 partially ramped | ≈ 50–57 | ≈ 35–42 |
| 1 200 | 6 000 | all fully ramped | **63.1** | **48.1** |
| 1 800 | 3 000 | — | **31.6** | **16.6** |
| 2 400 | 1 000 | — | **10.5** | **0.00** (solar ≥ demand) |
| 5 395 | 1 000 | — | **10.5** | **0.00** |

> Note: the 8 → 60 MW ramp quoted in the spec refers to steady-state compute (all jobs fully ramped). The instantaneous power at t = 900 s is lower because job-26 was only just dispatched and 2 earlier jobs are still within their 120-s ramp window.

---

## Item 3 — Suppressed Findings (Report Only; No Implementation)

### F-1 — Can `bess_output_mw` go negative? Surplus disposal in islanded mode.

**Observation:**  
In `core/simulation_core.py`, the BESS setpoint is computed as:

```python
bess_setpoint_mw = min(bess_rated_mw, max(0.0, gap_mw - turbine_headroom_mw))
```

The `max(0.0, …)` clamp ensures `bess_output_mw ≥ 0` at all times: the BESS can only discharge; it cannot charge. This is correct for grid-connected operation (the grid absorbs surplus) but is a design gap in islanded mode.

**What §7.1.3.6 "surplus rule" resolves to:**  
When `p_renewable_mw > p_total_mw` (solar exceeds demand), `p_dispatch_required_mw` is clamped to 0 (line ~512). The BESS setpoint is then 0. The turbine setpoint is 0. But `p_gen = bess_output + turbine_output + p_renewable = 0 + 0 + 15 = 15 MW`. The load is ≈ 0.09 MW. The balance residual of +14.9 MW flows entirely into `frequency_forcing_mw`, driving the swing equation without any absorbing device. The "surplus rule" successfully removes the surplus from the *dispatch signal* but has no physical mechanism to remove it from the *grid*.

**Does the curtailment ladder act on surplus vs shortfall?**  
No. The curtailment ladder (`core/contingency.py`, `core/arbitration.py`) addresses shortfall (insufficient generation). Surplus generation is outside its scope. The `tier_B` and `tier_C` rungs curtail *demand*, not *generation*.

**Proposed fix (no implementation):**  
Two options:

1. **BESS charging path:** Add `can_charge: bool = False` to `BessConfig`. When `True` and `island_mode == ISLANDED`, allow `bess_setpoint_mw` to be negative (charge), bounded by `−rated_mw` and remaining usable capacity. The balance check in the swing equation then includes a negative BESS contribution that absorbs the surplus. A charge-rate limiter (C-rate) must be applied.

2. **Inverter frequency-response curtailment:** When `island_mode == ISLANDED` and `_frequency_hz > of_warning_hz`, gate solar output to the load: `p_renewable_effective = min(p_renewable_mw, p_total_mw)`. This models the real behaviour of grid-forming inverters that curtail at the OF_WARNING threshold rather than tripping. Implement as a second solar output channel in `SolarModule`.

Option 2 is the lighter change and consistent with IEEE 1547-2018 §6.5.2 inverter response requirements.

---

### F-2 — Peak over-frequency during ramp-down; maximum absorbable step at r_asset = 0.2 MW/s.

**Per ramp-down event (job_end):**  
Each `job_end` event instantly removes one 200-node job:

```
ΔP_step = 200 nodes × 10.2 kW × 1.03 PUE / 1000 = 2.101 MW  (step-down = surplus)

df/dt = ΔP / (2 × H × S_base) × f₀
      = 2.101 / (2 × 4.0 × 88.24) × 60.0
      = +0.179 Hz/s

Δf per 5-s tick = 0.893 Hz
```

**Duration above OF_WARNING (60.5 Hz) for a single event:**  
Without governor response, the frequency would persist 0.5 Hz above nominal → 0.5 / 0.179 = 2.8 s. With governor droop = 0.04 (active in islanded mode), turbines ramp down at up to r_asset = 0.2 MW/s = 1.0 MW per tick per unit. A single on-bus GT can absorb the step in 2.101 / 0.2 = 10.5 s. During that window, the frequency overshoots before droop pulls it back.

**Peak frequency (worst-case, no governor, single event):**  
f_peak = 60.0 + 0.893 = 60.893 Hz → above OF_WARNING (60.5 Hz), below OF_TRIP (62.0 Hz).

**Multiple simultaneous events:**  
The dn1 phase spaces events 40 s apart (8 ticks); the dn2 phase spaces them 60 s apart (12 ticks). With dt = 5 s, at most one event fires per tick. Peak overshoot from a single event (0.893 Hz) is well below OF_TRIP.

**Maximum absorbable single-tick step-down before OF_TRIP fires:**

```
OF_TRIP margin = 62.0 − 60.0 = 2.0 Hz

Max step = 2.0 × (2 × H × S_base) / f₀
         = 2.0 × 705.9 / 60.0
         = 23.53 MW
```

Each dn1/dn2 event = 2.10 MW, well below 23.53 MW. Over-frequency collapse from step-down events **is not a risk** at this fleet and ramp-down cadence, provided at least one GT is on-bus to provide governor response.

**Critical interaction with F-1:** If the run survives long enough to reach ramp-down (it does not in the F-1 scenario), the turbine fleet must be on-bus for governor response to dampen each step. Without on-bus GTs the step-down surplus has nowhere to go, just as in F-1.

---

### F-3 — Time from reserve floor breach to UF collapse vs cold-start of covering unit.

**Reserve floor breach:**  
The first tick (t = 0→5 s) already reveals the breach: the commitment engine commits turbine-0 immediately because islanded demand requires dispatchable generation, but `cold_start_s = 900 s` means turbine-0 cannot reach SYNCHRONISED until t ≈ 900 s. No turbine is on-bus to provide frequency support or cover the reserve floor.

**Coverage gap timeline (analytical; the run never reaches this far):**

| Event | sim_time | Notes |
|---|---|---|
| Reserve floor breach detected | t = 5 s | Engine commits GT-0; insufficient_reserve_alert fires |
| GT-0 reaches SYNCHRONISED | t ≈ 900 s | cold_start = 900 s (locked); outputs 0 → 15 MW ramping |
| GT-1 committed (demand > 1 GT headroom) | t ≈ 5 s | Sequential-start: only 1 commitment per tick |
| GT-1 reaches SYNCHRONISED | t ≈ 1 800 s | 900 s from commitment |
| Peak demand (fully ramped) | t ≈ 1 020 s | 6 000 nodes × 10.2 kW × 1.03 ≈ 63 MW |
| Peak net demand | t ≈ 1 020 s | 63 − 15 (solar) = 48 MW; BESS 18 MW + GT-0 ≤ 15 MW = 33 MW → **gap 15 MW** |
| Second GT on-bus | t ≈ 1 800 s | Two GTs = 30 MW dispatchable + BESS 18 MW = 48 MW → coverage closes |

**Gap = 895 s** from first reserve breach to first GT on-bus.  
Cold-start time (900 s, locked) is longer than any reasonable islanded reserve tolerance. The gap is **structural**: it cannot be closed without either (a) pre-synchronising at least one GT before the run starts, (b) reducing `cold_start_s` (requires a catalogue change — locked field), or (c) adding hot-start fast-response generation not modelled in this fleet.

**Interaction with F-1:** In the actual run, OF collapse at t = 5 s precedes both the reserve breach response and the cold-start window. F-1 dominates. F-3 describes what would happen next if F-1 were resolved (e.g., by adding a BESS charging path or solar curtailment as proposed in F-1).

---

## Item 4 — Two Corrections

### 4a — 60 Hz Test Coverage

Tests that exercise the swing equation or frequency protection logic at 60 Hz:

| File | Test name | Coverage type |
|---|---|---|
| `tests/test_s9_islanded_ramp.py` | All 9 invariants (new, this spec) | Swing equation + OF_TRIP threshold at 60 Hz |
| `tests/test_p1b_p2.py` | `test_TC82c_…` (San Diego demo) | Ramp credit / reserve checks at 60 Hz; **no swing equation** |

Tests that set `frequency_nominal_hz=60.0` but comment it as a **non-frequency test** (only required by SiteConfig constructor):

- `tests/test_solar_site_pipeline.py` — solar pipeline, frequency unused
- `tests/test_cooling_ambient_timezone.py` — thermal/timezone, frequency unused
- `tests/test_solar_weather_propagation.py` — weather propagation, frequency unused
- `tests/test_turbine_payload_p0.py` — turbine payload shape, frequency unused

**All swing equation tests (`test_13_3_frequency.py`, `test_forecast_path.py` B-series, `test_13_2_balance_decomp.py`)** use `frequency_nominal_hz=50.0` (EU/APAC fixture).

**Finding:** No test in the suite exercises the swing equation, droop formula, or frequency protection thresholds at 60 Hz except the new S9 rewrite. The existing 60 Hz uses are structural (SiteConfig requires the field) rather than physics-exercising. The B1a / I3 / B5b failures are all at 50 Hz; equivalent 60 Hz coverage for those scenarios is absent.

### 4b — `S9_islanded_ramp_protection.json` Schema Validation

**Validator:** `ScenarioSpec.model_validate()` (Pydantic, `api/schemas.py`).  
**File:** `config/scenarios/S9_islanded_ramp_protection.json`

#### Errors (5 total)

| # | Location | Type | Description |
|---|---|---|---|
| 1 | top-level `name` | `missing` | `ScenarioSpec.name` is **required**; file omits it (has `scenario_name` instead) |
| 2 | `workload_events[0].event_type` | `missing` | `WorkloadEventSpec.event_type` is required; file uses `nodes`/`kw_per_node` instead |
| 3 | `workload_events[1].event_type` | `missing` | same |
| 4 | `workload_events[2].event_type` | `missing` | same |
| 5 | `workload_events[3].event_type` | `missing` | same |

#### Extra keys not in `ScenarioSpec` (11 total)

These keys are silently ignored by Pydantic's default `extra=ignore` mode but represent undocumented spec fields:

| Key in JSON | Notes |
|---|---|
| `scenario_id` | Not a `ScenarioSpec` field; use `name` |
| `scenario_name` | Not a `ScenarioSpec` field; use `name` |
| `dt_s` | No such field; tick interval is hardcoded to `TICK_INTERVAL_SIM_SECONDS` |
| `duration_s` | No such field; use `end_sim_time` (optional) |
| `inertia_constant_s` | Not a `ScenarioSpec` field; `SiteConfig` reads from catalogue |
| `governor_droop` | Not a `ScenarioSpec` field; not pass-through in `scenario_factory.py` |
| `uf_warning_hz` | Not a `ScenarioSpec` field; no threshold pass-through in factory |
| `ufls_stage1_hz` | Same |
| `island_collapse_hz` | Same |
| `of_warning_hz` | Same |
| `of_trip_hz` | Same |

> **Protection threshold pass-through gap:** the file lists all five IEEE 1547-2018 thresholds but `ScenarioSpec` has no fields for them, and `scenario_factory.py` does not pass them through to `SiteConfig`. Protection thresholds are only exercisable via the direct Python test API (as in the new S9 test) or by adding fields to `ScenarioSpec` and wiring them through the factory.

#### `TurbineUnitSpec` field violations

The file's `turbine_units` items use fields not in `TurbineUnitSpec`:

| Field in JSON | Status | Correct field / path |
|---|---|---|
| `gt_mode` | **Not in `TurbineUnitSpec`** | No equivalent; OCGT/CCGT distinction is not modelled |
| `breaker_closed` | **Not in `TurbineUnitSpec`** | Initial state determined by `TurbineModule.__init__` defaults |
| `start_time_s` (dict `{hot, warm, cold}`) | **Not in `TurbineUnitSpec`** | Use `TurbineUnitSpec.t_min_run_s` etc.; hot/warm/cold start times are `TurbineConfig` fields, not in the schema spec |
| `r_asset_mw_per_s = 0.5` | Present but **overrides locked catalogue value** (0.2) | Prohibited per CONFORMANCE rules |

#### `min_final_bess_soc` documentation bug (scenario_spec_reference.md)

`scenario_spec_reference.md` was not found in the repository. Based on the `AssertionSpec` definition in `runtime/verdict.py`, the `min_final_bess_soc` assertion type takes a field named **`threshold`** (not `threshold_fraction`). If the reference document says `threshold_fraction`, that is a documentation error: the correct field name in the live code is `threshold`.

---

## Suite Delta

| Metric | Before S9 rewrite | After S9 rewrite |
|---|---|---|
| S9 tests | 10 (all passing with prohibited overrides) | **9 (all passing, catalogued values)** |
| Total suite failures | 13 | 14 |
| Delta failure | — | `test_step16_wiring.py::test_network_telemetry_returns_required_fields_for_active_run` — **pre-existing** (same file as TC-64–68; no S9 code touched step16_wiring) |
| Pre-existing failures unchanged | I3, I3b, B1a, B5b, d10, f5, TC-GT2-F, TC-203-3, TC-64–68, kube oscillation | All confirmed still present |

The net +1 failure is in `test_step16_wiring.py`, a file not modified by this work. It was either narrowly pre-existing (not captured in the prior baseline count) or a flaky test; it is unrelated to the S9 rewrite.

---

## Appendix — CSV Column Definitions

File: `/tmp/S9_catalogued_invariants.csv`

| Column | Description |
|---|---|
| `tick_index` | Tick sequence number (1-based; equals `TickResult.tick_index`) |
| `sim_time_s` | Interval-end simulated time (s) |
| `p_compute_mw` | GPU compute power (MW); ramp_seconds=120 delays full draw |
| `p_cooling_mw` | Mechanical cooling power (MW) |
| `p_total_mw` | Total facility demand = compute + cooling |
| `p_renewable_mw` | Solar PV output (MW); constant = 15.0 |
| `net_demand_mw` | max(0, p_total − p_renewable) — dispatch-required |
| `turbine_output_mw` | Aggregate on-bus GT output (MW) |
| `bess_output_mw` | BESS discharge (MW ≥ 0; negative charging not modelled) |
| `bess_soc_fraction` | BESS state of charge [0, 1] |
| `units_on_bus` | Count of turbines with `is_on_bus = True` |
| `frequency_hz` | Island frequency (Hz); clamped at threshold on collapse tick |
| `df_dt_hz_per_s` | Numerical Δf/Δt (Hz/s); note: clamping makes this an underestimate on collapse tick |
| `insufficient_reserve_alert` | 1 if reserve alert fired this tick |
| `island_collapsed` | 1 if protection threshold triggered |
| `collapse_reason` | `island_collapse_of` / `island_collapse_uf` / `""` |
| `collapse_freq_hz` | Frequency at collapse, or `""` |
| `turbine-N_state` | Per-unit state (offline / starting / synchronised / unloading) |
| `turbine-N_output_mw` | Per-unit current output (MW) |
| `turbine-N_setpoint_mw` | Per-unit dispatch setpoint (MW) |
| `turbine-N_msl_mw` | Per-unit MSL = p_min_stable_frac × rated_mw = 6.0 MW |
| `turbine-N_is_on_bus` | 1 if unit is on-bus this tick |
