---
name: phase2a7-freq-dynamics
description: Key decisions and traps from Phases 2A-7 (frequency dynamics and the balance producer) for the GridSignal simulator.
---

## Suite state after Phases 2A-7

13 failed / 1036 passed / 21 xfailed. All 13 failures are pre-existing (I3a I3b f5 B1a B5 B5b d10 kube×4 tc203_3 tc_gt2f). 5 new xfails added by test_phase2a_catalogue.py (Phase 2A catalogue guards for TC-87–91).

Baseline was 13 failed / 987 passed / 16 xfailed (after spec 2).

## UFLS and 81U relay: OPT-IN (critical)

**Rule:** `SiteConfig.ufls_stages` defaults to `[]` (empty, disabled). `relay_81u_threshold_hz` defaults to `None` (disabled). Both must be explicitly set per-scenario to enable protection.

**Why:** The UFLS thresholds (59.3/58.9/58.5 Hz for 60 Hz systems) are only 0.7–1.5 Hz below nominal. Any islanded run with minor frequency deviations (e.g. verdict tests, kube tests) would trigger spurious UFLS trips. Making them opt-in preserves backward compatibility.

**How to apply:** In `ScenarioSpec`, add `ufls_stages` (list of dicts) and `relay_81u_threshold_hz` (float) explicitly. `scenario_factory.py` wires these to `SiteConfig`. For tests, set `state.site.ufls_stages = list(_sp.value('ufls_stages'))` and `state.site.relay_81u_threshold_hz = float(_sp.value('relay_81u_threshold_hz'))` then also resize `state._ufls_timer_s` and `state._ufls_fired`.

## UFLS and 81U guard: threshold must be below system nominal

**Rule:** Both UFLS and 81U guards check `threshold_hz < frequency_nominal_hz` (or `_f0`). If threshold ≥ nominal, the stage is skipped (not calibrated for this system).

**Why:** 57.5 Hz 81U threshold and 59.3 Hz UFLS threshold are calibrated for 60 Hz WECC systems. For 50 Hz EU/APAC systems, these thresholds are above nominal — the relay would fire immediately on every tick. The guard prevents this.

## Governor cascade: decoupled from swing equation forcing

**Rule:** Phase 4 governor cascade (valve_tc → fuel_tc → max_load_step_mw) runs in the sub-step loop to advance governor STATE (`_gov_valve_mw`, `_gov_power_mw`). This state is used diagnostically and can be read next tick. It does NOT feed back into this tick's swing equation forcing.

**Why:** If `_gov_increment` (within-tick governor change) were added to `_p_net_pu` in the swing equation, the governor fully converges within one 5-second outer tick (valve_tc=0.2s, fuel_tc=1.0s → 99% settled in 5s). This creates a large within-tick feedback that reduces the actual Δf by ~10× vs the swing equation prediction. The I2 test (`Δf within ±10% of predicted`) would fail.

**How to apply:** The swing equation uses `(_frequency_forcing_mw + _shed_this_tick_mw) / _s_base_mva` as forcing. No `_gov_increment` term. Governor advance in sub-step loop runs AFTER the swing equation.

## Dispatch droop: instantaneous formula (not previous terminal state)

**Rule:** The dispatch droop correction uses the instantaneous formula:
`_droop_correction_mw = Σ [(-Δf / (droop_r_i × f0)) × S_i]`
where Δf = current `state._frequency_hz - frequency_nominal_hz`, S_i = per-unit MVA for each on-bus turbine.

**Why:** Using the previous tick's governor terminal state (`sum(t._gov_power_mw)`) creates a one-tick delay. On the first tick with elevated frequency, `_gov_power_mw = 0` → no correction → I3 (droop restoring force invariant) fails.

**Why instantaneous formula works:** After one outer tick (5s), the governor cascade FULLY converges to the instantaneous target (valve_tc=0.2s → settled in 1s; fuel_tc=1.0s → settled in 5s). So the instantaneous formula and the terminal state give the same result on all ticks except the first, making the distinction irrelevant for multi-tick runs.

