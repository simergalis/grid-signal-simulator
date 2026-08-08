# NAR-001 — Phase 0 Orientation Report

**Task:** GS-DES-NAR-001 variable inventory  
**Phase:** 0 — Read-only orientation (pre-inventory)  
**Date:** 2026-08-08  
**Status:** Complete — awaiting Phase 1 sign-off

---

## ⚠ STOP-AND-REPORT: Two trigger conditions met

1. **More than two physics modules exist.** The codebase has nine distinct modules that compute physics (see §1.3 below). This is architecturally deliberate — `evaluate_tick()` orchestrates them — but the spec asks to be told.
2. **Sections F (Thermal) and H (Verdict/Network) are expected to return >25% NOT_FOUND** (see §4 below). Verified by reading the wire dict and frontend types.

---

## 1. Module Map

### 1.1 Simulation tick loop

| Item | Value |
|---|---|
| File | `core/simulation_core.py` |
| Line | 371 |
| Signature | `def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult` |

### 1.2 Per-tick state object

Single object: **yes.** `TickResult` is a frozen `@dataclass` at `core/models.py:869`. All 80+ fields are in one object. There is no secondary per-tick state object. The `SimulationState` object holds mutable run-time state *between* ticks (BESS SoC, turbine states, etc.); `TickResult` is the immutable snapshot of one interval.

### 1.3 Physics modules (nine, all called by `evaluate_tick`)

| Module | Primary entry point | What it computes |
|---|---|---|
| `core/simulation_core.py` | `evaluate_tick()` | Orchestration — calls all others; swing equation, UFLS, governor |
| `core/asset_modules.py` | `GPUModule`, `CoolingModule`, `BessModule`, `TurbineModule` methods | Per-asset power draw, ramp, SoC |
| `core/loading.py` | `compute_loading_setpoints()` | Fleet loading targets (MSL, setpoints) |
| `core/dispatch.py` | `DispatchArbitrator.compute_tick()`, `.compute_shift()` | Dispatch arbitration, pre-staging shift |
| `core/commitment.py` | `evaluate_commitment()` | Unit commitment (start/stop decisions) |
| `core/contingency.py` | `evaluate_contingency()` | N−1 gen-trip coverage assessment |
| `core/cost_model.py` | `compute_run_cost()` | Energy cost accounting |
| `core/kube_demand.py` | demand/power profile methods | Kubernetes workload demand model |
| `core/ramp_relaxation.py` | `RampRelaxation.evaluate()` | Ramp-rate relaxation |
| `renewable/solar.py` | (called via SolarSim) | Solar irradiance → output MW |

### 1.4 API layer and WebSocket publisher

| Item | Value |
|---|---|
| WS endpoint | `api/routes/ws.py`, route `GET /ws/{run_id}` |
| Publisher | `runtime/run_manager.py`, class `WebSocketHub`, method `broadcast(run_id, tick_result)` |
| Topic model | **No named topics.** Each connection subscribes to one run_id via the URL path. The hub is retrieved from `app.state.ws_hub`. |
| Message types | (1) Tick dict — the full `_tick_result_to_dict()` payload; (2) sentinel `{"type": "run_complete", "run_id": "..."}` on natural completion |
| Schema type name | `TickPayload` — TypeScript interface at `frontend/src/types.ts:10` |

### 1.5 Runtime configuration catalogue

| Item | Value |
|---|---|
| Values file | `gridsignal_parameters.json` (76 keys across `locked`, `adjustable`, `enumerated` sections) |
| Accessor | `core/site_parameters.py:197`, function `value(key: str) -> Any` |
| How callers import | `from core import site_parameters as _sp` then `_sp.value("key")` |

### 1.6 Frontend components — landing page tiles and detail panels

| Component / file | Role |
|---|---|
| `frontend/src/opening/OpeningScreen.tsx` | Root opening screen — orchestrates all opening-screen components |
| `frontend/src/opening/VerdictBand.tsx` | Primary verdict claim band (Band 1) — the plant readiness claim with live tick data |
| `frontend/src/opening/PlantDiagram.tsx` + `PlantNode.tsx` | Plant topology diagram tiles |
| `frontend/src/readiness/ReadinessScreen.tsx` | Nine readiness tiles layout |
| `frontend/src/readiness/SubsystemTile.tsx` | Individual readiness tile (used 9×) |
| `frontend/src/readiness/ReadinessBanner.tsx` | Overall verdict + four hero figures (header) |
| `frontend/src/readiness/subsystems.ts` | Static config for the 9 tiles (IDs, names, accent colours) |
| `frontend/src/subsystem/panels/compute.ts` | Compute & Workload detail panel data |
| `frontend/src/subsystem/panels/generation.ts` | Generation detail panel data |
| `frontend/src/subsystem/panels/storage.ts` | Energy Storage detail panel data |
| `frontend/src/subsystem/panels/renewable.ts` | Renewable Supply detail panel data |
| `frontend/src/subsystem/panels/forecastQuality.ts` | Forecast Quality detail panel data |
| `frontend/src/subsystem/panels/network.ts` | Network Fabric detail panel data |
| `frontend/src/subsystem/panels/agents.ts` | Optimisation Agents detail panel data |
| `frontend/src/subsystem/panels/turbineFleet.ts` | Gas Turbine Fleet detail panel |
| `frontend/src/subsystem/useSubsystemData.ts` | Hook that computes `TileState` + verdict string for all 9 tiles |

