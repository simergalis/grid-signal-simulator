---
name: Step 8 key decisions
description: IrradianceProfile zero-order hold; TC-33 delta_p PUE correction; SOLAR_STEP early-return; plane-separation in build_run_context_from_spec; TC-33 alert mechanics.
---

## IrradianceProfile — zero-order hold (not linear interpolation)

`fraction_at()` uses zero-order hold: each sample's value holds from its
timestamp forward until the next sample's timestamp.  `[(0.0, 1.0), (30.0, 0.0)]`
gives 1.0 for t<30 and 0.0 for t≥30.  No interpolation.

**Why:** solar profiles have step changes (cloud edge, inverter trip); linear
interpolation would understate peak shortfall in exactly the window that matters.

**Tiebreak:** `_samples = sorted(samples)` sorts tuples element-by-element, so
for equal timestamps the HIGHER fraction value wins (last in sorted order).
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

**Step 11 note:** SOLAR_STEP does NOT belong in WorkloadEventType long-term.
Solar irradiance is SCADA/EMS telemetry (§28), not scheduler intent.  Step 11
introduces a dedicated SCADA path; SOLAR_STEP should be retired then.
Do not use it as a precedent for routing non-workload signals through this enum.

**Why:** §7.1.1 — renewables carry no advance notice; dt_lead is always 0.
The early return ensures GPU modules don't misinterpret the event.

## Plane separation: build_run_context_from_spec

`runtime/scenario_factory.py` must NOT import from `api/`.
The API layer calls `spec.model_dump_json()` → `json.loads()` → passes a plain dict to
`build_run_context_from_spec(run_id, spec_data: dict, playback_speed)`.

This function converts `irradiance_steps: list[list[float]]` → `list[tuple[float, float]]`
with `[tuple(s) for s in irradiance_steps_raw]` (JSON arrays become lists, not tuples).

## TC-33 alert mechanics (power-ceiling guard, D11)

`_proportional_allocations` returns `demand × weight / total_weight` — NOT capped at
the ceiling. The cap is enforced inside `max_sustainable_seconds`: if
`discharge_mw > bridging_available_mw(island_mode)`, returns 0.0 (D11 guard).

This means:
  - Compute path (dt_lead=15s): already_ramped = 0.2 × 15 = 3.0 MW.
    peak_shortfall = 6.3036 - 3.0 = 3.3036 MW.
    3.3036 < BESS ceiling (5.0 MW) → max_sust = 2.5×3600/3.3036 = 2723s >> 16.5s → no alert.
  - Renewable path (dt_lead=0s): already_ramped = 0 MW.
    peak_shortfall = 6.3036 MW.
    6.3036 > BESS ceiling (5.0 MW) → max_sust returns 0.0 → fleet_min_s=0 < gap(31.518s) → ALERT.

THE TRAP: even with a fully-charged, large-capacity BESS, if peak_shortfall exceeds
the BESS rated_mw (power ceiling), max_sustainable_seconds returns 0.0 and the alert
fires. This is CORRECT — the BESS literally cannot deliver 6.3036 MW if rated at 5 MW.
The D11 guard is not a bug; it catches power-limited (not energy-limited) shortfalls.

TC-33 symmetry: delta_p_mw is identical (6.3036 MW) both paths, confirming A-fix.
The gap and alert status differ by construction (dt_lead 15s vs 0s changes already_ramped,
which changes peak_shortfall, which determines whether the power ceiling is exceeded).

## Alert firing threshold — usable_mwh=0.01 in tests

For test BESS alert scenarios: use `usable_mwh=0.01` to force energy exhaustion.
With normal 2.5 MWh the alert only fires if peak_shortfall > BESS rated_mw (power path).
TC-33 renewable seeded scenario alerts via the power-ceiling path (6.3036 > 5.0 MW).
TC-33 compute seeded scenario does NOT alert (3.3036 < 5.0 MW).

## Step 8 gate results

  pytest: 139/139 (101 pre-existing + 38 new)
  audit_tests: 13/13
  example_usage: 4/4 scenarios, alerts_seen=True
  plane separation: 8 core/ + 7 api/ clean
  tsc --noEmit: 0 errors
  vitest: 19/19
  vite build: clean
  load_test 2× FAIL (consistent with Steps 5-7): wall ~30-32s across samples
  (4× FAIL pre-exists — hardware capacity, not Step 8 regression)