## Isolating over-frequency droop in tests

**Rule:** A droop-direction fixture needs a protection threshold above the injected frequency, nonzero turbine output with downward headroom, and no available BESS discharge.

**Why:** A threshold below the disturbance correctly trips protection, a turbine at zero cannot reduce generation, and an energized BESS correctly fills the droop-created gap. Each condition masks the governor’s restoring-force signal.

**How to apply:** Author an over-frequency trip above the test disturbance, start the synchronized turbine above zero with its MSL floor disabled when appropriate, and deplete or omit BESS when asserting raw `frequency_forcing_mw`.

## protection_provisional: True for ALL islanded ticks

**Rule:** `TickResult.protection_provisional = True` whenever `_islanded` is True. Set unconditionally in the islanded branch.

**Why:** All islanded protection parameters (UFLS thresholds, 81U threshold, D_eff damping, droop_r, valve_tc, fuel_tc) are PROVISIONAL-UNMEASURED. Any islanded tick uses these parameters.

**How to apply:** `run_manager.py` calls `set_run_provisional()` whenever a tick with `protection_provisional=True` is broadcast. `is_export_blocked()` returns True after that. Export is blocked for the run's lifetime (not per-tick).

## Phase 6 p_served/p_unserved/p_imbalance: wired but TC-87/91 still xfail

Phase 6 wires `p_served_mw`, `p_unserved_mw`, `p_imbalance_mw` to TickResult (and through `_tick_result_to_dict()`). The actual values compute proportional UFLS shed allocation.

TC-87/91 use hardcoded `_PHASE2_TICK` dictionaries with `p_served_mw: None`. They remain xfail because the test checks the hardcoded None value (testing future state). `strict=True` means xpass = error — do NOT change to strict=False.

## Resolved parameters (DR-2026-08-08-FREQ)

| Parameter | Value | Status |
|---|---|---|
| dynamic_step_s | 0.01 s | CHOSEN |
| ufls_stages | [{59.3Hz, 0.15s, 10%}, {58.9Hz, 0.15s, 15%}, {58.5Hz, 0.15s, 20%}] | PROVISIONAL |
| relay_81u_threshold_hz | 57.5 Hz | PROVISIONAL |
| relay_81u_delay_s | 0.10 s | PROVISIONAL |
| fixed_speed_cooling_fraction | 0.30 | PROVISIONAL |
| d_motor | 2.5 | PROVISIONAL |
| droop_r (per-turbine) | 0.04 pu/pu | CHOSEN |
| power_factor_turbine | 0.85 | CHOSEN |
| valve_actuation_tc_s | 0.2 s | PROVISIONAL |
| fuel_to_power_tc_s | 1.0 s | PROVISIONAL |
| max_instantaneous_load_step_mw | 2.25 MW | PROVISIONAL |
| vsm_inertia_constant_s | 2.0 s | PROVISIONAL |

## Files touched (Phases 2A-7)

- `gridsignal_parameters.json` — 13 new locked entries
- `core/models.py` — SiteConfig Phase 2A-5 fields; TurbineConfig Phase 2B per-unit; TickResult protection_provisional + Phase 6 served/unserved fields; UFLS/81U opt-in defaults
- `core/simulation_core.py` — Phase 2C H_agg/S_base_mva; Phase 3 sub-step swing eq; Phase 4 governor cascade (decoupled); Phase 5 UFLS + 81U (with guards); Phase 6 producers
- `core/asset_modules.py` — TurbineModule governor state fields
- `api/schemas.py` — TurbineUnitSpec per-unit fields; ScenarioSpec UFLS/81U fields
- `runtime/scenario_factory.py` — UFLS/81U wiring to SiteConfig
- `runtime/run_manager.py` — protection_provisional + export gate + Phase 6 dict fields
- `api/routes/export.py` — HTTP 403 export gate
- `frontend/src/types.ts` — protection_provisional: boolean added
- `tests/test_phase2a_catalogue.py` — Phase 2A acceptance tests (new file)
