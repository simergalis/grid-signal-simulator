---
name: websockets package installation
description: uvicorn requires the websockets (or wsproto) library for WebSocket support; it is NOT included by default and must go into .pythonlibs, not the system Nix store.
---

## Rule

Install `websockets` via `pip3 install --target=/home/runner/workspace/.pythonlibs/lib/python3.13/site-packages websockets`.

**Why:** The Nix Python store is read-only — `pip install websockets` and `pip install --break-system-packages websockets` both fail with EPERM. `uv add websockets` (the Replit package manager) also fails with the same EPERM. The correct target is the writable `.pythonlibs` directory, which is already on `sys.path` and where uvicorn itself lives.

**How to apply:** Without this package, uvicorn logs "No supported WebSocket library detected" and returns HTTP 404 for every WS upgrade request. The frontend shows the LIVE badge (run detected via polling) but never receives any tick data — node MW values stay at their static defaults. Install once; the package persists across workflow restarts.

## AB1 — Load test 1× regression root cause

**Root cause: synchronous LLM calls blocking the asyncio event loop.**

`BaseAdvisoryAgent.__init__` sets `_last_run_wall = float("-inf")`. So on tick 1 of every run, `elapsed = wall_time - (-inf) = +inf ≥ FLOOR_WALL_S (30s)` — ALL six agents fire immediately. `build_load_test_context` wires `AgentRegistry(enabled=True, router=AdvisoryRouter())` WITHOUT checking `PYTEST_CURRENT_TEST` for `enabled`. Since `MISTRAL_API_KEY` is set in the environment, `has_agent=True`, and qualifying agents make synchronous HTTP requests (via `requests` library, NOT async) to `https://api.mistral.ai/v1/chat/completions`. These block the event loop.

**Profiler measurements (1 run, 4h scenario, max speed, 2880 ticks):**
- `E_registry_run_all`: 5.755s total (67.8% of wall clock); p50=0.003ms (cadence no-ops); ~1 call ≈ 5.7s (LLM call on tick 1)
- `A_evaluate_tick`: 2.287s (p50=0.775ms) — unchanged, not the regression
- All other sections: < 0.2s each
- Total single-run wall: 8.49s

**With 5 concurrent runs (load_test.py default):** Each run fires agents on tick 1. Calls are sync → serialize across all 5 runs. Net: 5 × ~5-6s = 25-30s LLM time + 8-10s base = 38-54s (observed: 54-66s with API variance).

**AD1 isolation:** `build_load_test_context` does NOT wire AD1 layers (`procurement_layer`, `maintenance_layer`, `ramp_relaxation_engine` all remain `None`). The 3 AD1 blocks in `_drive()` are guarded by `if ctx.X is not None:` and never execute during load tests. AD1 is not the regression.

**Fix applied (AC1):**
- (a) `build_load_test_context` now uses `enabled=False` — load test back to 20.4 s, PASSES.
- (b) `_drive()` wraps `ctx.registry.run_all()` in `asyncio.to_thread()` — production fix. With agents enabled, the LLM call runs in a worker thread; event loop stays free. Enabled=True load test: 26.3 s (vs 54–66 s blocked). The 6 s difference is the LLM call cost itself — that is now the lower bound when keys are set.
- (c) `asyncio.to_thread` passes `list(ctx.tick_history)` (a snapshot copy) to prevent race conditions with the main loop mutating the list after the await.

**AC2 decision (KEEP float("-inf") — deliberate tick-1 stampede):** Short demos (8 s wall at max speed) end before the 30 s cadence floor fires. Initializing to `time.monotonic()` would mean those runs produce zero proposals. The stampede on tick 1 is intentional and documented in `base.py`. With `asyncio.to_thread` in place, the stampede does not stall the event loop — it is purely a cost question.

**AC3:** Section profiling wired inside `_drive()` behind `GS_PROFILE_DRIVE=1`. Reports p50 + p95 per section at run end via `logger.info`. `_report_drive_profile()` is a module-level function in `run_manager.py`. Standalone `scripts/drive_profile.py` retained as a monkey-patch alternative for pre-restart profiling.

**Why previously 9.99–20.7s:** Either the registry was not yet wired into `build_load_test_context` (pre-W1), or `MISTRAL_API_KEY` / `ANTHROPIC_API_KEY` were absent. After W1 wired the registry AND the keys are present, tick 1 always fires synchronous LLM calls.

## Demo scenario duration

All 13 seeded demo scenarios use `end_sim_time=300.0 s` (5-minute sims). At MAX speed (`playback_speed=0`), a single run completes in ~1–2 s wall-clock. For a "running" screenshot with visible data, use `playback_speed=10` and start the screenshot 8+ seconds after run start (sim_time ~80 s, past the job-event at t=60 s).

## Run auto-detection in App.tsx

`App.tsx` polls `GET /runs` every 2 s when `runId === null` and sets the run_id automatically. This lets a curl-started run be picked up by the browser without clicking the START button. Once a run is detected, `handleRunStarted` no longer calls `setCurrentPage('overview')` — the opening screen stays visible during the run so flow lines can thicken live.
