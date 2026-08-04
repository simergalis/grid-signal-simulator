---
name: Phase 1b/2 Loading Layer + UnitAvailability
description: Continuous loading layer (core/loading.py), UnitAvailability boundary, turbine_ramp_credit_mw(), and critical traps encountered during implementation.
---

## Rule
Allocated set A (loading layer) = `t.state == TurbineState.SYNCHRONISED` only — NOT `t.is_synchronised`.

**Why:** `is_synchronised` returns True for RAMPING and AT_TARGET (legacy pre-Phase-2 aliases). Those units continue using `advance()`. Applying the loading layer to them causes a double-advance bug (both the loading layer AND `advance()` move the output in the same tick), which breaks B1a.

**How to apply:** The filter in `simulation_core.py` must read `t.state == TurbineState.SYNCHRONISED`, never `t.is_synchronised`. `ramp_capability()` in `loading.py` still uses `is_synchronised` since the ramp-credit calculation covers all on-bus units.

---

## THE TRAP: Stray @dataclass on TurbineState enum
When `TurbineState(str, Enum)` was inserted into models.py to replace the original `TurbineConfig` location, the `@dataclass` decorator that had been on the line above `TurbineConfig` was left pointing at `TurbineState`. This caused a `ValueError: mutable default <enum 'TurbineState'> for field state is not allowed` on import of asset_modules.py.

Fix: remove the `@dataclass` decorator from the line immediately before `class TurbineState(str, Enum)` in models.py. `TurbineConfig` has its own `@dataclass` decorator at its own line.

---

## UnitAvailability boundary
- Defined in `core/models.py` (no asset_modules import needed)
- Built by `TurbineModule.unit_availability()` in `core/asset_modules.py`
- Consumed by `turbine_ramp_credit_mw()` in `core/dispatch.py` (also imports from models only)
- Key fields: `hot_standby`, `is_starting` (property), `r_asset_effective_mw_per_s`, `time_to_online_s` (None = OOS, 0.0 = SYNCHRONISED, positive = STARTING countdown)
- Frozen dataclass — immutable after construction

## turbine_ramp_credit_mw() rules
- hot_standby units: excluded (0 credit)
- STARTING units: credit = r × max(0, lead_window - time_to_online_s)
- All others (SYNCHRONISED, RAMPING, AT_TARGET): credit = r × lead_window
- Result capped to delta_p_mw

---

## Pre-existing failures (do not touch)
- test_d10_demo_20mw_bess_fires_and_tapers
- test_item4_small_unit_capped_to_ceiling_under_equal_share
- test_f5_sim_time_interval_end (dt_lead_next_s gets 115.0 vs expected 40.0)
- test_kube_no_oscillation (intentionally red — documents §6.2 oscillation issue)
- test_demo_pms_column3_tc64_to_tc68 TC-67 (demo-pms turbine stays OFFLINE; inject_transition does not create a detectable coverage gap — pre-existing)

## Test counts after Phase 1b/2
Clean suite (excluding API/auth/step16/step8/fabric tests): 834 pass, 7 pre-existing failures, 1 skip.
Total suite: 911 pass when run in isolation (API tests pass alone, fail in combined run due to asyncio event loop ordering).
