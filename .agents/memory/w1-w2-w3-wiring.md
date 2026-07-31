---
name: W1/W2/W3 run-loop wiring, advisory endpoints, frontend un-stub
description: Architectural decisions and traps from the W1 agent+telemetry+thermal wiring, W2 new API endpoints, and W3 frontend live-data wiring.
---

## W1 — Run-loop wiring (runtime/run_manager.py + runtime/scenario_factory.py)

**Rule:** Agents, synthetic telemetry, corroboration, and thermal state are all wired in `_drive()` after each `ctx.step()`. Order is fixed: (1) registry.tick → registry.run_all, (2) _ingest_synthetic_telemetry, (3) corroborate checkpoint_states, (4) _update_thermal_state.

**Why:** TC-48 proves agents write only to the advisory gate (proposals), never to SimulationState. Dispatch is bit-identical whether agents are on or off. Concurrency isolation test confirms 5 concurrent runs are still bit-identical after W1.

**How to apply:** `ctx.registry.tick(sim_time)` MUST precede `ctx.registry.run_all(...)` on every tick (expiry before fire). Only call after `ctx.step()` completes.

**Performance:** p50 evaluate_tick() = 1075.7µs with agents on — within 6µs of pre-W1 baseline. LP-1 short-circuit fires when no LLM keys; agents add ~0 per-tick overhead.

**TRAP — circular imports:** `runtime/run_manager.py` MUST NOT import from `advisory/` at module level (advisory/ imports from runtime/advisory_gate → circular). Use `Optional[Any]` typed fields in RunContext. All advisory imports live in `runtime/scenario_factory.py` (allowed) and in lazy imports inside `_ingest_synthetic_telemetry()`.

**TRAP — plane separation:** `api/routes/advisory.py` MUST NOT import from `core/` even lazily inside functions. The plane-separation test scans all lines. Inline TC-70 clock-demotion: `eff = 'ntp' if (disc == 'ptp' and skew > 2.0) else disc`.

**TRAP — `_time_module`:** `time` is already imported as `_time_module` in run_manager.py. Don't re-import.

## W1 — Registry preservation post-run

**Rule:** In `_drive()`'s `finally` block, `self._registries[ctx.run_id] = ctx.registry` preserves the registry after run completion. `get_registry()` checks active contexts first, then `_registries`.

**Why:** `/proposals/{run_id}` must work for completed runs (reviewers often act after a run ends).

## W1 — Synthetic telemetry event_id uniqueness

**Rule:** Telemetry records use `event_id = f"nt-{switch}-{tick.tick_index}"` — unique per tick per switch. Using sim_time float would collide on duplicate timestamps; tick_index is guaranteed unique.

## W2 — Advisory endpoint plane rule

**Rule:** `api/routes/advisory.py` is in api/ — it reads from `RunManager` (via `request.app.state.run_manager`), not from core/ or runtime/ directly. Inline any core/ logic needed (e.g. TC-70 demotion check). No `from core.` or `from runtime.` imports at any scope in api/.

**Exception:** `from runtime.run_manager import RunManager` IS allowed (api/ → runtime/ is allowed; only core/ → runtime/ is forbidden).

## W2 — Monitoring surface semantics (409 for completed runs)

**Rule:** `/procurement/{run_id}`, `/network-telemetry?run_id=`, `/thermal?run_id=` return 409 for completed runs. `/proposals/{run_id}` and `/runs/{run_id}/energy-summary` work for completed runs.

**Why:** Procurement/telemetry/thermal are live monitoring surfaces. Proposals and energy-summary are historical records.

## W2 — Energy summary derivation

**Rule:** `generation_mwh = Σ turbine_output_mw × 5/3600`, `grid_import_mwh = Σ max(0, net_demand - turbine - bess) × 5/3600`, `storage_charge_mwh = discharge_mwh / 0.88` (RT_EFF proxy).

**Why:** Actual BESS charge power is not tracked in TickResult. Discharge / round_trip_efficiency = cost-model proxy for energy put into BESS. This matches the §21.2 cost model used by ScenarioPlannerPage.

## W3 — Frontend live-data wiring

**Rule:** All 4 un-stubbed pages (Procurement, NetworkTelemetry, Thermal, ScenarioPlannerPage) poll via `useEffect` + `setInterval`. Procurement at 2 Hz, Telemetry at 2 Hz, Thermal at 1 Hz, ScenarioPlanner polls every 3s for energy-summary until the run completes.

**TRAP — URL prefix:** Advisory routes (`/proposals/`, `/procurement/`, `/network-telemetry`, `/thermal`) have NO `/api/` prefix in the URL. The advisory router is included in app.py without a prefix. Runs router has `/runs` prefix (so energy-summary is at `/runs/{run_id}/energy-summary`).

**TRAP — 409 from procurement/telemetry/thermal:** When the run completes, these return 409. The frontend clears the interval and keeps the last-seen state. Do NOT treat 409 as an error — it's the expected terminal state for a completed run.

## Concurrency test notes

The test_concurrency.py and run-starting test_api.py tests may hang under pytest's asyncio strict mode (pre-existing — asyncio.create_task inside TestClient has known issues with some Starlette versions). The tests pass when run directly via asyncio.run(). The concurrency isolation property (5 concurrent runs bit-identical) was verified directly via asyncio.run() — PASS.
