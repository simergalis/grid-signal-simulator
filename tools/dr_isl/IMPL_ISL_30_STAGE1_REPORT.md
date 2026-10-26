# IMPL-ISL-30/31 — Stage 1 report

Base design: `tools/dr_isl/IMPL_ISL_30_DESIGN.md` at `2b26591`.
Scope completed: controller changes and submit-time plumbing only. No S10
regeneration, synthetic submit times, identity-version change, full suite, or
acceptance scenario runs.

## Implementation

- `P/runtime/turbine_commitment.py:23–31, 299–311`: added the
  `PROPOSED_HERE` 1,800-second announcement cap and the single announcement
  resolver. With `submit_time_s`, announcement is
  `max(submit_time_s, start_time_s - cap)`; without it, the existing lead is
  capped by the same value.
- `P/runtime/turbine_commitment.py:702–809`: shared start-timing wrapper,
  thermal-aware start horizon, and per-unit return-to-service (RTS) calculation.
  RTS uses current output-to-minimum-stable rundown, unload tail, configured
  minimum-down time, the asset module's thermal-tier start resolver, and
  rated-MW ramp time. Missing timing inputs fail closed for a decommit proposal.
- `P/core/asset_modules.py:1073–1104`: `start_timing_at()` accepts an optional
  projected offline time for the RTS preview. Its default continues to use the
  actual recorded stop time; `command_start()` still calls the same resolver at
  `:1123–1125`.
- `P/runtime/turbine_commitment.py:830–979, 1385–1502`: core decommit proposals
  receive the RTS/announced-job veto. Refusal records carry the RTS terms,
  triggering announced event IDs/times, forecast demand, remaining capacity,
  reserve deficit, BESS allowance, and sensitivity threshold. Profile sampling
  associates an event with the first sample at or after its start, including
  starts between sample boundaries.
- `P/runtime/turbine_commitment.py:1010–1100`: removed forecast-originated stop
  creation. Forecast evaluation can still request a start and run preload; a
  stop is now considered only when the core proposes decommit.
- `P/api/schemas.py:219–225`: added optional `submit_time_s` to workload events;
  absent values are omitted from serialized scenario specs.
- `P/core/models.py:137–194` and `P/runtime/scenario_factory.py:1683–1725`:
  carried the optional submit time into each `WorkloadSignal`.
- `P/api/schemas.py:1761–1773` and `P/runtime/scenario_factory.py:2051–2063`:
  added and wired `turbine_forecast_announcement_cap_seconds`, default
  1,800 seconds, marked `PROPOSED_HERE`. The unchanged default is omitted from
  canonical dumps so existing base/H identity payloads retain their previous
  shape; non-default values remain serialized.
- Shared construction remains centralized at
  `P/runtime/scenario_factory.py:670–678`. REST builds through it at
  `P/api/routes/runs.py:697–704`; `StudyRunExecutor` does so for probe and run
  contexts at `P/study_harness/executor.py:395–401, 463–470`; MCP calls the
  executor at `P/mcp_server/server.py:575–584`. No separate event plumbing path
  was added.

## Tests

New IDs used: **TC-ISL-80–89 and TC-ISL-91**. The collision search found no
existing tests with those IDs.

- `P/tests/test_isl30_stage1.py:121–319`: covers no forecast-originated stop;
  core decommit veto for an announced job within RTS; no new veto without an
  announced job; per-unit RTS; fail-closed missing terms; explicit and fallback
  announcement times; baseline-mode isolation; the S10 16,160–16,171-second
  announcement case; hot/warm/cold start horizons; cold-start request timing;
  and submit-time serialization into `WorkloadSignal`.
- `P/tests/test_addendum_h_phase2a_commitment.py:162–190, 403–426, 832–864`:
  updated TC-ISL-112, TC-ISL-118 and TC-ISL-133, whose previous assertions
  expected forecast-originated stops. They now assert that forecast evaluation
  does not originate stops, citing IMPL-ISL-30.
- `P/tests/test_d6e_forecast_active_job_power.py` remains unchanged and was run
  to verify the active-job power and measured-history behavior.

Focused verification from the package root:

| Set | Result |
|---|---:|
| New tests, D6e active-job tests, Addendum H Phase 2a, fuel-cell commitment, Addendum H Phase 2b Stage 2 | 60 passed, 1 existing warning |
| D6g study-harness tests TC-ISL-67/68/71/72/73 and MCP tests TC-ISL-65/66/70 | 8 passed, 1 existing deprecation warning |
| Combined final focused run | **68 passed, 0 failed, 2 warnings, 30.23 s** |
| `py_compile` for changed Python modules and tests | passed |

The MCP test TC-ISL-66 uses its existing `end_sim_time=5.0` override for the
baseline and informed API-path checks. No standalone acceptance scenario run
was made. No full suite was run, as requested.

The unchanged-default serialization was checked by the existing
`test_tc_isl_73_existing_base_and_h_identities_match_prechange_evidence`,
which passed in the final run.

## Commits

- `f8deefc` — Replit Agent-created implementation commit; initial implementation
  files: `P/api/schemas.py`, `P/core/asset_modules.py`, `P/core/models.py`,
  `P/runtime/scenario_factory.py`, `P/runtime/turbine_commitment.py`.
- `7f06cfc` — `IMPL-ISL-30: retain event index and preserve default identities`;
  final event-index retention and profile-boundary matching, plus unchanged-
  default serialization.
- `e2e5e64` — `IMPL-ISL-30: test announcement timing and decommit veto`;
  tests only.
- The report is committed separately after this update.

No publish, deploy, push, scenario edit, or full-suite run was performed.
