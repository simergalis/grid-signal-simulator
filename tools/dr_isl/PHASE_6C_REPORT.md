# Phase 6c — resumed validation complete

**Initial status:** STOP at the first full-suite gate, before Lloyd clarified
the IMPL-SSH-07 waiver. The resumption and its final results are recorded
below; they supersede the initial stop for Phase 6c completion.

## 6c.1 — diagnosis

`tests/test_mcp_server.py::test_mcp_cache_hit_and_build_parity_error` failed
because the cache-hit assertion expected `result["cache_hit"] is True` but
received `False` when the repeated request omitted its seed. The D4 seed
resolver draws a fresh root for a null seed before identity formation; the
per-request identity therefore differs. This was the null-seed cache miss
specified as the continue condition in 6c.1, not a build-parity failure.
Literal trace and traceback: `phase6c/6C_1_DIAGNOSIS.md` and
`phase6c/6C_1_CACHE_FAILURE.log`.

## 6c.2–6c.3 — cache rule and tests

- Implemented one shared `seed_cache_bypass_reason` policy in
  `study_harness/executor.py`; the MCP start path uses it to bypass cache lookup
  when `reuse_cache=true` and the requested seed is null.
- The response reports `cache_hit=false` and
  `cache_bypass_reason="seed_not_provided"`. The fresh run records its drawn
  seed; a later request supplying that recorded seed can hit the cache.
- TC-ISL-41, 42, and 43 cover explicit-seed reuse, fresh null-seed requests,
  and replay/cache reuse by a recorded seed. The existing parity half of the
  cache test remains unchanged.
- Focused test result: 53 passed, 0 failed, 1 warning. Evidence:
  `phase6c/6C_3_CACHE_TESTS.json`, `phase6c/6C_3_CACHE_TESTS.log`, and
  `phase6c/6C_4_FOCUSED_TESTS.log`.

## 6c.4 — re-checks

- Base demo, H1-24h, and H2-24h seed-42 gate: all compared saved metric and
  physical-hash values matched; each `compare_runs` result was PASS 10/10.
  Evidence: `phase6c/6C_4_SEED42_GATE.json`,
  `phase6c/6C_4_BASE_H1_RECORD_CHECK.json`, and
  `phase6c/6C_4_H2_RUN.json`.
- Base-demo seed-42 baseline and informed runs across `PYTHONHASHSEED=1` and
  `987654321` had identical metrics, identities, and physical hashes. Baseline
  hash: `f1ebd90e589a217bbaf85264a2153a268a493a8b644c75ebbe74fd89c7f5def6`;
  informed hash:
  `72cc28766574a78c44913d389207bc6cca268ac1bf29b15abd148c63af334754`.
  Evidence: `phase6c/6C_4_BASEDEMO_HASHSEED_COMPARISON.json`.

## 6c.5 — full-suite STOP

The real-package suite under `PYTHONHASHSEED=1` completed in 729.37 s:
**2,224 passed, 16 failed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests
passed**. JUnit recorded 2,266 test cases, including 16 failures, 26 skipped
entries (3 skips plus 23 xfails), and 0 errors.

Compared with the 15 known Phase 5b failing node IDs: **15 remaining, 0
removed, 1 added**:
`tests/test_gpu_load_profile.py::test_gpu_load_profile`.
Its literal failure was at `tests/test_gpu_load_profile.py:169`, reached from
line 284: at phase 3, `sim_t=2400.0s`,
`gpu_load_fraction=0.5 expected 0.1`; absolute difference `0.4`, tolerance
`1e-6`. This is an added node ID under the Phase 6c.5 comparison, so the gate
requires stopping even though the test was previously observed as
order-dependent in earlier work. No base rerun or second hash-seed run was
performed in Phase 6c.

Full run evidence: `phase6c/6C_5_1.log`,
`phase6c/6C_5_1.xml`, `phase6c/6C_5_1_SUMMARY.json`, and
`phase6c/6C_5_1_FAILING_TESTS.txt`. The consolidated first-run failure list is
`PHASE_6C_FAILING_TESTS.txt`.

