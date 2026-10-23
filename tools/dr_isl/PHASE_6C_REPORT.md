# Phase 6c — stopped at 6c.5

**Status:** STOP at the first full-suite gate. The first suite run, with
`PYTHONHASHSEED=1`, added one failure relative to
`tools/dr_isl/PHASE_5B_FAILING_TESTS.txt`. The required
`PYTHONHASHSEED=987654321` suite was not started. No Phase 6c commits were
created, no stash was dropped, and the dev workflow was not restarted.

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

## 6c.6 — not run

The gate failed, so implementation/test/docs/report commits, stash drops, and
workflow restart were not performed. To leave application files at the base,
the applied D4/6c candidate snapshot is preserved at
`refs/dr-isl/phase6c-stopped-candidate`:
`f0d55f26c7bf852d9f50b0e09c2e316f273f93b1`. Application paths have no diff
against `f6ac658`. Current HEAD is
`b6457716ea173a4f62aa46632ce3b3549f697fcc` (`Update phase 6b report details`).
The original stash stack was not changed: `a148238` remains at `stash@{0}` and
`52ee2a8` remains at `stash@{1}`. No publish, deploy, push, or workflow restart
was performed.
