# DR-2026-10-20-ISLAND-COLLAPSE — Phase 2b STOP report

## Status

**STOPPED during pre-fix diagnostic verification of item 2b.4.**
No application change was made. No fix, test edit, scenario edit, parameter
change, new constant, commit, publish, deployment or push was performed.
No Phase 3 work started.

This is a baseline protocol discrepancy, NOT an established application-engine
regression. The required historical curtailment number was not reproduced by
the unchanged persisted-runner execution described below. Per HARD CONSTRAINT 4,
no replay/spec/controller adjustment was made to force agreement after detection.

## Base and unchanged runner
```json
{
  "requested_base": "86ab0efab0b8d8597182100cd88565e6036033f8",
  "actual_head": "94dcee7dd65c486848e32225139fb015e5990f3b",
  "runner_sha256": "12320f7c74c42406cc6eca862b9621621f733c2d9ad94e3ecb0c80652af6593a"
}
```

HEAD differs from requested base only by the previously committed Phase-1c report.
`git diff 86ab0ef HEAD --name-status`:
```text
A	tools/dr_isl/PHASE_1C_REPORT.md
```

The application package diff against 86ab0ef is empty.
The persisted runner is unchanged; its SHA-256 is printed above.

## Diagnostic execution and literal STOP condition

Scratch adapter: `/tmp/DR-ISL-phase2b/scenario_checks.py`.
- Lines 80–86 call `StudyRunExecutor._expanded_spec` and `_probe` under pinned
  factory/fabric/wall-clock wrappers and save the generated replay.
- Lines 89–94 select the conventional (`baseline`) or informed arm and insert
  the generated WorkloadSignal event list, as in the retained Phase-1b protocol.
- Lines 98–118 adapt validated in-memory specs, attach demand replay, and collect
  live metrics through the in-memory sink.
- The adapter calls the UNCHANGED `tools/dr_isl/baseline_runner.py:91–158`;
  that runner invokes `RunManager` and writes every tick.

One conventional repetition completed. The command then returned a tool/process
error before producing a second repetition or the final collector output:
`Error: No process for id: "I0W6P09WISVKJAJ5AYUG0" found`.
No cause for that process/tool error is established here; it is not reported as
an engine exception. No scenario-check or baseline-runner process remained in
the subsequent process listing.

The completed first stream was inspected read-only. Its raw curtailment energy is
the ordered sum of `p_dispatch_curtailed_mw * 5.0 / 3600.0` over all 1440 ticks,
the same term used in retained Phase-1b `/tmp/DR-ISL-phase1b/runs.py:106–112`.
This yielded the required STOP condition before any application edit:
```json
{
  "completed_conventional_repetitions": 1,
  "completed_informed_repetitions": 0,
  "completed_ticks": 1440,
  "dispatch_curtailment_mwh_observed": 15.267058272851246,
  "dispatch_curtailment_mwh_required": 4.79477329394151,
  "dispatch_curtailment_mwh_difference": 10.472284978909736,
  "exact_equality": false,
  "balance_failure_count": 0,
  "balance_failure_ticks": [],
  "summary": {
    "scenario_id": "scenario-uneven-multisched-01",
    "repetition": 1,
    "physical_sha256": "67f2516cf5ede24ae11a15d1aae1f949ce19a812a5965b6c9226b84a3b2b51ac",
    "tick_count": 1440,
    "failing_tick_count": 0,
    "failing_ticks": [],
    "spec_island_mode": true,
    "verification_modes": [
      "islanded_verified"
    ],
    "tolerances_mw": [
      1.9913e-14
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ]
  }
}
```

This measurement is from the harness-prepared replay THROUGH the persisted
RunManager runner. It must not be presented as a successful reproduction of the
historical direct-step study-harness execution.

## Saved-input and trajectory comparison — reads only, no additional runs

Retained historical execution:
`/tmp/DR-ISL-phase1b/runs.py:86–98` builds a context and uses `ctx.step()` directly;
`:155–173` obtains the harness probe and prepares the two arms.
New execution uses persisted runner `tools/dr_isl/baseline_runner.py:130–147`,
including `RunManager.start_run`.

The saved probe data comparisons are:
```json
{
  "phase1b_probe_sha256": "35968ca0d879d21a23ed9082f8dee6e6a682a00a18fcff762c328875ca5e6185",
  "phase2b_probe_sha256": "13f636e83d1a7bfb49f7558434a1fdcf697d01d387c423b3708db2ceadf12e00",
  "phase1b_event_count": 237,
  "phase2b_event_count": 237,
  "phase1b_demand_count": 1440,
  "phase2b_demand_count": 1440,
  "demand_arrays_identical": true,
  "events_identical_excluding_site_id": true,
  "phase1b_first_site_id": "site-for-phase1b-baseline-probe",
  "phase2b_first_site_id": "site-for-phase2b-probe"
}
```

