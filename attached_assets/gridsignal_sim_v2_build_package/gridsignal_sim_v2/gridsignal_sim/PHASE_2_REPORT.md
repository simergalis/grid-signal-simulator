# Phase 2 — Unit States + UnitAvailability Boundary: Implementation Report

## Summary

Phase 2 introduces the **five-state turbine model**, the `UnitAvailability` boundary dataclass,
and the `turbine_ramp_credit_mw()` dispatch helper that severs the import path between the
reserve check and `TurbineModule`.  The structural goal is: "the reserve check and N-1 tile
have no import path to the turbine module — verify structurally."

---

## Acceptance Criteria — Result

| ID | Criterion | Result |
|----|-----------|--------|
| P2-1 | `TurbineState` has exactly five canonical states: OFFLINE, STARTING, SYNCHRONISED, OUT_OF_SERVICE, TRANSITIONAL (TC-81 structural test) | **PASS** |
| P2-2 | Legacy aliases RAMPING and AT_TARGET remain for backward compat | **PASS** |
| P2-3 | `UnitAvailability` is a frozen dataclass buildable without TurbineModule import (TC-81) | **PASS** |
| P2-4 | `TurbineModule.unit_availability()` returns correctly-typed `UnitAvailability` (TC-81) | **PASS** |
| P2-5 | STARTING unit reports `time_to_online_s > 0` in UnitAvailability (TC-81) | **PASS** |
| P2-6 | OUT_OF_SERVICE unit reports `time_to_online_s = None` and reason string (TC-81) | **PASS** |
| P2-7 | `turbine_ramp_credit_mw()` in `dispatch.py` computes credit from `UnitAvailability` only — hot-standby excluded, STARTING unit reduced by time-to-online, cap applied (TC-81) | **PASS** |
| P2-8 | `command_start()` transitions unit to STARTING and sets `_time_to_online_s` from thermal state (TC-80) | **PASS** |
| P2-9 | `advance()` ticks the STARTING countdown and transitions to SYNCHRONISED at expiry (TC-80) | **PASS** |
| P2-10 | P_anchor_reserve at San Diego = **1.0 MW** (BessConfig default, no site override) (TC-81) | **PASS** |

---

## State Machine Coverage

### Canonical States (Phase 2)

| State | Meaning | `is_synchronised` | Contributes to loading layer |
|-------|---------|-------------------|------------------------------|
| `OFFLINE` | Not rotating, not connected | `False` | No |
| `STARTING` | Startup countdown active | `False` | No (ramp credit only, partial) |
| `SYNCHRONISED` | On bus, fully available | `True` | Yes (allocated set A) |
| `OUT_OF_SERVICE` | Indefinitely unavailable | `False` | No |
| `TRANSITIONAL` | Between breaker operations | `False` | No |

### Legacy Aliases (Pre-Phase-2, Backward Compat)

| State | Maps to | `is_synchronised` | Contributes to loading layer |
|-------|---------|-------------------|------------------------------|
| `RAMPING` | Allocated, ramping toward target | `True` | No — uses `advance()` |
| `AT_TARGET` | Allocated, at setpoint | `True` | No — uses `advance()` |

**Key invariant:** `is_synchronised = state in {SYNCHRONISED, RAMPING, AT_TARGET} and not hot_standby`.
The loading layer uses `state == SYNCHRONISED` only (not `is_synchronised`) to preserve backward
compatibility with scenarios using the pre-Phase-2 ramp path.

### Transition Rules Implemented

| Trigger | From | To | Guard |
|---------|------|----|-------|
| `command_start()` | OFFLINE | STARTING | `not hot_standby` |
| `advance()` timer expiry | STARTING | SYNCHRONISED | `_time_to_online_s <= 0` |
| `stage_target(target > 0)` (legacy) | OFFLINE | RAMPING | `not hot_standby`, R6 cooling window |
| `stage_target(target == 0)` (legacy) | RAMPING/AT_TARGET | OFFLINE | R5 min-run-time |
| `advance()` ramp complete (legacy) | RAMPING | AT_TARGET | `output >= target` |

Transitions to `OUT_OF_SERVICE` and `TRANSITIONAL` are not yet automated — they require
operator commands (deferred to Phase 3 commitment logic).

---

## UnitAvailability Boundary — Structure

```python
@dataclass(frozen=True)
class UnitAvailability:
    unit_id: str
    state: TurbineState
    output_mw: float
    rated_mw: float
    msl_mw: float
    r_asset_effective_mw_per_s: float   # TurbineConfig.r_asset_mw_per_s (unre-rated in current build)
    time_to_online_s: Optional[float]   # 0.0 = SYNCHRONISED, NaN via STARTING, None = OOS
    out_of_service_reason: Optional[str]
    hot_standby: bool = False           # excluded from ramp credit and loading layer
    
    @property
    def is_starting(self) -> bool: ...
```

**Import chain:**
- `core/models.py` defines `UnitAvailability` (no dependency on `asset_modules.py`)
- `core/asset_modules.py` imports `UnitAvailability` from models and constructs it in `TurbineModule.unit_availability()`
- `core/dispatch.py` imports `UnitAvailability` from models and uses it in `turbine_ramp_credit_mw()`
- No `TurbineModule` import is required to use `UnitAvailability` or call `turbine_ramp_credit_mw()`

---