## 6c.6 — initial stop state

At the initial 6c.5 stop, implementation/test/docs/report commits, stash drops,
and workflow restart had not been performed. Application paths remained at
`f6ac658`; the candidate was preserved at
`refs/dr-isl/phase6c-stopped-candidate` (`f0d55f26c7bf852d9f50b0e09c2e316f273f93b1`).
The initial HEAD was `b6457716ea173a4f62aa46632ce3b3549f697fcc`. This is
historical status only; the 6cR resumption below records completion.

## 6cR.1 — waived GPU test confirmation

- `tests/test_gpu_load_profile.py::test_gpu_load_profile` passed in isolation
  on the candidate: 1 passed in 19.11 s; measured wall runtime 21 s
  (`phase6c/6cR_1_gpu_candidate.log`, `.json`). The waiver applies only to
  this node ID.
- The test uses `http://localhost:22126` (`P/tests/test_gpu_load_profile.py:46`).
  Before the candidate was applied, PID 2865 was running
  `python3 -m uvicorn api.app:app --host 0.0.0.0 --port 22126 --log-level info`
  from the simulator package directory, start reported as `Fri Oct 23
  11:08:13 2026`. The base commit was `f6ac65849906df7ab33654a0b126a79c9af23d04`
  (`2026-10-23T04:25:57Z`); its `runtime/scenario_factory.py` SHA-256 was
  `6833036473950d264f6393b92df3abfa5e3c5664fa06effe15d78d7534c4b966`.
  The server predates candidate application and was not restarted for this
  isolated run. Because the candidate test passed, the conditional base
  isolation run was not required. Evidence: `phase6c/6cR_1_SERVER.json`.

## 6cR.2–6cR.3 — second suite and waiver comparison

- `PYTHONHASHSEED=987654321` real-package suite completed in 743.31 s:
  **2,224 passed, 16 failed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests
  passed**. JUnit: 2,266 cases, 16 failures, 26 skipped entries (3 skips plus
  23 xfails), 0 errors.
- The second run has the same 16 failing node IDs as the first (`PYTHONHASHSEED=1`):
  the 15 Phase 5b failures plus the waived
  `tests/test_gpu_load_profile.py::test_gpu_load_profile`. Added beyond the
  Phase 5b list plus the waiver: 0. Removed: 0. Difference between runs: 0.
  Gate: PASS under the one-node waiver.
- The consolidated `PHASE_6C_FAILING_TESTS.txt` now contains both complete
  node-ID lists and identifies the single waiver. Run 2 summary, list, log and
  JUnit are under `phase6c/6cR_2_987654321_*`.

## 6cR.4 — committed candidate and workflow verification

- The final committed source/docs/runner tree matches
  `refs/dr-isl/phase6c-stopped-candidate` exactly for `P/`, the D4 contract
  document and the pinned baseline runner (`git diff` empty).
- Replit checkpoint `a6735de` (`Update agent registry and expand API run
  management functionality`) captured the main D4 source changes, existing
  stale-test edits, D4 documentation, baseline-runner update and part of the
  6cR evidence in one checkpoint. It was not rewritten. The explicit helper
  modules were committed as `2d5f99c` (`D4: deterministic per-run seed
  resolution, physical identity, and null-seed cache bypass`); TC-ISL-34–40
  were committed separately as `707ddc7` (`D4 tests: add TC-ISL-34–40
  reproducibility coverage`). This is the only commit-structure deviation:
  the documentation and existing-file test edits are in the automatic
  checkpoint rather than separate documentation/test commits.
