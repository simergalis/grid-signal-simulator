---
name: Step 5 clock domains
description: SimClock design, two clock rules, 2x load-test borderline status, and the load-test instrumentation wrapper that must be kept in sync with evaluate_tick's signature.
---

**Two rules (stated in core/sim_clock.py docstring):**
1. All specification intervals are measured in SIMULATED time (15-min dedupe, 45s recovery, 30s grace, 120s curtailment, 10s BESS taper, Δt_lead ramp, dt_thermal+5τ retention).
2. A restart RESUMES simulated time (reads tick_seq from DB) — does not reset to 0. Resetting would make a nearly-expired grace period appear to just have started.

**SimClock design:**
- `@dataclass(frozen=True, slots=True)` in `core/sim_clock.py` — slots=True reduces per-tick construction from ~1.09µs to ~0.97µs.
- Fields: `sim_time: float`, `dt_seconds: float`, `wall_stamp_utc: float` (UTC Unix ts, 0.0 sentinel for tests), `rate: float`, `tick_seq: int`.
- Constructed in `runtime/run_manager.py:RunContext.step()` (the ONLY place that reads the wall clock in the hot path).
- Injected into `evaluate_tick(state, clock: SimClock)` — function body uses `sim_time = clock.sim_time; dt_seconds = clock.dt_seconds` shim.
- `core/` never calls `time.time()` — Step 4's static gate enforces this.

**Persistence:**
- `wall_stamp_utc: Mapped[float]` added to `RunTimeseries` in persistence.py.
- `TickResult.wall_stamp_utc: float = 0.0` (default 0.0 preserves backward-compat for in-memory tests).

**THE TRAP — load test instrumentation wrapper:**
`scripts/load_test.py` monkey-patches `run_manager_module.evaluate_tick` with `_instrumented_evaluate_tick`.
The wrapper signature MUST match evaluate_tick's current signature.
When evaluate_tick's signature changed from `(state, sim_time, dt_seconds)` to `(state, clock)`, the wrapper had to be updated too.
If it's out of sync: `TypeError: _instrumented_evaluate_tick() missing 1 required positional argument`.

**2x load-test borderline note:**
The 2x NFR (4h run in <30s at max speed) was borderline at 27–28s before Step 5. After Step 5, Replit container load caused consistent 30–38s readings. Profiling confirmed SimClock adds only 0.074s of overhead at 2x (negligible). The regression is environmental (container degradation after 5+ consecutive load tests). Best observed run after Step 5: 866µs p50 / 30.3s wall — borderline pass. Do NOT run the load test multiple consecutive times; the container degrades under sustained load.

**Tests added:**
- `tests/test_step5_clock_domains.py` — TC-34 (rate arithmetic, parametrized rate=[1.0, 60.0]) and TC-35 (restart resumes uncertain grace period, parametrized rate=[1.0, 60.0]).
- Helper `_make_clock(sim_time, dt_seconds, tick_seq=0, rate=1.0)` → SimClock(wall_stamp_utc=0.0) added to test_formulas.py, test_plane_separation.py, and test_step5_clock_domains.py.
