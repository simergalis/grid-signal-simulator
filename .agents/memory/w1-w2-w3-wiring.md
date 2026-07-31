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

## Z1 — Cooling plant sizing and thermal→dispatch isolation

**Z1(a) sizing formula:** All three factory functions set `_rated_cooling_mw = site.alpha_max × peak_compute_mw` — both **derived** (not a constant). `alpha_max=0.20` is a hardcoded class constant in `SiteConfig`; peak_compute is reverse-engineered from `solar_rated_mw / 0.25` (PROTO-7). Bug: formula accounts for pure compute thermal load only; BESS charging and PUE-base overhead applied to total IT load add ~2-4% excess that immediately saturates the system at peak. **Fix: multiply by 1.15 (PROTO-10-MARGIN)** in all three factory functions — applied July 2026.

**Z1(b) PreStagingEngine isolation:** `PreStagingEngine` in `core/dispatch.py` owns its own `_current_temp_c` state (from `config.initial_temp_c`) and advances it from `gap_mw` alone. It never reads `absorbable_mw` or `time_to_limit_s` — those are computed from `CoolingModule` state and exist only in the thermal API endpoint response. The two systems are **completely decoupled**. demo-20mw has no `pre_staging_config` in spec, so the engine is inactive (None) — `absorbable_mw` has no path into dispatch.

## Z2 — DeterministicRouter must be agent-aware

**Rule:** The private `_DeterministicRouter` in `tests/test_step13_agents.py` is now an alias for the public `DeterministicRouter` from `runtime/advisory_router.py`. The TC-48 companion B assertion (`len(observed_kinds) >= 3`) caught the bug — alias all future private test copies the same way.

**Kind map (in `DeterministicRouter._KIND_MAP`):** compute→curtailment/a_defer, storage→bess_reserve_adjust, generation→turbine_ramp_rate, renewable→pre_staging, thermal→load_defer, calibration→calibration. Unknown agents fall back to curtailment.

**How to apply:** Any new agent added to the registry needs a `_KIND_MAP` entry in `DeterministicRouter`. Without it the fallback is curtailment, which won't break TC-48 but will mask kind-mapping bugs in new agents.

## Y1 — Gate the transport, not the capability

**Rule:** Under pytest (`PYTEST_CURRENT_TEST` set), inject `DeterministicRouter` (in `runtime/advisory_router.py`) as the router — never disable the registry. `AgentRegistry(router=DeterministicRouter() if os.environ.get('PYTEST_CURRENT_TEST') else AdvisoryRouter(), enabled=True)`. The full five-phase loop (qualify → deidentify → route → gate.validate → provenance-stamp) executes; only the network call is bypassed.

**Why:** Disabling the registry with `enabled=False` makes TC-48's hash comparison vacuous — both sides are "agents off" and the test is green regardless of whether the agent code executes. Gating the transport lets TC-48 prove the invariant non-trivially.

**How to apply:** Check is call-time (inside the factory function body), not module-level — `PYTEST_CURRENT_TEST` is set by pytest during test execution, not during collection/import. Module-level assignment always gets False.

**TC-48 companion assertion:** `test_tc48_hash_identical_agents_stopped_vs_active` now asserts `len(registry.all_proposals()) > 0` after the hash check — prevents green-because-vacuous regressions.

## X1 — Test hang fix (three compounding bugs)

**Bug 1 — lifespan didn't cancel tasks:** `_lifespan` in `api/app.py` was a bare `yield` with no shutdown code. Runs with `end_sim_time=1e15` never completed. **Fix:** added `task.cancel()` + `asyncio.gather(*tasks, return_exceptions=True)` in the shutdown path.

**Bug 2 — `finally` block drained the sink after cancel:** Even after cancellation, `_drive()`'s `finally` block called `ctx.sink.get_eval_rows()` + `get_tick_dicts()` which iterates every accumulated `TickResult`. On a max-speed run with millions of ticks, this caused a second hang. **Fix:** `_cancelled_externally` flag (set in `except asyncio.CancelledError`) + `_skip_verdict = _cancelled_externally or ctx.cancelled` guards the entire verdict block. Cleanup (registry preserve, `_contexts`/`_tasks` pop) always runs.

**Bug 3 — LLM API calls during tests:** `ANTHROPIC_API_KEY` and `MISTRAL_API_KEY` are both set in this environment. `AgentRegistry(enabled=True)` was the default in `build_run_context()`. Agents fired when cadence floor was reached (~60s sim time), each LLM call adding 10-25s per test. **Fix:** call-time check in all three `build_*` factory functions: `AgentRegistry(enabled=not bool(os.environ.get('PYTEST_CURRENT_TEST')))`. MUST be call-time (not module-level) — `PYTEST_CURRENT_TEST` is set by pytest only during test execution, not during module import/collection.

**Result:** 414 passed in 7.96s (was hanging indefinitely before).

## X2 — demo-20mw populated-state (300s sim, 60 ticks, agents=True, playback=0)

- **Proposals:** 6 total (pending) — curtailment 2.0MW (compute agent, t=60s), turbine_ramp_rate 12.0MW (storage agent, conf=0.95), plus 4 more agents at 2.0MW / conf=0.85.
- **Energy summary:** generation=1.4006 MWh, grid_import=0.0 MWh, storage_charge=0.0726 MWh (RT_EFF proxy), duration=5 min.
- **Procurement/thermal/network-telemetry:** all 409 after completion (expected).
- **Tick snapshot:** compute ramps 0.55→19.96MW; turbine covers all load; BESS minimal (SOC 0.950→0.942); no reserve alert; verdict=INCONCLUSIVE (assertions empty for demo spec).
