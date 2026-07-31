---
name: Step 8 key decisions
description: IrradianceProfile zero-order hold; TC-33 delta_p PUE correction; SOLAR_STEP early-return in apply_workload_signal; plane-separation in build_run_context_from_spec.
---

## IrradianceProfile — zero-order hold (not linear interpolation)

`fraction_at()` uses zero-order hold: each sample's value holds from its
timestamp forward until the next sample's timestamp.  `[(0.0, 1.0), (30.0, 0.0)]`
gives 1.0 for t<30 and 0.0 for t≥30.  No interpolation.

**Why:** solar profiles have step changes (cloud edge, inverter trip); linear
interpolation would understate peak shortfall in exactly the window that matters.

**Tiebreak:** `_samples = sorted(samples)` sorts tuples element-by-element, so
for equal timestamps the HIGHER fraction value wins (it's last in sort order).
Document this but treat duplicate timestamps as unnecessary (just use one sample).

## TC-33 delta_p math — 6.3036 MW, not 6.12 MW

For 600 nodes at enterprise_8gpu_air (10.2 kW/node) with PUE 1.03:
  `600 × 10.2 × 1.03 / 1000 = 6.3036 MW` (PUE-adjusted)
NOT `600 × 10.2 / 1000 = 6.12 MW` (raw IT, misses PUE).

Solar rated_mw for TC-33 renewable must equal 6.3036 MW exactly to fully offset
the compute draw at t=0 (so the SOLAR_STEP at t=30 creates the full 6.3036 MW gap).

**Why:** staging calls `delta_p_mw = p_target_after - p_renewable_mw`; if solar
underestimates compute draw the renewable scenario doesn't match the compute scenario.

## SOLAR_STEP — early-return in apply_workload_signal

`WorkloadEventType.SOLAR_STEP = "solar_step"` added to core/models.py.
`WorkloadSignal.renewable_shortfall_mw: float = 0.0` added.

In `apply_workload_signal`: if `signal.event_type == WorkloadEventType.SOLAR_STEP`,
call `stage_for_predicted_step(delta_p_mw=signal.renewable_shortfall_mw, dt_lead_seconds=0.0, ...)`
and `return` immediately. The GPU plane is never touched.

**Why:** §7.1.1 — renewables carry no advance notice; dt_lead is always 0.
The early return ensures GPU modules don't misinterpret the event.

## Plane separation: build_run_context_from_spec

`runtime/scenario_factory.py` must NOT import from `api/`.
The API layer calls `spec.model_dump_json()` → `json.loads()` → passes a plain dict to
`build_run_context_from_spec(run_id, spec_data: dict, playback_speed)`.

This function converts `irradiance_steps: list[list[float]]` → `list[tuple[float, float]]`
with `[tuple(s) for s in irradiance_steps_raw]` (JSON arrays become lists, not tuples).

## Alert firing threshold in TC-33 tests

For alert tests to fire, the BESS must exhaust energy before gap_s elapses.
With a normal BESS (5 MW / 2.5 MWh, SoC=1.0) and gap_s=16.5s, max_sustainable
is ~2700s — no alert. Use `usable_mwh=0.01` (soc_mwh=0.01 MWh) to make alerts fire.

Arithmetic for test BESS (5 MW / 0.01 MWh, grid_forming=False):
  compute: peak_shortfall=3.3036 MW, max_sust = 0.01/3.3036 × 3600 = 10.9s < 16.5s → ALERT
  renewable: peak_shortfall=6.3036 MW, ceil=5.0, alloc=5.0, max_sust = 7.2s < 31.5s → ALERT

## Step 8 gate results

  pytest: 139/139 (101 pre-existing + 38 new)
  audit_tests: 13/13
  example_usage: 4/4 scenarios, alerts_seen=True
  plane separation: 8 core/ + 7 api/ clean
  tsc --noEmit: 0 errors
  vitest: 19/19
  vite build: clean
  load_test 2× PASS: wall 29.6s, compute p50 1772µs, delivery p50 3.77ms
  (4× FAIL pre-exists — hardware capacity, not Step 8 regression)