- Main source line ranges in `a6735de`:
  `P/api/routes/runs.py:76–79,359–382,435,474,521,676,695–697,719–727,813–814`;
  `P/api/schemas.py:2837–2842,2946–2947`;
  `P/mcp_server/server.py:42,413–424,429,457–479,504,522–524,535,543–544,564–566`;
  `P/runtime/scenario_factory.py:234–244,304–306,386–414,441,454–461,510–512,
  578–589,611–613,628–630,673–676,701–708,1120–1127,1165–1167,1365–1397,
  1672–1700,1876–1878,2033–2035,2076–2078,2095–2097,2188,2233–2252`;
  `P/runtime/run_manager.py:49,82–88,1933–1934,2594,2652–2669,2697–2703,
  3199,3283–3285,3692–3705,3723–3726`;
  `P/study_harness/executor.py:20–25,50–68,101–102,329–340,346,350–357,
  386,390,399–423,434,438,449–452,568–569,574–578,584–592,596,604–605,609,
  621–625,631,635,644,646,655,657`.
  Other source ranges: `P/advisory/agent_registry.py:71,76,80–83,160`;
  `P/advisory/agents/base.py:123,164`; `P/core/deident.py:134–139,149,271,394,
  462–465,482`; `P/renewable/solar.py:643–646`; `P/runtime/cluster_gen.py:
  230–233,246,254,272,279`; `P/runtime/stressor_gen.py:198–203`;
  `P/tests/test_mcp_server.py:19,187–189,216,275–399,566–571,618–620,627,
  679–683`; `P/tests/test_study_harness.py:22–25,339–362,386–387`;
  `docs/d4-seed-cache-contract.md:1–24`;
  `tools/dr_isl/baseline_runner.py:3–6,14,23,42,88–91,98,101,115,117–123,
  139,142–145,157,166`.
- `2d5f99c` adds `P/core/physical_identity.py:1–83` and
  `P/runtime/seed_resolution.py:1–139`. `707ddc7` adds
  `P/tests/test_dr_isl_phase6_reproducibility.py:1–192`.
- Workflow `artifacts/gridsignal: web` was restarted. The candidate Uvicorn
  process is PID 11989, started `Fri Oct 23 16:24:16 2026`; current and
  committed `P/runtime/scenario_factory.py` SHA-256 both equal
  `3f8f697bf4f944ef8814bc20386535d1a8755558d698078ed8ad60de6e48f024`.
  `GET http://127.0.0.1:22126/` returned **200**. After restart,
  `test_gpu_load_profile` passed again: 1 passed in 19.36 s; wall runtime
  21 s (`phase6c/6cR_4_gpu_after_restart.log`, `.json`).

## 6cR.5 — seed sensitivity, tracking and final state

- The template's seed-dependent physical solar output is caused by the
  `solar_sim` consumer: the run-seed resolver derives its consumer seed at
  `P/runtime/seed_resolution.py:64–71` and includes `solar_sim` in the consumer
  set at `:87–94`; the run route applies it at `P/api/routes/runs.py:723–727`;
  `SolarSim` constructs `random.Random(seed)` at
  `P/renewable/solar.py:618–622`, and run-manager solar output is read at
  `P/runtime/run_manager.py:2674–2681`. With a null root seed, the recorded
  root draw changes this consumer seed. No template fix was made.
- No `*.channels.csv` and no `attached_assets/supercloud/` file is tracked.
- Before cleanup, the committed source/docs/runner diff against the preserved
  candidate ref was empty. After the implementation, tests and docs were
  committed, stash `a148238` and stash `52ee2a8` were dropped, and
  `refs/dr-isl/phase6c-stopped-candidate` was deleted. The report-only commit
  contains this report and the two-run failing-ID list; the after-restart GPU
  JSON summary is at `phase6c/6cR_4_gpu_after_restart.json`. The JUnit, JSON
  summary and failing-ID list for run 2 are already committed with the
  checkpoint.
- No `*.channels.csv` or SuperCloud file is tracked; the tracked-path query
  returned no matches. No publish, deploy or push occurred. No D5 or D6 work
  was started. After the report-only commit, `git status --short` was empty.