### 1.7 Persistence layer

File: `runtime/persistence.py`

| Table | Notes |
|---|---|
| `site` | Site identity and thermal config |
| `asset_config` | Per-asset configuration |
| `scenario` | Scenario definitions |
| `run_timeseries` | Tick-by-tick run output |
| `control_event` | Operator commands |
| `control_event_ack` | Acknowledgement records |
| `dedupe_key` | Idempotency |
| `quarantine` | Quarantined ticks |
| `principal` | Identity principals |
| `auth_user` | Authenticated user accounts |
| `recommendation` | Advisory proposals |
| `parameter_change_audit` | Audited parameter changes |

### 1.8 LLM client

| Item | Value |
|---|---|
| File | `runtime/advisory_router.py` |
| Selection logic | Priority: MISTRAL_API_KEY → `mistral-small-latest`; fallback ANTHROPIC_API_KEY → `claude-haiku-3-5`; else no LLM |
| Mistral model string | `"mistral-small-latest"` — constant `_MISTRAL_MODEL` at line 49 |
| Anthropic model string | `"claude-haiku-3-5"` — constant `_ANTHROPIC_MODEL` at line 52 |
| API version header | Anthropic only: `"2023-06-01"` at line 53 |

---

## 2. Enumerations

### 2.1 Backend enums (all in `core/models.py`)

**`TurbineState(str, Enum)`** — unit operating state:
`OFFLINE='offline'` · `OUT_OF_SERVICE='out_of_service'` · `STARTING='starting'` · `UNLOADING='unloading'` · `SYNCHRONISED='synchronised'`

**`WorkloadEventType(str, Enum)`** — scheduler event:
`QUEUED` · `STARTING` · `RUNNING` · `SCALE` · `CHECKPOINT_START` · `CHECKPOINT_END` · `JOB_END` · `CANCELLED` · `SOLAR_STEP` · `UNIT_TRIP`

**`WorkloadClass(str, Enum)`**: `TRAINING='training'` · `INFERENCE='inference'` · `OTHER='other'`

**`IslandMode(str, Enum)`** (`core/models.py:124`): `GRID_TIE='grid_tie'` · `ISLANDED='islanded'`

**`OperatingTier(str, Enum)`**: `AUTONOMOUS='autonomous'` · `SUPERVISED='supervised'` · `OPERATOR='operator'`

**`ThermalState(str, Enum)`**: `COLD='cold'` · `WARM='warm'` · `HOT='hot'`

**`ContingencyState(str, Enum)`**: `COVERED='COVERED'` · `COVERED_WITH_SHED='COVERED_WITH_SHED'` · `CANNOT_CARRY='CANNOT_CARRY'`

**`DataQualityTag(str, Enum)`**: `UNMAPPED_HARDWARE` · `UNCALIBRATED_SITE` · `INVALID_PAYLOAD` · `STALE_PROFILE` · `WORKLOAD_SIGNAL_STALE` · `WORKLOAD_SIGNAL_ABSENT`

**`TransitionMode(str, Enum)`**: `OPEN_TRANSITION` · `CLOSED_TRANSITION`

**BESS mode — NOT FOUND as enum.** `BessConfig.grid_forming: bool` is the only mode flag. No `CHARGING` / `DISCHARGING` / `IDLE` / `ANCHOR` states exist in any enum.

**Run state — NOT FOUND as enum.** Lifecycle is implicit: active `RunContext` in a dict, `ctx.cancelled: bool`, asyncio task completion. The WS sentinel `{"type": "run_complete"}` signals termination but there is no `RunState` class.

### 2.2 Frontend-only enum-like types (TypeScript, `frontend/src/`)

**`TileState`** (`readiness/SubsystemTile.tsx:15`) — per-subsystem readiness verdict:
`'READY'` · `'ACTIVE'` · `'ARMED'` · `'ATTENTION'` · `'ISLANDED'` · `'ADVISORY'` · `'INACTIVE'` · `'OFFLINE'` · `'—'`

**`AssertionResult.status`** (`types.ts`): `'PASS'` · `'FAIL'` · `'INCONCLUSIVE'`

**`RunResult.overall`** (`types.ts`): `'PASS'` · `'FAIL'` · `'INCONCLUSIVE'`

---

## 3. TC- and Document IDs

**Highest TC- number in repo:** `TC-203` (in `tests/test_operator_unit_commands.py`)