The demand arrays are exactly equal. Event content is equal after excluding
the printed site_id difference. Therefore the replay-demand values do not
explain away this discrepancy. The site-id distinction alone is not established
as a physical cause. Full input/protocol equivalence and the cause of the
trajectory divergence have NOT been proven.

Comparing selected physical fields of the retained Phase-1b stream and the new
completed stream gives the first difference at:
```json
{
  "tick": 9,
  "sim_time_seconds": 45.0,
  "compared_fields": [
    "sim_time_seconds",
    "p_compute_demand_mw",
    "p_cooling_demand_mw",
    "p_demand_mw",
    "p_generation_mw",
    "p_served_mw",
    "p_unserved_mw",
    "turbine_output_mw",
    "bess_output_mw",
    "bess_soc_fraction",
    "p_dispatch_curtailed_mw",
    "frequency_hz",
    "committed_rated_mw"
  ],
  "differing_values": {
    "turbine_output_mw": {
      "phase1b": 17.5,
      "phase2b": 18.85204445111111
    },
    "bess_output_mw": {
      "phase1b": 1.3520444511111087,
      "phase2b": 0.0
    },
    "bess_soc_fraction": {
      "phase1b": 0.952491679897726,
      "phase2b": 0.9525243629460044
    }
  }
}
```

This is a selected-field comparison, not a claim that every TickResult field
before tick 9 was equal. Run identifiers and excluded advisory fields are not
physical-hash-equivalent across these two historical protocols.

## 2b.1 — IMPL-ISL-10

NOT IMPLEMENTED. The accepted stale-curtailment diagnosis remains in the Phase-1b
report; this turn did not re-run its tests. No generation, curtailment producer,
supply reconciliation or ledger code was edited.

## 2b.2 — D7

NOT IMPLEMENTED. No served/unserved reconciliation was edited.
The requested exhaustive downstream-consumer inventory was not completed:
the diagnostic STOP condition was reached before implementation and inventory work.

## 2b.3 — Tests and TC IDs

NOT RUN OR EDITED. A text collision search of tests and tools found no
TC-ISL-15/16 match, but no IDs were assigned and no test was created.
The two stale tests and all Addendum G tests remain unchanged.
No passing Stage-3 result is claimed.

## 2b.4 — Scenario and study checks

- Conventional study replay: one completed repetition, 1440 ticks, 0 balance
  failures; raw curtailment 15.267058272851246 MWh, required 4.79477329394151.
- Second conventional repetition: no completed result.
- Informed arm: not run; no reproduction of required 0.3700526648755099 is claimed.
- Complete interval-exposure/attributable fuel comparisons: not available; the
  interrupted adapter had not finalized/persisted its collectors.
- SJ-1, demo-islanded-ramp, S10, turbine-01, hybrid and FC/BESS/diesel catalogue
  baseline/post-fix pairs: not run in this phase.
- No post-fix hashes or unchanged-fuel assertions are claimed.

## 2b.5 — Full suite

NOT RUN. No pass/fail count, no comparison against the historical 17-failure set,
and no expected two-test removal is claimed. A scratch pytest capture plugin was
prepared but never invoked.

## 2b.6 — Commit and literal full diff

No Phase-2b commit exists. Current HEAD remains:
`94dcee7dd65c486848e32225139fb015e5990f3b`

`git diff HEAD -- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim` literal stdout:
```text
```

`git diff HEAD -- tools/dr_isl/baseline_runner.py` literal stdout:
```text
```

Both diff blocks are empty. There are no production/test hunks to report.

Repository output created in this phase:
- `tools/dr_isl/PHASE_2B_REPORT.md` — this report, uncommitted.

Scratch scripts and evidence:
- `/tmp/DR-ISL-phase2b/scenario_checks.py`
- `/tmp/DR-ISL-phase2b/suite_capture.py` (not invoked)
- `/tmp/DR-ISL-phase2b/pre_study.log`
- `/tmp/DR-ISL-phase2b/pre/study/probe.json`
- `/tmp/DR-ISL-phase2b/pre/study/baseline/engine.log`
- `/tmp/DR-ISL-phase2b/pre/study/baseline/scenario-uneven-multisched-01.1.ticks.jsonl`
- `/tmp/DR-ISL-phase2b/pre/study/baseline/scenario-uneven-multisched-01.1.events.json`
- `/tmp/DR-ISL-phase2b/pre/study/baseline/scenario-uneven-multisched-01.1.spec.json`
- `/tmp/DR-ISL-phase2b/pre/study/baseline/scenario-uneven-multisched-01.1.summary.json`
- `/tmp/DR-ISL-phase2b/STOP_EVIDENCE.json`
- `/tmp/DR-ISL-phase2b/write_stop_report.py`
- `/tmp/DR-ISL-phase2b/PHASE_2B_REPORT.md`

## Final status

`git status --porcelain=v1 --untracked-files=all`:
```text
?? tools/dr_isl/PHASE_2B_REPORT.md
```

STOP — Phase 2b diagnostic gate failed; no fixes or Phase 3 started.
