# DR-ISL Phase 4 reserve — preflight STOP

Date: 2026-10-22.
Application base: `ae49aaab89564ccf2ef42d505e021641484d0d3a`.
Scope: D2-r / D1-b / IMPL-ISL-2, not IMPL-ISL-17.

## Status

**Stopped at 4.0 preflight; no implementation candidate created.**

Saved the source-level design note:
`tools/dr_isl/PHASE_4_RESERVE_DESIGN.md`.
It documents current floor terms/callers, emergency release, thermal
startup durations, live grid-forming source semantics and the distinct
read-only advisory bridge escalation.

## Blockers

1. Required tracking target `P/mcp_server/main.py` does not exist.
   Existing CLI filename is `P/mcp_server/__main__.py`.
   No substitute was added and no file was created/renamed.
2. STARTING turbines fall within the stated not-on-bus/not-failed
   population, but `start_eligibility` returns `"state"` for them
   (`P/core/asset_modules.py:1061–1062`). They subsequently become
   SYNCHRONISED (`1214–1220`), not eligible for a new start. Clarification
   is required on remaining startup countdown versus OFFLINE-only
   restart candidates.
3. D9b's current `winning_term` has only diesel/depth labels
   (`P/runtime/build_warnings.py:37`). Clarification is required for
   attribution-only support of D2-r without changing the warning trigger
   or no-cap/no-reject behavior.

## Literal tracking preflight values

SHA-256 before any tracking operation:

| File under P | Exists | SHA-256 |
|---|---|---|
|tests/test_task_630_100mw_fuel_cell_scenario.py|yes|`9898e80b75e0c4734ae8143de6728ce46a7e6e65d8ef05a8de068f2b9744ca30`|
|knowledge/behind-the-meter-market-context.md|yes|`f3b52a3fdfca0f9c7c49ee3bc41e28dcb4a4c349f9e560f4f4ff2411fbf2aa63`|
|knowledge/gridsignal-operator-benefits.md|yes|`57a098dfe8bc563eb435e6a637284571cee02a0cf4d8f1763944541817fa43ac`|
|mcp_server/__init__.py|yes|`688a30c32f0fff1ba2a9bbf22054c658c15c54eb6453e145dff7b5e7f5ce5851`|
|mcp_server/main.py|no|not computable: file absent|
|mcp_server/__main__.py, potential correction only|yes|`f62076518bb1c16c668be4376b6c379087b2f4dd5dc79ddd6b3aca08bf725fe9`|

No after-tracking values or tracking commit exist: 4.6 was not performed.

## Work not performed

- 4.1/4.2 implementation: not started.
- 4.3 tests: not added, updated or run.
- 4.4 R1–R4 runs: not started; no protected record remeasured.
- 4.5 suite: not run. The existing housekeeping result is not relabeled
  as a Phase 4 result.
- 4.6 force-add: not performed; database not added.
- 4.7 implementation/test/tracking commits: none.

## Safe state

Verified `git diff --quiet ae49aaa -- P/core P/runtime P/api P/tests
P/config/scenarios` returned exit **0** before writing these documents.
No application candidate exists, so there is no new stash reference.
Existing stashes were not applied or changed. Only these two report/design
documents are new.

No publish, deploy, push, workflow restart or Phase 5 work.
STOP pending the three clarifications.
