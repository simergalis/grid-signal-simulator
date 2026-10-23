# Phase 6c durable progress

## 6c.1 — diagnosis

- `test_mcp_cache_hit_and_build_parity_error` failed in isolation: assertion
  `result["cache_hit"] is True`, actual `False`; full traceback:
  `6C_1_CACHE_FAILURE.log`.
- The fixture cached an identity with `seed=None`; the candidate resolves an
  omitted seed to a new `secrets.randbits(64)` root before forming the request
  identity (`runtime/seed_resolution.py:43–47`,
  `mcp_server/server.py:456–469`). The cache key consequently differs.
- This is the specific null-seed cache miss allowed by 6c.1; no build-parity
  behavior caused the failure. Proceeded to 6c.2.

## 6c.2–6c.3 — implementation and focused tests

- Added the shared `seed_cache_bypass_reason` policy in
  `study_harness/executor.py`; MCP start uses it to skip lookup and passes the
  same effective cache flag to execution. Fresh null-seed results are still
  stored under their drawn-seed identity for later explicit replay.
- Exact response field/value for `reuse_cache=true` and omitted seed:
  `cache_bypass_reason="seed_not_provided"`; response also has `cache_hit=false`.
- `TC-ISL-41–43` are free and used: explicit-seed cache reuse, null-seed fresh
  requests with different recorded roots, and cache reuse via a previously
  recorded root. Test results: `6C_3_CACHE_TESTS.json` and
  `6C_3_CACHE_TESTS.log`.
- Existing cache/build parity test now uses explicit seed 42 for its cache-hit
  fixture and request; its build-parity half is unchanged.

## 6c.4 — protected-record gate

- Base demo seed-42 run: exact reference values and physical hashes matched;
  compare_runs was PASS with all 10/10 conditions true. See
  `6C_4_SEED42_GATE.json`.
- Base demo and H1-24h raw records now match every saved reference metric and
  physical hash; each compare_runs result is PASS 10/10. See
  `6C_4_BASE_H1_RECORD_CHECK.json`.
- H2-24h also matches every saved reference metric and physical hash;
  compare_runs is PASS 10/10. Combined gate: `6C_4_SEED42_GATE.json`.
- Base-demo seed-42 baseline and informed arms were run in separate processes
  with `PYTHONHASHSEED=1` and `987654321`; metrics, identities, and physical
  hashes matched each other and the Phase 6b hashes. See
  `6C_4_BASEDEMO_HASHSEED_COMPARISON.json`.
- Focused MCP, study-harness, and D4 reproducibility tests: 53 passed, 0
  failed, 1 warning (`6C_4_FOCUSED_TESTS.json`).
- Full suite under `PYTHONHASHSEED=1` completed with 2,224 passed, 16 failed,
  3 skipped, 23 xfailed, 54 warnings, and 3 subtests passed in 729.37 s.
  Compared with the 15 Phase 5b failures, 15 remain, none were removed, and
  `tests/test_gpu_load_profile.py::test_gpu_load_profile` is an added failure.
- Per 6c.5, STOPPED before the second hash-seed suite: no second run, commit,
  stash drop, or workflow restart was performed. See `PHASE_6C_REPORT.md` and
  `../PHASE_6C_FAILING_TESTS.txt`.
