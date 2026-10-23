# Phase 6b — STOP report

**Status:** STOP at 6b.5 after the first full-suite run. It found one added failure, so the required second `PYTHONHASHSEED` suite run and all commits were not performed. No Phase 6b code/test commit was made; no workflow restart, publish, deploy, or push was performed.

## Base and preserved candidate

- Application base: `f6ac65849906df7ab33654a0b126a79c9af23d04`.
- HEAD at the stop: `3cdcca033e5f33c7cf69f12e1f8e1d55e89b270c` (report-only history atop the application base).
- After the suite gate failed, the Phase 6b candidate was stashed as `stash@{0}`: `a1482386e473eac911686103e9946572aed39d56` (`DR-ISL Phase 6b candidate stopped at 6b.5 added suite failure; preserve D4 work`).
- The original candidate stash was preserved unchanged and shifted to `stash@{1}`: `52ee2a88971cfd122a654352e20c6442d15e150c`.
- `git diff f6ac658 -- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim` was empty after stashing. No S10 scenario edits were made.

## 6b.1 — base behavior before applying the candidate

Base-demo seed-42 baseline arm, separate processes with `PYTHONHASHSEED=1`, `987654321`, and `1729`:

- Phase-5b-contract physical hash in all three runs: `f1ebd90e589a217bbaf85264a2153a268a493a8b644c75ebbe74fd89c7f5def6`.
- Informed arm hash in all three runs: `72cc28766574a78c44913d389207bc6cca268ac1bf29b15abd148c63af334754`.
- All-field differences were limited to `wall_stamp_utc`: 1,440/1,440 ticks, first at tick 1 (`sim_time=5.0 s`). All other tick fields were identical. No energy, fuel, served/unserved, curtailment, SoC, start, or dispatch field differed.
- Historical hashes `e9a25202a069acdb648779981f07bc27e1cbe53a5a2b44e1571bd8724912a5f9` / `34bc07cdebda13c4e07bc990408745fbeeb5f916248cd7159d9f8fd656ee2702` were not reproduced under those three hash-seed values. See `phase6b/6B_1_BASE_HASHSEED_COMPARISON.json` for the exact tick hashes and values.

## 6b.2–6b.3 — candidate focused checks and protected records

- Focused MCP tests: **3 passed**; the H1 bounded-forecast-history determinism test: **1 passed**; TC-ISL-34–40: **7 passed**.
- Base demo, seed 42, `reuse_cache=false`: baseline/informed physical hashes `f1ebd90e…f5def6` / `72cc2876…334754`; compare_runs **PASS, 10/10**. Unserved `0.351692658 / 0.020719074 MWh`; turbine fuel `714.363019086 / 665.398247704 MMBtu`; curtailment `8.136511735 / 5.278943188 MWh`; peak unserved `22.309362466 / 7.52325057 MW`.
- H1-24h: physical hashes `c4fa3b35…85fc20` / `437d4801…8a264`; compare_runs **PASS, 10/10**. Baseline/informed recorded and measured starts `12/12` each; both arms match the Phase 6 reference.
- H2-24h: physical hashes `60344137…217f` / `17954e94…a9fba`; compare_runs **PASS, 10/10**. Baseline start reconciliation `11/11`; informed `14/14`; both arms match the Phase 6 reference.
- Full metric payloads and focused results are in `phase6b/6B_2_BASE_DEMO_GATE.json`, `6B_2_H1_GATE.json`, `6B_2_H2_GATE.json`, `6B_2_FOCUSED_TESTS.json`, and `6B_3_FOCUSED_TESTS.json`.

## 6b.4 — reproducibility

- Fresh null-seed draws across `PYTHONHASHSEED=1` and `987654321`: seven of eight scenarios had equal physical hashes and matched their pinned Phase-5b hashes. `demo-islanded-ramp` drew different recorded root seeds (`5887540250213314481` and `6131235703570113716`) and corresponding physical hashes (`81c649616d3a82c9107b46f5c779d1a214a4f44e6142a1253d3f913f58544df7` and `4a4f51d2062a6bf7ca17ffc792752a932f0f5d42a17db80617ac0d75077fb119`). This was a comparison of separate random null-seed draws, not a replay of the same recorded seed.
- Replaying each of the eight scenarios with the first run's recorded root seed in a separate process produced identical physical hashes for all eight; evidence: `phase6b/6B_4_RECORDED_SEED_REPLAYS.json`.
- Seed-42 study pairs across both hash seeds were identical in full metrics, physical hashes, and comparison payloads. Both process runs had PASS 10/10 for each pair:
  - Base demo: baseline `f1ebd90e…f5def6`, informed `72cc2876…334754`.
  - H1-24h: baseline `c4fa3b35…85fc20`, informed `437d4801…8a264`.
  - H2-24h: baseline `60344137…217f`, informed `17954e94…a9fba`.
- Compact and independent-run evidence: `phase6b/6B_4_SEED42_CROSSPROCESS.json`, `6B_4_INDEPENDENT_NULL_SEED_DRAWS.json`, and `6B_4_RECORDED_SEED_REPLAYS.json`.

## 6b.5 — full-suite STOP gate

Real-package suite command: `PYTHONHASHSEED=1 PYTHONPATH=<package-root> python -m pytest -q --junitxml=tools/dr_isl/phase6b/SUITE_HASHSEED1.xml`.

Result: **2,221 passed, 16 failed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed** in `988.08 s` (pytest exit 1). Compared with `tools/dr_isl/PHASE_5B_FAILING_TESTS.txt` (15 failures): **added 1, removed 0, remaining 15**. Added node ID:

`tests/test_mcp_server.py::test_mcp_cache_hit_and_build_parity_error`

This added failure triggered the required STOP. The `PYTHONHASHSEED=987654321` full-suite run was not started. The single completed run's failure list is `tools/dr_isl/PHASE_6B_FAILING_TESTS.txt`; this is not a two-run aggregate.

Suite artifacts: `phase6b/SUITE_HASHSEED1.log`, `phase6b/SUITE_HASHSEED1.xml`, `phase6b/SUITE_HASHSEED1_FAILING_TESTS.txt`, and `phase6b/6B_5_HASHSEED1_SUMMARY.json`. No file in `phase6b/` exceeds 50 MB.

## Final state

- No commits made; in particular, no D4 implementation, D4 test, or report-only commit was made because 6b.5 failed its gate.
- The application tree is restored to the base (`git diff f6ac658 -- <package-root>` empty). The candidate is preserved in the new stash listed above; the original stash remains intact.
- The only current uncommitted files are this report and Phase 6b evidence/failing list. No `*.channels.csv` or raw files under `attached_assets/supercloud/` are tracked. The existing S10 scenario JSON remains tracked as before.
- No developer workflow restart was performed after the STOP.