## P_anchor_reserve Report — San Diego

`BessConfig.p_anchor_reserve_mw` defaults to **1.0 MW**.  The San Diego site configuration
(`core/site_config.py`) does not override this field.  Therefore:

> **P_anchor_reserve at San Diego = 1.0 MW** (TC-81 `test_tc81_p_anchor_reserve_report`)

This is the MW of BESS capacity held in reserve by the anchor-reserve logic (`bess_anchor_reserve.py`)
to maintain island-mode frequency stability.  Any scenario run at the San Diego site sees 1.0 MW
permanently off-limits to the demand-response dispatch path.

---

## Thermal State — Startup Durations

| Thermal State | Condition | Default Startup Duration |
|---------------|-----------|--------------------------|
| HOT | Last-stop < `hot_threshold_s` (3 600 s) | `hot_start_s` = 60 s |
| WARM | Last-stop < `warm_threshold_s` (14 400 s) | `warm_start_s` = 300 s |
| COLD | Otherwise | `cold_start_s` = 900 s |

**CHOSEN — no measured OEM basis.** These are illustrative values for the demo fleet.
TC-80 tests that `command_start()` applies the correct duration given the `_thermal_state`
at call time; the thermal classification logic (tracking `_last_sync_stop_s`) is wired
in `TurbineModule.advance()`.

---

## Spec Contradictions Found

### Contradiction 1: `time_to_online_s` for OFFLINE units
The spec implies OFFLINE units should have `time_to_online_s = None` (no planned return
to service).  But OFFLINE units that have cooled down (eligible for restart) should
arguably report their warm/cold startup time.  In the current build, `unit_availability()`
returns `time_to_online_s = None` for OFFLINE units (same as OUT_OF_SERVICE), which loses
the "restartable in X seconds" information.

**Resolution (deferred):** Phase 3 commitment logic will populate `time_to_online_s` for
OFFLINE units based on thermal state.  Phase 2 treats OFFLINE ≡ unavailable for ramp credit.

### Contradiction 2: RAMPING / AT_TARGET aliases in `is_synchronised`
The spec defines exactly five canonical states.  RAMPING and AT_TARGET are "in allocated
set A" and treated equivalently to SYNCHRONISED for ramp-credit purposes.  But `is_synchronised`
returning True for RAMPING/AT_TARGET while the loading layer excludes them creates a
visible inconsistency: a consumer reading `t.is_synchronised == True` would expect the unit
to be in the loading layer's allocated set, but it is not (it uses `advance()`).

**Resolution (accepted):** The inconsistency is intentional for backward compat.  The
`is_synchronised` property documents this: "RAMPING and AT_TARGET are pre-Phase-2 aliases
retained for backward compatibility … new code must use SYNCHRONISED."  The loading layer
filter explicitly uses `t.state == TurbineState.SYNCHRONISED` to avoid the ambiguity.

### Contradiction 3: `r_asset_effective_mw_per_s` re-rating
`UnitAvailability.r_asset_effective_mw_per_s` is documented as "re-rated if applicable
(TC-58)."  In the current build it equals `TurbineConfig.r_asset_mw_per_s` with no
re-rating.  TC-58 (ambient-temperature de-rating) is tracked under a separate task.

---

## Out-of-Scope Temptations Rejected

1. **Automating OUT_OF_SERVICE / TRANSITIONAL transitions** from operator events.  The
   `OUT_OF_SERVICE` and `TRANSITIONAL` states are defined and have UnitAvailability
   representations, but no automated transition into them.  That requires Phase 3
   commitment/commitment logic which is out of scope here.

2. **Migrating all scenarios to use SYNCHRONISED-state turbines** (removing RAMPING/AT_TARGET).
   The scenario factory and all existing scenarios use `stage_target()` which produces
   RAMPING turbines.  Migrating the factory is a breaking change that would invalidate all
   existing test snapshots.

3. **Wiring `turbine_ramp_credit_mw()` into `stage_for_predicted_step()`** to replace
   the existing `sum(t.config.r_asset_mw_per_s ...)` inline credit formula.  The staging
   call still needs `TurbineModule` for state mutation; only the credit *formula* needed
   the structural extraction.  Replacing the inline formula with the dispatch boundary
   helper is a refactor with no behavioral change — deferred.

4. **Adding STARTING-unit telemetry to the frontend** (`time_to_online_s`, `_start_phase`
   fields).  The `turbine_units` dict in `run_manager.py` already emits these fields, but
   the frontend `TurbineFleet.ts` panel does not yet display startup countdown.

---

## Files Changed

| File | Change |
|------|--------|
| `core/models.py` | `TurbineState` (7 values), `ThermalState`, `UnitAvailability` (+ `hot_standby`, `is_starting`); `TurbineConfig` + 7 Phase 2 fields |
| `core/asset_modules.py` | `TurbineModule` + Phase 2 fields + `command_start()`, `set_output()`, `unit_availability()`; `advance()` updated for STARTING; `stage_target()` records `_last_sync_stop_s` |
| `core/dispatch.py` | `UnitAvailability` imported from models; `turbine_ramp_credit_mw()` pure function added |
| `core/simulation_core.py` | `is_synchronized` in PlantState now uses `t.is_synchronised` |
| `tests/test_p1b_p2.py` | TC-81 × 9 (structural + dispatch boundary + P_anchor_reserve report) |