The number space is not contiguous: TC-21, TC-47, TC-52, TC-61 through TC-98, TC-203. The range TC-100 through TC-202 is empty.

| ID type | IDs found |
|---|---|
| GS-DES- | `GS-DES-CFG-001` |
| DR- | `DR-2026-08-08-FREQ` |

---

## 4. Expected Phase 1 Signal Coverage and NOT_FOUND Forecast

| Section | Signals | Est. FOUND | Est. NOT_FOUND | Notes |
|---|---|---|---|---|
| A — SCHED (13) | 13 | ~8 | ~5 | `jobs_total`, `jobs_running`, `jobs_starting`, `last_event_age_s`, `feed_health` have no exact wire names; `kube_metrics.active_jobs` is nearest to `jobs_running` but a different concept |
| B — LOAD (~11) | ~11 | ~8 | ~3 | `pue_effective` not on wire; served/unserved for compute/cooling present but null (Phase 6 partial) |
| C — GEN (25) | 25 | ~17 | ~8 | `BESS.mode` NOT_FOUND; `units_installed` NOT_FOUND; `floor_violated` NOT_FOUND (→ `reserve_satisfied` bool only); `reserve_margin_mw` NOT_FOUND (only `reserve_floor_mw` + `committed_rated_mw`); `gen_trip_cover_shed_mw` AMBIGUOUS vs `contingency_coverage.shed_required_mw` |
| D — DEMAND (7) | 7 | ~4 | ~3 | `DQ.band_widening_pct` NOT_FOUND; `DEMAND.calibration_state` NOT_FOUND |
| E — RENEW (8) | 8 | ~5 | ~3 | `sun_elevation_deg` NOT_FOUND; `offset_applied_mw` NOT_FOUND; `conditions` AMBIGUOUS (`solar_conditions` string exists) |
| **F — THERM (10)** | **10** | **~4** | **~6 ⚠ >25%** | `alpha_measured`, `cooling_lag_observed_s`, `cdu_state`, `loop_state`, `approach_temp_c` all NOT_FOUND; only `rated_cooling_mw`, `alpha_max`, `ambient_avg_c`, `compute_inlet_temp_c` on wire |
| G — RUN (13) | 13 | ~8 | ~5 | `physics_path` NOT_FOUND; `code_rev` NOT_FOUND; `CLOCK.site_tz` NOT_FOUND; `CLOCK.site_local` NOT_FOUND; `RUN.scenario_version` NOT_FOUND |
| **H — VERDICT/NET (~8)** | **~8** | **~2** | **~6 ⚠ >25%** | `VERDICT.{panel}` is a formatted string built in `useSubsystemData.ts` — no structured backing; `ALERT.active_list` NOT_FOUND (only `insufficient_reserve_alert: bool`); all four NET signals (switches_reporting, clock_class, clock_class_degraded_n, attention_subsystem_count) NOT_FOUND or AMBIGUOUS |
| I — Invariants | 9 inputs | partial | — | See note below |
| J — Catalogue | 76 keys | 76 | `tick_rate_s` missing | Deadband/hysteresis/trend_window/staleness/tolerance partially present under different key names (`levelled_off_epsilon_mw`, `commit_confirm_s`, etc.) |

### Section I — Invariant input coverage note

| Invariant | Coverage |
|---|---|
| I1 — power balance | All inputs in `TickResult` or turbine_units dict |
| I2 — attribution | All inputs locatable |
| I3 — tri-field | All inputs locatable |
| I4 — asset rating | All inputs locatable |
| I5 — storage energy | All inputs in `TickResult` |
| I6 — N−1 firm capacity | Partial: `committed_rated_mw` present; `units_online` and `n1_firm` need mapping |
| I7 — solar vs elevation | Partial: `p_expected_mw` present; `sun_elevation_deg` NOT_FOUND |
| I8 — feed health vs last-event age | NOT_FOUND: no feed-health or last-event-age field on wire |
| I9 — clock coherence | Partial: `site_utc_offset_h` on wire; `site_tz` and `site_local` absent |

### Section K — Tile content

- **Explainer tile content:** TSX string literals in `frontend/src/opening/TopologyExplainer.tsx` (three plane descriptions + signal flow). No component-level IDs.
- **Readiness header verdict string:** Derived inline in `ReadinessBanner.tsx` from live tick fields. No stable component ID — addressed by component name only.
- **VerdictBand claim string:** Built inline from `tick.contingency_coverage` state. No stable ID.

---

## 5. STOP-AND-REPORT Summary

| Trigger | Section | NOT_FOUND rate | Threshold |
|---|---|---|---|
| ⚠ Exceeded | F — Thermal | ~60% | 25% |
| ⚠ Exceeded | H — Verdict / Network | ~75% | 25% |
| ℹ Note | Physics modules | 9 modules (not ≤2) | >2 = report |
