# DR-2026-10-20-ISLAND-COLLAPSE — Phase 1c resumed

## Scope and status

FINISHED: 1c.0 and 1c.2–1c.5. STOP — no Phase 3 and no IMPL-ISL-10/11 fix.

Application baseline: `a28b8987eadefdef7acc62978e581addeccc3cd2`.
Main HEAD after the explicitly authorized tooling-only commit: `86ab0efab0b8d8597182100cd88565e6036033f8`.
The only committed file is `tools/dr_isl/baseline_runner.py:1–188`.
Commit message: `DR-ISL tooling: persist pinned baseline runner (no app code)`.
No application code/config/scenario/test/parameter was changed, and nothing was published, deployed or pushed.
This report is the other explicitly authorized persistent output, uncommitted at `tools/dr_isl/PHASE_1C_REPORT.md`.

All application paths below are literal paths relative to `/home/runner/workspace`.
Application line numbers are for the unchanged a28b898 package. `P` in explanations means:
`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim`.
The code excerpts at the end print the full paths and line numbers.
Printed measurements come from the named JSON/JSONL/CSV files in `/tmp/DR-ISL-phase1c/`.

## Runner and hash contract

`tools/dr_isl/baseline_runner.py:1–188` accepts a scenario id and `-n/--repetitions`;
its header specifies fabric seed/hash 1729, wall clock 1792454400.0, Python/NumPy
1729, configured kube seed 1729, per-diesel seed 1729+i, generator/corruption pinning.
It uses `ScenarioSpec.model_validate_json` → `model_dump(mode="json")` → factory →
`RunManager` with instant playback and an in-memory sink (lines 91–158).
The hash is SHA-256 of ordered ticks: one UTF-8, compact sorted-key JSON object plus
LF per tick, NaN allowed. Exactly these top-level fields are excluded:
`advisory_telemetry`, `fabric_modal`, `wall_stamp_utc`, `insufficient_reserve_proposal_id`.
`run_id` is retained and equals the scenario id. No runner edits followed its commit.

SHA-256 of the runner and each scratch-worktree copy:
`12320f7c74c42406cc6eca862b9621621f733c2d9ad94e3ecb0c80652af6593a`.

## 1c.0 — Re-baseline gate

Scratch worktrees:
- `/tmp/DR-ISL-phase1c/phase1` → `55b21842220209f489a244df3d755bedeb158be2`
- `/tmp/DR-ISL-phase1c/phase2` → `a28b8987eadefdef7acc62978e581addeccc3cd2`

### Checkout qualification — not hidden

The first clean Phase-1 worktree run failed:
`ModuleNotFoundError: No module named 'runtime.fuel_cell_defaults'`.
The same six missing, unversioned support files were copied from the current workspace
into both scratch worktrees, without overwriting tracked files. Therefore this is
a comparison of the two tracked commits **conditional on the identical support snapshot**,
not a claim that either pristine checkout runs standalone.
The copied paths, byte counts and SHA-256 values are:
```json
[
  {
    "path": "core/infrastructure_admission.py",
    "sha256": "d86ee3c2697f4d21f6f042685f27d00bb2b4ea65c2058129e9cc05f88225d825",
    "bytes": 30829
  },
  {
    "path": "runtime/reference_forecast.py",
    "sha256": "2fa438a2380a84e954a20a29574aa3b269be2133654f890fef2ca74ef4518e8d",
    "bytes": 736
  },
  {
    "path": "runtime/fuel_cell_defaults.py",
    "sha256": "208107e53c3a3e985001ffb4126c61035955ac1a049327fb8b0693e71854f07f",
    "bytes": 181
  },
  {
    "path": "config/scenarios/scenario-kubernetes-scheduler-demo.json",
    "sha256": "d08196037183229e46e90882372df4b587821ebba698acb1d217d462c6e3d36f",
    "bytes": 2442
  },
  {
    "path": "config/scenarios/scenario-100mw-fuel-cell-bess-diesel.json",
    "sha256": "2573809039859f38bce0d83ca227ca8dd9d34a7e88ceb795cbcbf3eca864d388",
    "bytes": 23262
  },
  {
    "path": "config/scenarios/S10_mit_supercloud_2021-08-11.json",
    "sha256": "8126ee38ef2206f55d28ea9f4da029df836fbf7c4daf7d65e266d821f323f7ad",
    "bytes": 151176
  }
]
```

Both scratch worktrees passed `git diff --exit-code` with no output.
No tracked application file was changed to make the runs work.

### Four literal run results

`rebaseline_gate.json`:
```json
{
  "gate_passed": true,
  "new_reference_sha256": "a80a43bde260f51fb5f78a5f474b64a1c328452c6422e93446c2ce6e20a12716",
  "superseded_reference_sha256": "511b65899967e4ce48d908d974fb2bfd3ccb630b76528e9ffdef7f7328135b36",
  "runs": [
    {
      "file": "/tmp/DR-ISL-phase1c/rebaseline-phase1/scenario-equinix-sj-1.1.summary.json",
      "scenario_id": "scenario-equinix-sj-1",
      "repetition": 1,
      "physical_sha256": "a80a43bde260f51fb5f78a5f474b64a1c328452c6422e93446c2ce6e20a12716",
      "tick_count": 720,
      "failing_tick_count": 24,
      "failing_ticks": [
        61,
        62,
        63,
        64,
        65,
        66,
        67,
        68,
        69,
        70,
        71,
        72,
        211,
        212,
        213,
        214,
        215,
        216,
        217,
        218,
        219,
        220,
        221,
        222
      ],
      "spec_island_mode": false,
      "verification_modes": [
        "grid_tied_provisional"
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
    },
    {
      "file": "/tmp/DR-ISL-phase1c/rebaseline-phase1/scenario-equinix-sj-1.2.summary.json",
      "scenario_id": "scenario-equinix-sj-1",
      "repetition": 2,
      "physical_sha256": "a80a43bde260f51fb5f78a5f474b64a1c328452c6422e93446c2ce6e20a12716",
      "tick_count": 720,
      "failing_tick_count": 24,
      "failing_ticks": [
        61,
        62,
        63,
        64,
        65,
        66,
        67,
        68,
        69,
        70,
        71,
        72,
        211,
        212,
        213,
        214,
        215,
        216,
        217,
        218,
        219,
        220,
        221,
        222
      ],
      "spec_island_mode": false,
      "verification_modes": [
        "grid_tied_provisional"
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
    },
    {
      "file": "/tmp/DR-ISL-phase1c/rebaseline-phase2/scenario-equinix-sj-1.1.summary.json",
      "scenario_id": "scenario-equinix-sj-1",
      "repetition": 1,
      "physical_sha256": "a80a43bde260f51fb5f78a5f474b64a1c328452c6422e93446c2ce6e20a12716",
      "tick_count": 720,
      "failing_tick_count": 24,
      "failing_ticks": [
        61,
        62,
        63,
        64,
        65,
        66,
        67,
        68,
        69,
        70,
        71,
        72,
        211,
        212,
        213,
        214,
        215,
        216,
        217,
        218,
        219,
        220,
        221,
        222
      ],
      "spec_island_mode": false,
      "verification_modes": [
        "grid_tied_provisional"
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
    },
    {
      "file": "/tmp/DR-ISL-phase1c/rebaseline-phase2/scenario-equinix-sj-1.2.summary.json",
      "scenario_id": "scenario-equinix-sj-1",
      "repetition": 2,
      "physical_sha256": "a80a43bde260f51fb5f78a5f474b64a1c328452c6422e93446c2ce6e20a12716",
      "tick_count": 720,
      "failing_tick_count": 24,
      "failing_ticks": [
        61,
        62,
        63,
        64,
        65,
        66,
        67,
        68,
        69,
        70,
        71,
        72,
        211,
        212,
        213,
        214,
        215,
        216,
        217,
        218,
        219,
        220,
        221,
        222
      ],
      "spec_island_mode": false,
      "verification_modes": [
        "grid_tied_provisional"
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
  ]
}
```

**GATE PASSED.** Adopt
`a80a43bde260f51fb5f78a5f474b64a1c328452c6422e93446c2ce6e20a12716`
as the new SJ-1 reference **for this runner**, superseding
`511b65899967e4ce48d908d974fb2bfd3ccb630b76528e9ffdef7f7328135b36`.
All four runs have 720 ticks, 24 failures, exactly ticks 61–72 and 211–222.
This is not evidence that the missing old hash was wrong; its original per-tick
material is unavailable for a comparison using its original contract.

Search of retained workspace and /tmp tick/baseline artifacts found no original
Phase-1 SJ-1 per-tick output. The old `/tmp/DR-ISL-phase1` directory is absent.
Retained Phase-1b and earlier Phase-1c traces are not original Phase-1 output.
Consequently an original-old-Phase-1 versus new-run field comparison cannot be supplied.

As an additional actual field-by-field comparison, the newly generated Phase-1
repetition 1 and Phase-2 repetition 1 differed only in:
```json
{
  "insufficient_reserve_proposal_id": {
    "count": 1,
    "first_tick": 1
  },
  "advisory_telemetry": {
    "count": 708,
    "first_tick": 13
  }
}
```

Those are excluded fields. No physical field differs.
Full differing values are retained in `new_commit_raw_field_differences.json`;
they are not evidence of an original retained Phase-1 trace.

Resolved SJ-1 values, printed by all four runner summaries:
`spec_island_mode=false`; `verification_modes=["grid_tied_provisional"]`;
`tolerances_mw=[1.9913e-14]`.

## 1c.2 — Every failing tick, full terms and events

Source: `rebaseline-phase2/scenario-equinix-sj-1.1.ticks.jsonl`,
`.events.json` and `.spec.json`. Extracted without rounding into
`failing_ticks.csv` and `failing_ticks_full.json`.
In canonical raw ticks the boolean is `physical_balance.closes`; the runner tests
the `passed` property on that result (runner lines 157–158).
Ledger grid exchange is positive import; engine tick grid exchange is negative import.
FC target/achieved *block-fleet* telemetry is null because SJ-1 uses the legacy aggregate
FC module; the actual legacy module target and output were also captured live below.

Every BalanceTerms field, BESS charge/discharge/SoC, FC target/actual, cap/exchange
and event indicators for every failing tick follows in CSV, with full float representations:

```csv
tick,sim_time,defect_mw,grid_exchange_mw,island_mode,p_bess_mw,p_curtailment_mw,p_demand_mw,p_fuel_cell_mw,p_generation_mw,p_losses_mw,p_renewable_mw,p_served_mw,p_turbine_mw,p_unserved_mw,import_mw,tolerance_mw,bess_soc_fraction,bess_soc_before_fraction,bess_discharge_mw,bess_charge_mw,fc_target_mw,fc_achieved_mw,fc_state,fc_state_change,block_fc_target_telemetry,block_fc_achieved_telemetry,grid_import_limit_mw,engine_grid_exchange_mw,frequency_forcing_mw,contingency_release_alert,fc_ride_through_trips,active_tenant_burst_count,events,profile_transitions,group
61,305.0,-10.133034197934023,5.0,grid_tie,30.0,0.0,63.23303419793404,18.100000000000016,48.100000000000016,0.0,0,63.23303419793404,0,0.0,5.0,1.9913e-14,0.9626139698076789,0.9633391615331045,30.0,0.0,24.0,18.100000000000016,running,,,,5.0,-5.0,-10.133034197934023,False,,0,[],"[{""gpu_load_profile_start"": 300.0, ""multiplier"": 4.8}]",G1 FC ramping + saturated BESS/PCC
62,310.0,-10.050055781831347,5.0,grid_tie,30.0,0.0,63.250055781831364,18.200000000000017,48.20000000000002,0.0,0,63.250055781831364,0,0.0,5.0,1.9913e-14,0.9618887780822533,0.9626139698076789,30.0,0.0,24.0,18.200000000000017,running,,,,5.0,-5.0,-10.050055781831347,False,,0,[],[],G1 FC ramping + saturated BESS/PCC
63,315.0,-9.96331220469969,5.0,grid_tie,30.0,0.0,63.26331220469971,18.30000000000002,48.30000000000002,0.0,0,63.26331220469971,0,0.0,5.0,1.9913e-14,0.9611635863568276,0.9618887780822533,30.0,0.0,24.0,18.30000000000002,running,,,,5.0,-5.0,-9.96331220469969,False,,0,[],[],G1 FC ramping + saturated BESS/PCC
64,320.0,-9.873636317210284,5.0,grid_tie,30.0,0.0,63.273636317210304,18.40000000000002,48.40000000000002,0.0,0,63.273636317210304,0,0.0,5.0,1.9913e-14,0.960438394631402,0.9611635863568276,30.0,0.0,24.0,18.40000000000002,running,,,,5.0,-5.0,-9.873636317210284,False,,0,[],[],G1 FC ramping + saturated BESS/PCC
65,325.0,-9.781676744118059,5.0,grid_tie,30.0,0.0,63.28167674411808,18.50000000000002,48.50000000000002,0.0,0,63.28167674411808,0,0.0,5.0,1.9913e-14,0.9597132029059765,0.960438394631402,30.0,0.0,24.0,18.50000000000002,running,,,,5.0,-5.0,-9.781676744118059,False,,0,[],[],G1 FC ramping + saturated BESS/PCC
66,330.0,-9.412163131118149,5.0,grid_tie,30.0,0.0,63.01216313111817,18.600000000000023,48.60000000000002,0.0,0,63.01216313111817,0,0.0,5.0,1.9913e-14,0.9589880111805509,0.9597132029059765,30.0,0.0,24.0,18.600000000000023,running,,,,5.0,-5.0,-9.412163131118149,False,,0,[],[],G1 FC ramping + saturated BESS/PCC
67,335.0,-9.315140458067745,5.0,grid_tie,30.0,0.0,63.01514045806777,18.700000000000024,48.700000000000024,0.0,0,63.01514045806777,0,0.0,5.0,1.9913e-14,0.9582628194551253,0.9589880111805509,30.0,0.0,24.0,18.700000000000024,running,,,,5.0,-5.0,-9.315140458067745,False,,0,[],[],G1 FC ramping + saturated BESS/PCC
68,340.0,-9.217459202627545,5.0,grid_tie,30.0,0.0,63.01745920262757,18.800000000000026,48.800000000000026,0.0,0,63.01745920262757,0,0.0,5.0,1.9913e-14,0.9575376277296996,0.9582628194551253,30.0,0.0,24.0,18.800000000000026,running,,,,5.0,-5.0,-9.217459202627545,False,,0,[],[],G1 FC ramping + saturated BESS/PCC
69,345.0,-9.119265042706466,5.0,grid_tie,30.0,0.0,63.01926504270649,18.900000000000027,48.90000000000003,0.0,0,63.01926504270649,0,0.0,5.0,1.9913e-14,0.956812436004274,0.9575376277296996,30.0,0.0,24.0,18.900000000000027,running,,,,5.0,-5.0,-9.119265042706466,False,,0,[],[],G1 FC ramping + saturated BESS/PCC
70,350.0,-9.082669314564136,5.0,grid_tie,30.0,0.0,63.082669314564164,19.00000000000003,49.00000000000003,0.0,0,63.082669314564164,0,0.0,5.0,1.9913e-14,0.9560872442788484,0.956812436004274,30.0,0.0,24.0,19.00000000000003,running,,,,5.0,-5.0,-9.082669314564136,False,,0,[],[],G1 FC ramping + saturated BESS/PCC
71,355.0,-9.032048611136965,5.0,grid_tie,30.0,0.0,63.132048611136995,19.10000000000003,49.10000000000003,0.0,0,63.132048611136995,0,0.0,5.0,1.9913e-14,0.9553620525534228,0.9560872442788484,30.0,0.0,24.0,19.10000000000003,running,,,,5.0,-5.0,-9.032048611136965,False,,0,[],[],G1 FC ramping + saturated BESS/PCC
72,360.0,-8.970505245975396,5.0,grid_tie,30.0,0.0,63.17050524597543,19.20000000000003,49.20000000000003,0.0,0,63.17050524597543,0,0.0,5.0,1.9913e-14,0.9546368608279973,0.9553620525534228,30.0,0.0,24.0,19.20000000000003,running,,,,5.0,-5.0,-8.970505245975396,False,,0,[],[],G1 FC ramping + saturated BESS/PCC
211,1055.0,-5.647013550039816,5.0,grid_tie,30.0,0.0,64.64701355003982,24.0,54.0,0.0,0,64.64701355003982,0,0.0,5.0,1.9913e-14,0.9937630877154766,0.9944882794409022,30.0,0.0,24.0,24.0,running,,,,5.0,-5.0,-5.647013550039816,False,,0,[],"[{""gpu_load_profile_start"": 1050.0, ""multiplier"": 5.8}]",G2 FC at target + saturated BESS/PCC
212,1060.0,-5.648633657424114,5.0,grid_tie,30.0,0.0,64.64863365742411,24.0,54.0,0.0,0,64.64863365742411,0,0.0,5.0,1.9913e-14,0.993037895990051,0.9937630877154766,30.0,0.0,24.0,24.0,running,,,,5.0,-5.0,-5.648633657424114,False,,0,[],[],G2 FC at target + saturated BESS/PCC
213,1065.0,-5.649895398323665,5.0,grid_tie,30.0,0.0,64.64989539832366,24.0,54.0,0.0,0,64.64989539832366,0,0.0,5.0,1.9913e-14,0.9923127042646254,0.993037895990051,30.0,0.0,24.0,24.0,running,,,,5.0,-5.0,-5.649895398323665,False,,0,[],[],G2 FC at target + saturated BESS/PCC
214,1070.0,-5.65087804312428,5.0,grid_tie,30.0,0.0,64.65087804312428,24.0,54.0,0.0,0,64.65087804312428,0,0.0,5.0,1.9913e-14,0.9915875125391997,0.9923127042646254,30.0,0.0,24.0,24.0,running,,,,5.0,-5.0,-5.65087804312428,False,,0,[],[],G2 FC at target + saturated BESS/PCC
215,1075.0,-5.651643327664473,5.0,grid_tie,30.0,0.0,64.65164332766447,24.0,54.0,0.0,0,64.65164332766447,0,0.0,5.0,1.9913e-14,0.9908623208137741,0.9915875125391997,30.0,0.0,24.0,24.0,running,,,,5.0,-5.0,-5.651643327664473,False,,0,[],[],G2 FC at target + saturated BESS/PCC
216,1080.0,-5.65223933186364,5.0,grid_tie,30.0,0.0,64.65223933186364,24.0,54.0,0.0,0,64.65223933186364,0,0.0,5.0,1.9913e-14,0.9901371290883485,0.9908623208137741,30.0,0.0,24.0,24.0,running,,,,5.0,-5.0,-5.65223933186364,False,,0,[],[],G2 FC at target + saturated BESS/PCC
217,1085.0,-5.652703500400676,5.0,grid_tie,30.0,0.0,64.65270350040068,24.0,54.0,0.0,0,64.65270350040068,0,0.0,5.0,1.9913e-14,0.989411937362923,0.9901371290883485,30.0,0.0,24.0,24.0,running,,,,5.0,-5.0,-5.652703500400676,False,,0,[],[],G2 FC at target + saturated BESS/PCC
218,1090.0,-5.653064995220788,5.0,grid_tie,30.0,0.0,64.65306499522079,24.0,54.0,0.0,0,64.65306499522079,0,0.0,5.0,1.9913e-14,0.9886867456374974,0.989411937362923,30.0,0.0,24.0,24.0,running,,,,5.0,-5.0,-5.653064995220788,False,,0,[],[],G2 FC at target + saturated BESS/PCC
219,1095.0,-5.653346527669768,5.0,grid_tie,30.0,0.0,64.65334652766977,24.0,54.0,0.0,0,64.65334652766977,0,0.0,5.0,1.9913e-14,0.9879615539120717,0.9886867456374974,30.0,0.0,24.0,24.0,running,,,,5.0,-5.0,-5.653346527669768,False,,0,[],[],G2 FC at target + saturated BESS/PCC
220,1100.0,-5.653565785361494,5.0,grid_tie,30.0,0.0,64.6535657853615,24.0,54.0,0.0,0,64.6535657853615,0,0.0,5.0,1.9913e-14,0.9872363621866461,0.9879615539120717,30.0,0.0,24.0,24.0,running,,,,5.0,-5.0,-5.653565785361494,False,,0,[],[],G2 FC at target + saturated BESS/PCC
221,1105.0,-5.585707924566762,5.0,grid_tie,30.0,0.0,64.58570792456676,24.0,54.0,0.0,0,64.58570792456676,0,0.0,5.0,1.9913e-14,0.9865111704612205,0.9872363621866461,30.0,0.0,24.0,24.0,running,,,,5.0,-5.0,-5.585707924566762,False,,0,[],[],G2 FC at target + saturated BESS/PCC
222,1110.0,-5.5858407586412255,5.0,grid_tie,30.0,0.0,64.58584075864123,24.0,54.0,0.0,0,64.58584075864123,0,0.0,5.0,1.9913e-14,0.9857859787357949,0.9865111704612205,30.0,0.0,24.0,24.0,running,,,,5.0,-5.0,-5.5858407586412255,False,,0,[],[],G2 FC at target + saturated BESS/PCC
```

`events=[]` means no `SimulationState.apply_workload_signal` call coincided
with those ticks; this is not an assertion that the scheduler has no internal
activity at other times. The runner records these calls at lines 114–117.
Tenant bursts are resolved from the spec's half-open start/duration intervals.
The failed windows have no active tenant burst, no FC state change, no contingency
release alert and no FC ride-through trip record.
The transitions at interval starts 300 and 1050 seconds are GPU load-profile
changes, not tenant-burst or authored WorkloadSignal events.

### Groups and energy
```json
{
  "groups": [
    {
      "group": "G1 FC ramping + saturated BESS/PCC",
      "count": 12,
      "ticks": [
        61,
        62,
        63,
        64,
        65,
        66,
        67,
        68,
        69,
        70,
        71,
        72
      ],
      "absolute_defect_mwh": 0.1582652309055414,
      "defect_min_mw": -10.133034197934023,
      "defect_max_mw": -8.970505245975396,
      "fc_output_min_mw": 18.100000000000016,
      "fc_output_max_mw": 19.20000000000003,
      "with_profile_transition": 1,
      "with_workload_events": 0,
      "with_tenant_burst": 0,
      "with_fc_state_change": 0,
      "with_contingency_release": 0,
      "with_fc_trip": 0
    },
    {
      "group": "G2 FC at target + saturated BESS/PCC",
      "count": 12,
      "ticks": [
        211,
        212,
        213,
        214,
        215,
        216,
        217,
        218,
        219,
        220,
        221,
        222
      ],
      "absolute_defect_mwh": 0.0940062955559732,
      "defect_min_mw": -5.653565785361494,
      "defect_max_mw": -5.585707924566762,
      "fc_output_min_mw": 24.0,
      "fc_output_max_mw": 24.0,
      "with_profile_transition": 1,
      "with_workload_events": 0,
      "with_tenant_burst": 0,
      "with_fc_state_change": 0,
      "with_contingency_release": 0,
      "with_fc_trip": 0
    }
  ],
  "sum_abs_defect_mwh": 0.2522715264615146,
  "min_abs_defect_mw": 5.585707924566762,
  "max_abs_defect_mw": 10.133034197934023,
  "min_defect_tolerance_multiple": 280505595569063.53,
  "max_defect_tolerance_multiple": 508865273837896.0,
  "reported_served_mwh": 7.645088274381166,
  "reported_unserved_mwh": 0.0,
  "failure_soc_min": 0.9546368608279973,
  "failure_soc_max": 0.9937630877154766,
  "third_peak_max_demand_mw": 40.4603004419726,
  "third_peak_failure_ticks": []
}
```

There is one shared cause, split into two operating-state groups:
- G1: 12 negative-defect ticks; FC is still ramping; BESS/PCC are saturated.
- G2: 12 negative-defect ticks; FC is at its target; BESS/PCC are saturated.
For both groups: local generation + permitted import < requested demand,
while `p_served_mw == p_demand_mw` and `p_unserved_mw == 0`.

The description at `P/config/scenarios/scenario-equinix-sj-1.json:89`
claims three over-peak intervals create temporary unserved energy.
The literal pinned run instead has two physical-deficit windows, zero reported
unserved energy, and no failing tick in the third profile peak. Its third-peak
maximum demand is printed above as 40.4603004419726 MW; do not substitute the
description's claim for the run result.

## 1c.3 — Producer-to-ledger trace

A separate read-only, in-process trace of ticks 61 and 211 used the unchanged
persisted runner. It changed no spec or application file and recorded function
calls/returns only. `trace_representatives.py` and `representative_trace.json`
are scratch files. Its physical hash is again:
`a80a43bde260f51fb5f78a5f474b64a1c328452c6422e93446c2ce6e20a12716`;
720 ticks; the same 24 failures (`instrumented/scenario-equinix-sj-1.1.summary.json`).

### Live inputs and outputs at each relevant call/return
```json
{
  "tick": 61,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py",
  "line": 842,
  "function": "evaluate_tick",
  "return": null,
  "locals": {}
}
```
```json
{
  "tick": 61,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/fuel_cell_module.py",
  "line": 287,
  "function": "advance",
  "return": null,
  "locals": {
    "sim_time": 300.0,
    "dt_seconds": 5.0,
    "unit_target_output_mw": 24.0,
    "unit_current_output_mw": 18.000000000000014
  }
}
```
```json
{
  "tick": 61,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/fuel_cell_module.py",
  "line": 329,
  "function": "advance",
  "return": null,
  "locals": {
    "dt_seconds": 5.0,
    "unit_target_output_mw": 24.0,
    "unit_current_output_mw": 18.100000000000016
  }
}
```
```json
{
  "tick": 61,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py",
  "line": 738,
  "function": "tick",
  "return": null,
  "locals": {
    "p_dispatch_required_mw": 45.13303419793402,
    "dt_seconds": 5.0,
    "bess_dispatch_target_mw": 30.0
  }
}
```
```json
{
  "tick": 61,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py",
  "line": 1632,
  "function": "cover_shortfall",
  "return": null,
  "locals": {
    "allocated_mw": 30.0,
    "dt_seconds": 5.0,
    "power_ceiling_mw": 30.0,
    "soc_floor_mwh": 55.199999999999996,
    "unit_soc_mwh": 57.80034969198627
  }
}
```
```json
{
  "tick": 61,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py",
  "line": 1713,
  "function": "cover_shortfall",
  "return": 30.0,
  "locals": {
    "allocated_mw": 30.0,
    "dt_seconds": 5.0,
    "power_ceiling_mw": 30.0,
    "soc_floor_mwh": 55.199999999999996,
    "unit_soc_mwh": 57.75683818846073
  }
}
```
```json
{
  "tick": 61,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py",
  "line": 907,
  "function": "tick",
  "return": null,
  "locals": {
    "p_dispatch_required_mw": 45.13303419793402,
    "dt_seconds": 5.0,
    "bess_dispatch_target_mw": 30.0,
    "turbine_output_mw": 0,
    "bess_output_mw": 30.0,
    "soc_floor_mwh": 55.199999999999996
  }
}
```
```json
{
  "tick": 61,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py",
  "line": 145,
  "function": "balance_defect_mw",
  "return": null,
  "locals": {
    "terms": {
      "p_generation_mw": 48.100000000000016,
      "p_demand_mw": 63.23303419793404,
      "p_unserved_mw": 0.0,
      "grid_exchange_mw": 5.0,
      "p_losses_mw": 0.0,
      "p_curtailment_mw": 0.0,
      "island_mode": "grid_tie",
      "p_served_mw": null,
      "p_turbine_mw": 0.0,
      "p_bess_mw": 0.0,
      "p_fuel_cell_mw": 0.0,
      "p_renewable_mw": 0.0
    }
  }
}
```
```json
{
  "tick": 61,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py",
  "line": 160,
  "function": "balance_defect_mw",
  "return": -10.133034197934023,
  "locals": {
    "terms": {
      "p_generation_mw": 48.100000000000016,
      "p_demand_mw": 63.23303419793404,
      "p_unserved_mw": 0.0,
      "grid_exchange_mw": 5.0,
      "p_losses_mw": 0.0,
      "p_curtailment_mw": 0.0,
      "island_mode": "grid_tie",
      "p_served_mw": null,
      "p_turbine_mw": 0.0,
      "p_bess_mw": 0.0,
      "p_fuel_cell_mw": 0.0,
      "p_renewable_mw": 0.0
    }
  }
}
```
```json
{
  "tick": 61,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py",
  "line": 169,
  "function": "evaluate",
  "return": null,
  "locals": {
    "tolerance_mw": 1.9913e-14,
    "terms": {
      "p_generation_mw": 48.100000000000016,
      "p_demand_mw": 63.23303419793404,
      "p_unserved_mw": 0.0,
      "grid_exchange_mw": 5.0,
      "p_losses_mw": 0.0,
      "p_curtailment_mw": 0.0,
      "island_mode": "grid_tie",
      "p_served_mw": 63.23303419793404,
      "p_turbine_mw": 0,
      "p_bess_mw": 30.0,
      "p_fuel_cell_mw": 18.100000000000016,
      "p_renewable_mw": 0
    }
  }
}
```
```json
{
  "tick": 61,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py",
  "line": 145,
  "function": "balance_defect_mw",
  "return": null,
  "locals": {
    "terms": {
      "p_generation_mw": 48.100000000000016,
      "p_demand_mw": 63.23303419793404,
      "p_unserved_mw": 0.0,
      "grid_exchange_mw": 5.0,
      "p_losses_mw": 0.0,
      "p_curtailment_mw": 0.0,
      "island_mode": "grid_tie",
      "p_served_mw": 63.23303419793404,
      "p_turbine_mw": 0,
      "p_bess_mw": 30.0,
      "p_fuel_cell_mw": 18.100000000000016,
      "p_renewable_mw": 0
    }
  }
}
```
```json
{
  "tick": 61,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py",
  "line": 160,
  "function": "balance_defect_mw",
  "return": -10.133034197934023,
  "locals": {
    "terms": {
      "p_generation_mw": 48.100000000000016,
      "p_demand_mw": 63.23303419793404,
      "p_unserved_mw": 0.0,
      "grid_exchange_mw": 5.0,
      "p_losses_mw": 0.0,
      "p_curtailment_mw": 0.0,
      "island_mode": "grid_tie",
      "p_served_mw": 63.23303419793404,
      "p_turbine_mw": 0,
      "p_bess_mw": 30.0,
      "p_fuel_cell_mw": 18.100000000000016,
      "p_renewable_mw": 0
    }
  }
}
```
```json
{
  "tick": 61,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py",
  "line": 176,
  "function": "evaluate",
  "return": null,
  "locals": {
    "tolerance_mw": 1.9913e-14,
    "terms": {
      "p_generation_mw": 48.100000000000016,
      "p_demand_mw": 63.23303419793404,
      "p_unserved_mw": 0.0,
      "grid_exchange_mw": 5.0,
      "p_losses_mw": 0.0,
      "p_curtailment_mw": 0.0,
      "island_mode": "grid_tie",
      "p_served_mw": 63.23303419793404,
      "p_turbine_mw": 0,
      "p_bess_mw": 30.0,
      "p_fuel_cell_mw": 18.100000000000016,
      "p_renewable_mw": 0
    }
  }
}
```
```json
{
  "tick": 61,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py",
  "line": 3612,
  "function": "evaluate_tick",
  "return": null,
  "locals": {
    "dt_seconds": 5.0,
    "p_compute_demand_mw": 61.48503936,
    "p_cooling_demand_mw": 1.7479948379340389,
    "p_demand_mw": 63.23303419793404,
    "p_dispatch_required_mw": 63.23303419793404,
    "fuel_cell_output_mw": 18.100000000000016,
    "_planned_bess_setpoint_mw": 30.0,
    "_normal_bess_energy_exhausted": false,
    "_emergency_release_authorized": false,
    "_effective_bess_setpoint_mw": 30.0,
    "turbine_output_mw": 0,
    "bess_output_mw": 30.0,
    "_p_gen_mw": 48.100000000000016,
    "_p_dispatch_curtailed_mw": 0.0,
    "_balance_residual_mw": -15.133034197934023,
    "_grid_exchange_mw": -5.0,
    "_frequency_forcing_mw": -10.133034197934023,
    "_p_generation_mw": 53.100000000000016,
    "_islanded_supply_shortfall_mw": 0.0,
    "_p_unserved_mw": 0.0,
    "_p_served_mw": 63.23303419793404,
    "sim_time": 300.0
  }
}
```
```json
{
  "tick": 211,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py",
  "line": 842,
  "function": "evaluate_tick",
  "return": null,
  "locals": {}
}
```
```json
{
  "tick": 211,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/fuel_cell_module.py",
  "line": 287,
  "function": "advance",
  "return": null,
  "locals": {
    "sim_time": 1050.0,
    "dt_seconds": 5.0,
    "unit_target_output_mw": 24.0,
    "unit_current_output_mw": 24.0
  }
}
```
```json
{
  "tick": 211,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/fuel_cell_module.py",
  "line": 329,
  "function": "advance",
  "return": null,
  "locals": {
    "dt_seconds": 5.0,
    "unit_target_output_mw": 24.0,
    "unit_current_output_mw": 24.0
  }
}
```
```json
{
  "tick": 211,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py",
  "line": 738,
  "function": "tick",
  "return": null,
  "locals": {
    "p_dispatch_required_mw": 40.647013550039816,
    "dt_seconds": 5.0,
    "bess_dispatch_target_mw": 30.0
  }
}
```
```json
{
  "tick": 211,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py",
  "line": 1632,
  "function": "cover_shortfall",
  "return": null,
  "locals": {
    "allocated_mw": 30.0,
    "dt_seconds": 5.0,
    "power_ceiling_mw": 30.0,
    "soc_floor_mwh": 55.199999999999996,
    "unit_soc_mwh": 59.66929676645413
  }
}
```
```json
{
  "tick": 211,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py",
  "line": 1713,
  "function": "cover_shortfall",
  "return": 30.0,
  "locals": {
    "allocated_mw": 30.0,
    "dt_seconds": 5.0,
    "power_ceiling_mw": 30.0,
    "soc_floor_mwh": 55.199999999999996,
    "unit_soc_mwh": 59.625785262928595
  }
}
```
```json
{
  "tick": 211,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py",
  "line": 907,
  "function": "tick",
  "return": null,
  "locals": {
    "p_dispatch_required_mw": 40.647013550039816,
    "dt_seconds": 5.0,
    "bess_dispatch_target_mw": 30.0,
    "turbine_output_mw": 0,
    "bess_output_mw": 30.0,
    "soc_floor_mwh": 55.199999999999996
  }
}
```
```json
{
  "tick": 211,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py",
  "line": 145,
  "function": "balance_defect_mw",
  "return": null,
  "locals": {
    "terms": {
      "p_generation_mw": 54.0,
      "p_demand_mw": 64.64701355003982,
      "p_unserved_mw": 0.0,
      "grid_exchange_mw": 5.0,
      "p_losses_mw": 0.0,
      "p_curtailment_mw": 0.0,
      "island_mode": "grid_tie",
      "p_served_mw": null,
      "p_turbine_mw": 0.0,
      "p_bess_mw": 0.0,
      "p_fuel_cell_mw": 0.0,
      "p_renewable_mw": 0.0
    }
  }
}
```
```json
{
  "tick": 211,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py",
  "line": 160,
  "function": "balance_defect_mw",
  "return": -5.647013550039816,
  "locals": {
    "terms": {
      "p_generation_mw": 54.0,
      "p_demand_mw": 64.64701355003982,
      "p_unserved_mw": 0.0,
      "grid_exchange_mw": 5.0,
      "p_losses_mw": 0.0,
      "p_curtailment_mw": 0.0,
      "island_mode": "grid_tie",
      "p_served_mw": null,
      "p_turbine_mw": 0.0,
      "p_bess_mw": 0.0,
      "p_fuel_cell_mw": 0.0,
      "p_renewable_mw": 0.0
    }
  }
}
```
```json
{
  "tick": 211,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py",
  "line": 169,
  "function": "evaluate",
  "return": null,
  "locals": {
    "tolerance_mw": 1.9913e-14,
    "terms": {
      "p_generation_mw": 54.0,
      "p_demand_mw": 64.64701355003982,
      "p_unserved_mw": 0.0,
      "grid_exchange_mw": 5.0,
      "p_losses_mw": 0.0,
      "p_curtailment_mw": 0.0,
      "island_mode": "grid_tie",
      "p_served_mw": 64.64701355003982,
      "p_turbine_mw": 0,
      "p_bess_mw": 30.0,
      "p_fuel_cell_mw": 24.0,
      "p_renewable_mw": 0
    }
  }
}
```
```json
{
  "tick": 211,
  "event": "call",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py",
  "line": 145,
  "function": "balance_defect_mw",
  "return": null,
  "locals": {
    "terms": {
      "p_generation_mw": 54.0,
      "p_demand_mw": 64.64701355003982,
      "p_unserved_mw": 0.0,
      "grid_exchange_mw": 5.0,
      "p_losses_mw": 0.0,
      "p_curtailment_mw": 0.0,
      "island_mode": "grid_tie",
      "p_served_mw": 64.64701355003982,
      "p_turbine_mw": 0,
      "p_bess_mw": 30.0,
      "p_fuel_cell_mw": 24.0,
      "p_renewable_mw": 0
    }
  }
}
```
```json
{
  "tick": 211,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py",
  "line": 160,
  "function": "balance_defect_mw",
  "return": -5.647013550039816,
  "locals": {
    "terms": {
      "p_generation_mw": 54.0,
      "p_demand_mw": 64.64701355003982,
      "p_unserved_mw": 0.0,
      "grid_exchange_mw": 5.0,
      "p_losses_mw": 0.0,
      "p_curtailment_mw": 0.0,
      "island_mode": "grid_tie",
      "p_served_mw": 64.64701355003982,
      "p_turbine_mw": 0,
      "p_bess_mw": 30.0,
      "p_fuel_cell_mw": 24.0,
      "p_renewable_mw": 0
    }
  }
}
```
```json
{
  "tick": 211,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py",
  "line": 176,
  "function": "evaluate",
  "return": null,
  "locals": {
    "tolerance_mw": 1.9913e-14,
    "terms": {
      "p_generation_mw": 54.0,
      "p_demand_mw": 64.64701355003982,
      "p_unserved_mw": 0.0,
      "grid_exchange_mw": 5.0,
      "p_losses_mw": 0.0,
      "p_curtailment_mw": 0.0,
      "island_mode": "grid_tie",
      "p_served_mw": 64.64701355003982,
      "p_turbine_mw": 0,
      "p_bess_mw": 30.0,
      "p_fuel_cell_mw": 24.0,
      "p_renewable_mw": 0
    }
  }
}
```
```json
{
  "tick": 211,
  "event": "return",
  "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py",
  "line": 3612,
  "function": "evaluate_tick",
  "return": null,
  "locals": {
    "dt_seconds": 5.0,
    "p_compute_demand_mw": 63.17530056,
    "p_cooling_demand_mw": 1.471712990039821,
    "p_demand_mw": 64.64701355003982,
    "p_dispatch_required_mw": 64.64701355003982,
    "fuel_cell_output_mw": 24.0,
    "_planned_bess_setpoint_mw": 30.0,
    "_normal_bess_energy_exhausted": false,
    "_emergency_release_authorized": false,
    "_effective_bess_setpoint_mw": 30.0,
    "turbine_output_mw": 0,
    "bess_output_mw": 30.0,
    "_p_gen_mw": 54.0,
    "_p_dispatch_curtailed_mw": 0.0,
    "_balance_residual_mw": -10.647013550039816,
    "_grid_exchange_mw": -5.0,
    "_frequency_forcing_mw": -5.647013550039816,
    "_p_generation_mw": 59.0,
    "_islanded_supply_shortfall_mw": 0.0,
    "_p_unserved_mw": 0.0,
    "_p_served_mw": 64.64701355003982,
    "sim_time": 1050.0
  }
}
```

### Call path and ordering

1. `P/core/simulation_core.py:1219` adds compute and cooling:
   tick 61 `61.48503936 + 1.7479948379340389 = 63.23303419793404`;
   tick 211 `63.17530056 + 1.471712990039821 = 64.64701355003982`.
   There is no additional "other" component in this producer.
2. `P/core/simulation_core.py:1288–1289` removes renewable output (0 here) from
   dispatch-required demand. `P/core/fuel_cell_module.py:287–329` advances the
   legacy FC toward target 24.0. Tick 61: pre-output 18.000000000000014,
   post-output 18.100000000000016; tick 211: 24.0 before and after.
3. `P/core/simulation_core.py:1941–1951` calls `DispatchArbitrator.tick` at
   `P/core/dispatch.py:738` with demand after achieved FC:
   45.13303419793402 at tick 61 and 40.647013550039816 at tick 211.
   BESS dispatch target is 30.0 in both calls. `BESSModule.cover_shortfall`
   at `P/core/asset_modules.py:1632–1713` receives allocated 30.0, power ceiling
   30.0 and SoC floor 55.199999999999996 MWh; it returns 30.0 MW.
   The trace has `_normal_bess_energy_exhausted=false` and
   `_emergency_release_authorized=false` on both representative ticks.
4. `P/core/simulation_core.py:2994–3000` produces local generation:
   48.100000000000016 at tick 61 and 54.0 at tick 211.
   The residual before the PCC is respectively -15.133034197934023 and
   -10.647013550039816 MW (`:3037`, `:3128–3132`).
5. The import clamp at `P/core/simulation_core.py:3120–3132` sets engine
   grid exchange to -5.0 in both cases. Remaining forcing is
   -10.133034197934023 / -5.647013550039816 MW.
   Public generation including imports at `:3140` is
   53.100000000000016 / 59.0 MW.
6. The responsible load-side branch is `P/core/simulation_core.py:3494–3502`:
   `max(0, demand - local_generation)` is evaluated only if islanded;
   here `_islanded_supply_shortfall_mw=0`, cumulative shed is 0, unserved is 0,
   and served equals requested demand.
7. `P/core/simulation_core.py:3542–3559` gives the physical ledger local
   generation, positive-import PCC exchange, and that unreduced served demand.
   `P/core/power_balance.py:133–176` computes:
   local generation + import - served - losses - curtailment.
   Results are -10.133034197934023 and -5.647013550039816 MW; both fail
   tolerance 1.9913e-14. The ledger is correctly exposing the supply deficit,
   not creating it by rounding.

### Cause classification against the requested alternatives

- **IMPL-ISL-10 stale sink after supply change: not this mechanism.**
  All 24 failures have curtailment 0, FC state running, and no FC trip.
- **Grid-tied provisional circular-PCC artefact: not a sufficient explanation.**
  Unlimited-grid routing can close by construction, but here an actual 5 MW
  import clamp leaves the printed, nonzero residual. The provisional flag
  does not supply the missing MW.
- **BESS charge/AC efficiency/full-charge guard: not the failure mechanism.**
  Failing ticks have charge 0 and AC discharge 30.0. Failed-tick SoC is
  0.9546368608279973–0.9937630877154766, not full or depleted.
  `asset_modules.py:1704–1713` applies discharge efficiency to stored energy
  and returns AC discharge; that is not an extra missing grid-supplied term.
- **Import-limit capping: trigger, correctly applied**, rather than a wrongly
  implemented clamp. The semantic defect is treating the capped residual
  as still served instead of classifying it as electrically unmet load.
- **Tolerance: not the mechanism.** Defect magnitude is
  5.585707924566762–10.133034197934023 MW, or
  280505595569063.53–508865273837896.0 times tolerance.

## 1c.4 — Provenance, coverage and scope

### Provenance (do not infer missing source history)

Literal pickaxe and historical excerpts are saved in
`provenance_resume.txt` and `provenance_detail.txt`.

- `78555831cc6674902fa437393701ec5e2acd5853`,
  `2026-08-08T16:47:04Z`, "Implement export functionality and update simulation core data models",
  introduced the explicit-shed-only producer with the comment
  "NOT: min(P_demand, P_generation) — that is explicitly prohibited by the spec."
- `1f27c0ca49c082a506b026b3377ffc7355d9fa5c`,
  `2026-08-09T16:51:05Z`, "Update simulation core logic and add reference image",
  changed that producer to cap served power by local generation.
- `5281fd5880590e88de91c0242adfb215408e8116`,
  `2026-08-19T04:35:28Z`, "Implement scenario API routes and update memory documentation",
  is the first retained pickaxe addition of `_grid_exchange_mw = max(`.
  Its historical `core/simulation_core.py:2039–2043` clamps import and leaves the
  residual in frequency forcing. Historical lines 2325–2333 in that SAME commit
  cap served load using generation INCLUDING grid import. Thus it is not honest
  to label this cap-introduction commit alone as introducing the current SJ-1 defect.
- `46bf003db0af0c8dd8d6875c0551196256850463`,
  `2026-09-03T00:40:41Z`, "Track simulator source and regression assets",
  re-adds the whole simulation_core.py (3041 insertions), including the import cap
  together with explicit-shed-only unserved (`historical :2816–2818`).
  This is the retained tracked reintroduction of the problematic combination.
  Because it is a whole-file re-tracking, its date is not proof of the original
  untracked edit date or author intent.
- `c0737fc54b82e238fe620cf48a5ce74d8d136a27`,
  `2026-09-04T03:25:43Z`, "Update fuel cell readiness documentation and add scenario specification schema",
  introduced the CURRENT `_islanded_supply_shortfall_mw` branch, extending physical
  unmet-load accounting only to islanded sites. Its added comment says
  "Grid-tied deficits are supplied through the PCC accounting path, so only
  islanded residuals are load-side unserved here." That assumption does not hold
  once the PCC cap binds. The current producer is `simulation_core.py:3495–3502`.

The root cause therefore has a traced policy/producer history, not an attributable
Phase-2 regression: all four Phase-1/Phase-2 physical hashes match.
Where source was untracked and later re-added, no more precise introducing edit
date is established by these files; none is estimated.

### Existing coverage and why it passes

`P/tests/test_grid_import_limit_scenario.py:715–732` does exercise a capped
grid supply deficit, but explicitly expects:
`grid_exchange_mw=-10.0`, `p_unserved_mw=0.0`, and nonzero balance defect
equal to negative `frequency_forcing_mw`. Its name says "remains balanced",
but its assertions intentionally accept a nonzero physical residual.
`P/tests/test_grid_import_limit_scenario.py:297–336` checks the three SJ-1 peak
windows and explicitly asserts zero reported unserved power at :321; recovery
imbalance, not physical ledger closure during peaks, is checked at :334.
These tests encode the current policy; they are not evidence of physical closure.
They would need a reviewed policy change, not a test-only workaround.

Targeted read-only pytest output (`coverage.log`; XML `coverage.xml`):
```text
....                                                                     [100%]
4 passed in 10.40s
```

The four node IDs:
- tests/test_grid_import_limit_scenario.py::test_grid_import_is_physically_capped_and_d4_remains_balanced
- tests/test_grid_import_limit_scenario.py::test_unset_grid_import_limit_preserves_unlimited_grid_balancing
- tests/test_grid_import_limit_scenario.py::test_grid_import_limit_does_not_cap_export
- tests/test_grid_import_limit_scenario.py::test_sj1_three_overpeak_bursts_respect_supply_limits_and_recover

### Other scenarios — same unchanged pinned runner, seeder path

The scope runs below are catalogue/default arms, one run each; no forecast-informed
spec variation was requested for Phase 1c. Counts cover the completed ticks only;
they do not extrapolate beyond a collapse or configured end.
```json
[
  {
    "scenario_id": "scenario-100mw-fuel-cell-bess-diesel",
    "repetition": 1,
    "physical_sha256": "565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b",
    "tick_count": 252,
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
    ],
    "planned_end_seconds": 1260.0,
    "last_completed_seconds": 1260.0,
    "last_tick_collapse_fields": {
      "collapse_frequency_hz": null,
      "collapse_reason": null,
      "collapse_tick_index": null,
      "island_collapsed": false
    },
    "group_counts": {
      "G1": 0,
      "G2": 0,
      "other_balance_failure": 0
    }
  },
  {
    "scenario_id": "scenario-hybrid-ai-100mw-addendum-i",
    "repetition": 1,
    "physical_sha256": "4e9c1a040eeaa4952600225cef71fa7ab8088419a916184bad09ba45bc8bc518",
    "tick_count": 120,
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
    ],
    "planned_end_seconds": 600.0,
    "last_completed_seconds": 600.0,
    "last_tick_collapse_fields": {
      "collapse_frequency_hz": null,
      "collapse_reason": null,
      "collapse_tick_index": null,
      "island_collapsed": false
    },
    "group_counts": {
      "G1": 0,
      "G2": 0,
      "other_balance_failure": 0
    }
  },
  {
    "scenario_id": "scenario-uneven-multisched-01",
    "repetition": 1,
    "physical_sha256": "bd125c313284ddfcb7f5a5e1112b95ab25cc82a9a731273cb050a7a14e3d31a9",
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
    ],
    "planned_end_seconds": 7200.0,
    "last_completed_seconds": 7200.0,
    "last_tick_collapse_fields": {
      "collapse_frequency_hz": null,
      "collapse_reason": null,
      "collapse_tick_index": null,
      "island_collapsed": false
    },
    "group_counts": {
      "G1": 0,
      "G2": 0,
      "other_balance_failure": 0
    }
  }
]
```

No failing tick in those completed streams exhibits the SJ-1 mechanism.
This does not prove every possible configuration or later unexecuted interval
is free of it; their recorded verification modes are islanded, unlike SJ-1.

## 1c.5 — Classification and impact

| Group | Classification | One-sentence fix direction (not implemented) |
|---|---|---|
| G1, ticks 61–72 | Genuine served/unserved semantics defect under a binding PCC cap; not stale-test, harness or tolerance artefact | Define physically served versus unmet demand from achieved local supply plus permitted PCC imports, without changing requested demand or dispatch policy, and reconcile the load-side ledger accordingly. |
| G2, ticks 211–222 | Same genuine defect at FC target rather than during FC ramp | Use the same reviewed capped-grid served/unserved rule consistently when all local sources and permitted imports are saturated. |

The negative physical balance residual itself is an accurate warning of insufficient
available supply. The defect is the simultaneous claim that all requested MW were
electrically served and no energy was unserved. Existing tests deliberately encode
that claim; changing only their expectations would not resolve the producer semantics.

Printed impact from `impact.json`:
- G1 sum |defect| × 5/3600: **0.1582652309055414 MWh**.
- G2 sum |defect| × 5/3600: **0.0940062955559732 MWh**.
- Total: **0.2522715264615146 MWh**.
- Run's reported served energy: **7.645088274381166 MWh**.
- Run's reported unserved energy: **0.0 MWh**.
- For an ACCOUNTING-ONLY reconciliation of these recorded deficits: served energy
  would decrease by 0.2522715264615146 to **7.392816747919651 MWh**, and unserved
  would increase to **0.2522715264615146 MWh**.
- That accounting-only relabelling would not change the recorded BESS SoC, FC
  output, PCC imports or fuel counters. No numerical change to those quantities
  is established for a future control/dispatch fix; such closed-loop effects
  cannot be inferred from the failing-tick residuals alone.

SJ-1 output is not presented here as externally validated customer data.
No code fix, scenario edit, test edit, constant change or parameter tuning was made.

## Evidence excerpts — current application

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-equinix-sj-1.json:28–88`
```text
28:   "edl_calendar_month": null,
29:   "tenant_budgets": null,
30:   "operator_response_profile": null,
31:   "grid_authority_tier": "autonomous",
32:   "design_peak_load_mw": null,
33:   "irradiance_steps": [
34:     [
35:       0.0,
36:       1.0
37:     ]
38:   ],
39:   "gpu_load_profile": [
40:     [
41:       0.0,
42:       0.45
43:     ],
44:     [
45:       300.0,
46:       4.8
47:     ],
48:     [
49:       360.0,
50:       0.45
51:     ],
52:     [
53:       1050.0,
54:       5.8
55:     ],
56:     [
57:       1110.0,
58:       0.45
59:     ],
60:     [
61:       1800.0,
62:       6.3
63:     ],
64:     [
65:       1860.0,
66:       0.45
67:     ],
68:     [
69:       2400.0,
70:       0.1
71:     ]
72:   ],
73:   "workload_floor_fraction": null,
74:   "island_mode": false,
75:   "grid_import_limit_mw": 5.0,
76:   "bess_normal_dispatch_depth_fraction": 0.03,
77:   "frequency_nominal_hz": 60.0,
78:   "uf_warning_hz": null,
79:   "ufls_stage1_hz": null,
80:   "island_collapse_hz": null,
81:   "of_warning_hz": null,
82:   "of_trip_hz": null,
83:   "ufls_stages": null,
84:   "relay_81u_threshold_hz": null,
85:   "relay_81u_delay_s": null,
86:   "power_factor": 0.85,
87:   "pue_base": 1.074,
88:   "end_sim_time": 3600.0,
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:1219–1228`
```text
1219:     p_demand_mw = p_compute_demand_mw + p_cooling_demand_mw
1220: 
1221:     # _islanded: hoisted here (before section 3) so the §INV-CURT inverter
1222:     # curtailment block can reference it before the Phase 13.3 droop block.
1223:     # A single assignment; the same object is referenced throughout evaluate_tick().
1224:     _islanded = (state.site.island_mode == IslandMode.ISLANDED)
1225: 
1226:     # 3. Solar offset (Extension E-1 / §7.1.1) — evaluated BEFORE arbitration
1227:     #    so the fleet sizes against P_dispatch_required, not P_total.
1228:     #    P_renewable can vanish without notice (Δt_lead = 0 for inverter trips);
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:1288–1289`
```text
1288:     p_dispatch_required_mw = max(0.0, p_demand_mw - p_renewable_mw)
1289:     net_demand_mw = p_dispatch_required_mw
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/fuel_cell_module.py:209–216`
```text
209:     def min_stable_mw(self) -> float:
210:         return self.config.min_stable_frac * self.config.rated_mw
211: 
212:     @property
213:     def target_output_mw(self) -> float:
214:         if self.config.load_following and self._load_following_target_mw is not None:
215:             return self._load_following_target_mw
216:         return float(self.config.baseload_target_mw)
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/fuel_cell_module.py:287–294`
```text
287:     def advance(self, sim_time: float, dt_seconds: float) -> None:
288:         """Advance warming, cooling, or chemically rate-limited output."""
289:         del sim_time  # Reserved for later event/audit integration.
290:         if dt_seconds < 0.0:
291:             raise ValueError("FuelCellModule.advance() requires non-negative dt")
292: 
293:         if self.state == FuelCellState.WARMING:
294:             self._time_remaining_s = max(
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/fuel_cell_module.py:317–329`
```text
317:         if self.target_output_mw < self.min_stable_mw:
318:             self.command_stop(0.0)
319:             return
320: 
321:         delta_mw = self.target_output_mw - self._current_output_mw
322:         ramp_rate_mw_per_s = (
323:             self.config.ramp_rate_mw_per_s
324:             if delta_mw >= 0.0
325:             else float(self.config.ramp_down_rate_mw_per_s)
326:         )
327:         max_step_mw = ramp_rate_mw_per_s * dt_seconds
328:         step_mw = max(-max_step_mw, min(max_step_mw, delta_mw))
329:         self._current_output_mw = max(
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:1887–1916`
```text
1887:     _emergency_release_authorized = False
1888:     if _normal_bess_energy_exhausted:
1889:         _grid_emergency_support_mw = (
1890:             0.0
1891:             if _islanded
1892:             else (
1893:                 float("inf")
1894:                 if state.site.grid_import_limit_mw is None
1895:                 else max(0.0, state.site.grid_import_limit_mw)
1896:             )
1897:         )
1898:         # An emergency is an actual residual after every non-BESS source
1899:         # available to this model: online turbine output, measured fuel-cell
1900:         # output, and PCC import. Only the retained BESS reserve is released.
1901:         _emergency_gap_mw = max(
1902:             0.0,
1903:             _physical_bess_shortfall_mw
1904:             # Diesel coordination runs after BESS arbitration.  Use measured
1905:             # delivery from the preceding interval when deciding whether the
1906:             # retained reserve must be released.
1907:             - state._prev_diesel_output_mw
1908:             - _grid_emergency_support_mw,
1909:         )
1910:         _emergency_release_authorized = _emergency_gap_mw > 0.0
1911:         _emergency_bess_target_mw = min(
1912:             _emergency_gap_mw,
1913:             sum(_reserve_bess_ceilings_mw),
1914:         )
1915:     else:
1916:         _emergency_bess_target_mw = 0.0
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:1928–1952`
```text
1928:     _effective_bess_setpoint_mw = min(
1929:         _planned_bess_setpoint_mw + _emergency_bess_target_mw,
1930:         _physical_bess_shortfall_mw,
1931:     )
1932:     # The same reconciled threshold that shaped the upstream ceiling is the
1933:     # downstream physical floor.  The existing emergency-release condition
1934:     # authorizes that retained energy for this tick only; no other contingency
1935:     # state is introduced here.
1936:     _bess_soc_floors_mwh = (
1937:         [0.0] * len(_bess_reconciled_reserve_mwh)
1938:         if _emergency_release_authorized
1939:         else _bess_reconciled_reserve_mwh
1940:     )
1941:     turbine_output_mw, bess_output_mw, _bess_setpoint_mw, _arb_candidates = state.arbitrator.tick(
1942:         # Pass the signed physical net demand after achieved FC output, never
1943:         # a command-achieved residual.  Positive values let tick() discharge
1944:         # against an actual shortfall; negative values preserve its existing
1945:         # surplus-absorption path so fixed FC overproduction charges the BESS.
1946:         # tick() removes measured turbine output exactly once.
1947:         p_dispatch_required_mw - fuel_cell_output_mw,
1948:         dt_seconds,
1949:         bess_dispatch_target_mw=_effective_bess_setpoint_mw,
1950:         bess_dispatch_ceilings_mw=_bess_dispatch_ceilings_mw,
1951:         bess_soc_floors_mwh=_bess_soc_floors_mwh,
1952:     )
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py:1681–1713`
```text
1681:         max_by_power = power_ceiling_mw
1682:         max_by_energy = (
1683:             self.deliverable_energy_mwh(soc_floor_mwh)
1684:             / (dt_seconds / 3600.0)
1685:             if dt_seconds > 0
1686:             else max_by_power
1687:         )
1688:         discharge_target_mw = min(allocated_mw, max_by_power, max_by_energy)
1689: 
1690:         # Phase 13.3 — first-order inverter response lag.
1691:         # Discrete: actual = prev + alpha × (target − prev), alpha = 1 − exp(−dt/τ).
1692:         # At τ=0.05 s (grid-forming inverter) and dt=0.1 s: alpha≈0.865 (fast).
1693:         # At τ=0.05 s and dt=5 s (live dispatch tick):     alpha≈1.000 (instant).
1694:         # Clamp actual output to [0, discharge_target_mw] so the lag never
1695:         # over-shoots (inverter cannot deliver more than the physics allows).
1696:         tau = self.config.bess_response_tau_s
1697:         if tau > 0.0 and dt_seconds > 0.0:
1698:             alpha = 1.0 - math.exp(-dt_seconds / tau)
1699:             discharge_mw = self._prev_output_mw + alpha * (discharge_target_mw - self._prev_output_mw)
1700:             discharge_mw = max(0.0, min(discharge_mw, discharge_target_mw))
1701:         else:
1702:             discharge_mw = discharge_target_mw
1703: 
1704:         self.soc_mwh = max(
1705:             0.0,
1706:             self.soc_mwh
1707:             - discharge_mw
1708:             * (dt_seconds / 3600.0)
1709:             / self.config.discharge_efficiency,
1710:         )
1711:         self._prev_output_mw = discharge_mw
1712:         self._current_output_mw = discharge_mw
1713:         return discharge_mw
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:2994–3037`
```text
2994:     _p_gen_mw = (
2995:         turbine_output_mw
2996:         + bess_output_mw
2997:         + fuel_cell_output_mw
2998:         + p_renewable_mw
2999:         + diesel_output_mw
3000:     )
3001:     # Once synchronized turbines have reached their minimum stable load and the
3002:     # BESS has accepted all energy it physically can, the remaining positive
3003:     # residual is an explicit dispatch-curtailment sink.  Keep generation and
3004:     # turbine fuel physical, but do not subtract that sink before the
3005:     # electromechanical response: the rotor must see the surplus on this tick.
3006:     #
3007:     # Turbine rundown is already time-based above (machine ramp rate and the
3008:     # existing commitment/unloading policy).  The explicit dump action has its
3009:     # own configurable response delay on SiteConfig; this ledger value is the
3010:     # surplus scheduled for that action, not a fictional change to measured
3011:     # generation.  Keeping it as an explicit balance term preserves a closed
3012:     # physical ledger while frequency_forcing_mw receives the pre-curtailment
3013:     # residual.
3014:     _surplus_before_dump_mw = (
3015:         max(0.0, _p_gen_mw - p_demand_mw) if _islanded else 0.0
3016:     )
3017:     if _surplus_before_dump_mw <= 1e-12:
3018:         state._dispatch_curtailment_elapsed_s = 0.0
3019:         _p_dispatch_curtailed_mw = 0.0
3020:     else:
3021:         _dump_delay_s = max(
3022:             0.0,
3023:             float(getattr(state.site, "dispatch_curtailment_response_delay_s", 0.0)),
3024:         )
3025:         state._dispatch_curtailment_elapsed_s = min(
3026:             _dump_delay_s,
3027:             state._dispatch_curtailment_elapsed_s + max(0.0, dt_seconds),
3028:         )
3029:         _dump_response_fraction = (
3030:             1.0
3031:             if _dump_delay_s <= 0.0
3032:             else state._dispatch_curtailment_elapsed_s / _dump_delay_s
3033:         )
3034:         _p_dispatch_curtailed_mw = (
3035:             _surplus_before_dump_mw * min(1.0, _dump_response_fraction)
3036:         )
3037:     _balance_residual_mw = _p_gen_mw - p_demand_mw
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3116–3140`
```text
3116:     if _islanded:
3117:         _grid_exchange_mw     = 0.0                    # PCC open (D1)
3118:         _frequency_forcing_mw = _balance_residual_mw   # actual supply-demand → rotors
3119:     else:
3120:         _grid_import_limit_mw = state.site.grid_import_limit_mw
3121:         if _grid_import_limit_mw is None:
3122:             _grid_exchange_mw     = _balance_residual_mw
3123:             _frequency_forcing_mw = 0.0                # unlimited grid holds frequency (D2)
3124:         else:
3125:             # Negative grid_exchange_mw means import.  Clamp only that direction;
3126:             # positive export remains unconstrained.  Any deficit beyond the PCC
3127:             # ceiling stays visible in the second D4 energy channel.
3128:             _grid_exchange_mw = max(
3129:                 _balance_residual_mw,
3130:                 -max(0.0, _grid_import_limit_mw),
3131:             )
3132:             _frequency_forcing_mw = _balance_residual_mw - _grid_exchange_mw
3133: 
3134:     # GS-CHG-2026-08-08 successor Phase 1 — P_generation aggregate producer.
3135:     # ONE computation site; the serialiser must NOT sum these components again (Spec 19 / TC-92).
3136:     # _p_gen_mw = turbine + BESS + solar (already computed at line ~1291).
3137:     # Grid import: _grid_exchange_mw < 0 in grid-connected when local gen < demand;
3138:     #   -_grid_exchange_mw > 0 gives the MW drawn from the PCC.  In islanded mode
3139:     #   _grid_exchange_mw = 0 always (D1), so max(0, -0) = 0 and this is a no-op.
3140:     _p_generation_mw = _p_gen_mw + max(0.0, -_grid_exchange_mw)
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3487–3506`
```text
3487:     # ── Phase 6: Load-side served/shed producers ───────────────────────────────
3488:     # The served/unserved split includes explicit UFLS/curtailment shedding and,
3489:     # for an islanded site, any remaining physical supply deficit. A power
3490:     # ceiling is not merely telemetry: demand above deliverable generation is
3491:     # electrically unserved.
3492:     # Per-subsystem shed is proportional to demand fraction because stage
3493:     # definitions specify a block fraction of total demand only.
3494:     _cumulative_shed_mw = state._cumulative_shed_mw  # monotonic run total
3495:     _islanded_supply_shortfall_mw = (
3496:         max(0.0, p_demand_mw - _p_gen_mw) if _islanded else 0.0
3497:     )
3498:     _p_unserved_mw = min(
3499:         p_demand_mw,
3500:         max(_cumulative_shed_mw, _islanded_supply_shortfall_mw),
3501:     )
3502:     _p_served_mw = p_demand_mw - _p_unserved_mw
3503:     # p_imbalance is the measured generation-versus-served-load channel.  An
3504:     # explicit curtailment sink closes the physical ledger, but it must not
3505:     # erase the surplus from the frequency/imbalance signal on the same tick.
3506:     _p_imbalance_mw = _p_generation_mw - _p_served_mw
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3542–3559`
```text
3542:     # p_imbalance_mw; it is never hidden inside the explicit-shed field.
3543:     _p_losses_mw = 0.0  # no loss model is currently represented by the simulator
3544:     _physical_balance = _evaluate_physical_balance(
3545:         _BalanceTerms(
3546:             p_generation_mw=_p_gen_mw,
3547:             p_demand_mw=p_demand_mw,
3548:             p_unserved_mw=_p_unserved_mw,
3549:             p_served_mw=_p_served_mw,
3550:             grid_exchange_mw=-_grid_exchange_mw,
3551:             p_losses_mw=_p_losses_mw,
3552:             island_mode=_BAL_ISLANDED if _islanded else _BAL_GRID_TIE,
3553:             p_turbine_mw=turbine_output_mw,
3554:             p_bess_mw=bess_output_mw,
3555:             p_fuel_cell_mw=fuel_cell_output_mw,
3556:             p_renewable_mw=p_renewable_mw,
3557:             p_curtailment_mw=_p_dispatch_curtailed_mw,
3558:         ),
3559:         tolerance_mw=_sp.value("balance_defect_tolerance_mw"),
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py:58–87`
```text
58: class BalanceResult:
59:     defect_mw: float                # generation + import - served - losses
60:     served_mw: float
61:     import_mw: float
62:     closes: bool | None             # None when no tolerance was supplied
63:     tolerance_mw: float | None
64:     terms: BalanceTerms
65: 
66:     @property
67:     def independent(self) -> bool:
68:         """Whether the grid term comes from an independent physical boundary."""
69:         return str(self.terms.island_mode).lower() == ISLANDED
70: 
71:     @property
72:     def verification_mode(self) -> str:
73:         """Authority of this ledger result, not whether its residual is small."""
74:         return (
75:             ISLANDED_VERIFIED
76:             if self.independent
77:             else GRID_TIED_PROVISIONAL
78:         )
79: 
80:     @property
81:     def passed(self) -> bool:
82:         """Whether this evaluated identity closes at its supplied tolerance."""
83:         return self.closes is True
84: 
85:     @property
86:     def residual_magnitude_mw(self) -> float:
87:         """Absolute size of the signed identity defect."""
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py:133–176`
```text
133: def served_load_mw(terms: BalanceTerms) -> float:
134:     """Load actually carried: total demand less whatever was shed.
135: 
136:     The load-side value is intentionally independent of supply. A generation
137:     deficit remains visible in the balance residual and p_imbalance_mw rather
138:     than being silently absorbed into the served/unserved split.
139:     """
140:     if terms.p_served_mw is not None:
141:         return terms.p_served_mw
142:     return terms.p_demand_mw - terms.p_unserved_mw
143: 
144: 
145: def balance_defect_mw(terms: BalanceTerms) -> float:
146:     """Signed identity residual. Positive means surplus generation.
147: 
148:     Islanded, this quantity must be zero at every instant: there is nowhere for
149:     surplus to go and nothing to supply a deficit. A non-zero value is not a
150:     measurement of anything physical -- it is the amount by which the model has
151:     failed to close, and it should drive frequency once phase 2 lands.
152:     """
153:     imp = (
154:         0.0
155:         if str(terms.island_mode).lower() == ISLANDED
156:         else terms.grid_exchange_mw
157:     )
158:     if not GRID_EXCHANGE_POSITIVE_IS_IMPORT:
159:         imp = -imp
160:     return (
161:         terms.p_generation_mw
162:         + imp
163:         - served_load_mw(terms)
164:         - terms.p_losses_mw
165:         - terms.p_curtailment_mw
166:     )
167: 
168: 
169: def evaluate(terms: BalanceTerms, tolerance_mw: float | None = None) -> BalanceResult:
170:     d = balance_defect_mw(terms)
171:     imp = (
172:         0.0
173:         if str(terms.island_mode).lower() == ISLANDED
174:         else terms.grid_exchange_mw
175:     )
176:     return BalanceResult(
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_grid_import_limit_scenario.py:297–336`
```text
297: def test_sj1_three_overpeak_bursts_respect_supply_limits_and_recover() -> None:
298:     """Each authored peak respects the PCC cap and recovers before the next."""
299:     spec_data = _load_raw(_SCENARIO_PATH)
300:     ctx = build_run_context_from_spec("sj1-three-deficit-peaks", spec_data)
301:     ctx.playback_speed = 0.0
302:     sink = InMemoryTimeseriesSink()
303:     ctx.sink = sink
304:     manager = RunManager(WebSocketHub())
305: 
306:     async def run() -> None:
307:         await manager.start_run(ctx)
308:         task = manager._tasks.get(ctx.run_id)
309:         if task is not None:
310:             await task
311: 
312:     asyncio.run(run())
313: 
314:     for start_s, end_s in ((300.0, 360.0), (1050.0, 1110.0), (1800.0, 1860.0)):
315:         peak_ticks = [
316:             tick for tick in sink.rows
317:             if start_s <= tick.sim_time_seconds < end_s
318:         ]
319:         assert peak_ticks
320:         assert all(
321:             tick.p_unserved_mw == pytest.approx(0.0, abs=1e-6)
322:             for tick in peak_ticks
323:         )
324:         assert min(tick.grid_exchange_mw for tick in peak_ticks) >= -5.0 - 1e-6
325: 
326:         recovery_ticks = [
327:             tick for tick in sink.rows
328:             # Ticks are timestamped at interval end, so the tick stamped at
329:             # end_s still reflects the preceding five-second peak interval.
330:             if end_s + 5.0 <= tick.sim_time_seconds < end_s + 30.0
331:         ]
332:         assert recovery_ticks
333:         assert all(
334:             tick.p_imbalance_mw == pytest.approx(0.0, abs=1e-6)
335:             for tick in recovery_ticks
336:         )
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_grid_import_limit_scenario.py:715–741`
```text
715: def test_grid_import_is_physically_capped_and_d4_remains_balanced() -> None:
716:     tick = _grid_only_tick(10.0)
717: 
718:     assert tick.p_demand_mw > 10.0
719:     assert tick.grid_exchange_mw == pytest.approx(-10.0, abs=1e-9)
720:     assert tick.frequency_forcing_mw < 0.0
721:     # Shortfall is reported through p_imbalance_mw. p_unserved_mw remains
722:     # explicit shed only and is zero until protection actually sheds load.
723:     assert tick.d4_balance_defect_mw == pytest.approx(
724:         tick.frequency_forcing_mw,
725:         abs=1e-9,
726:     )
727:     assert tick.p_unserved_mw == pytest.approx(0.0, abs=1e-9)
728:     assert tick.p_imbalance_mw == pytest.approx(
729:         tick.frequency_forcing_mw,
730:         abs=1e-9,
731:     )
732:     assert tick.p_generation_mw == pytest.approx(10.0, abs=1e-9)
733: 
734: 
735: def test_unset_grid_import_limit_preserves_unlimited_grid_balancing() -> None:
736:     tick = _grid_only_tick(None)
737: 
738:     assert tick.p_demand_mw > 10.0
739:     assert -tick.grid_exchange_mw == pytest.approx(tick.p_demand_mw, abs=1e-9)
740:     assert tick.frequency_forcing_mw == 0.0
741:     assert tick.d4_balance_defect_mw == pytest.approx(0.0, abs=1e-9)
```

## Complete retained provenance command output

```text
EXPLICIT_SHED_PICKAXE
78555831cc6674902fa437393701ec5e2acd5853 2026-08-08T16:47:04Z Implement export functionality and update simulation core data models
1f27c0ca49c082a506b026b3377ffc7355d9fa5c 2026-08-09T16:51:05Z Update simulation core logic and add reference image
46bf003db0af0c8dd8d6875c0551196256850463 2026-09-03T00:40:41Z Track simulator source and regression assets
c0737fc54b82e238fe620cf48a5ce74d8d136a27 2026-09-04T03:25:43Z Update fuel cell readiness documentation and add scenario specification schema
PRE_C073_BLAME
46bf003d (simergalis 2026-09-03 00:40:41 +0000 2935)     _p_unserved_mw = _cumulative_shed_mw
46bf003d (simergalis 2026-09-03 00:40:41 +0000 2936)     _p_served_mw = p_demand_mw - _p_unserved_mw
CAP_INTRO_DIFF
commit 5281fd5880590e88de91c0242adfb215408e8116
Author: Replit Agent <agent@replit.com>
Date:   Wed Aug 19 04:35:28 2026 +0000

    Implement scenario API routes and update memory documentation
    
    Replit-Commit-Author: Agent

diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
index 75a57ee..617f6e6 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -1972,7 +1972,10 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     # Phase 13.2 + Task #200 B1/B2 — two-channel energy identity, one reporting field.
     #
     # D1: islanded → grid_exchange_mw = 0.0 exactly (PCC open).
-    # D2: grid-connected → frequency_forcing_mw = 0.0 exactly (grid holds f).
+    # D2: grid-connected with an unconstrained PCC → frequency_forcing_mw = 0.0
+    #     exactly (grid holds f).  When grid_import_limit_mw is configured and
+    #     saturated, the excess deficit remains on frequency_forcing_mw so D4
+    #     continues to expose the unserved power rather than inventing grid import.
     # D4: grid_exchange + frequency_forcing = balance_residual.
     #     Two channels only; holds in BOTH modes without any conditional or RHS term.
     # D5: asset_delivery_error_mw is NOT a term in D4.  Computed independently
@@ -2025,8 +2028,19 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         _grid_exchange_mw     = 0.0                    # PCC open (D1)
         _frequency_forcing_mw = _balance_residual_mw   # actual supply-demand → rotors
     else:
-        _grid_exchange_mw     = _balance_residual_mw   # actual supply-demand → PCC
-        _frequency_forcing_mw = 0.0                    # grid holds frequency (D2)
+        _grid_import_limit_mw = state.site.grid_import_limit_mw
+        if _grid_import_limit_mw is None:
+            _grid_exchange_mw     = _balance_residual_mw
+            _frequency_forcing_mw = 0.0                # unlimited grid holds frequency (D2)
+        else:
+            # Negative grid_exchange_mw means import.  Clamp only that direction;
+            # positive export remains unconstrained.  Any deficit beyond the PCC
+            # ceiling stays visible in the second D4 energy channel.
+            _grid_exchange_mw = max(
+                _balance_residual_mw,
+                -max(0.0, _grid_import_limit_mw),
+            )
+            _frequency_forcing_mw = _balance_residual_mw - _grid_exchange_mw
 
     # GS-CHG-2026-08-08 successor Phase 1 — P_generation aggregate producer.
     # ONE computation site; the serialiser must NOT sum these components again (Spec 19 / TC-92).
C073_DIFF
commit c0737fc54b82e238fe620cf48a5ce74d8d136a27
Author: Replit Agent <agent@replit.com>
Date:   Fri Sep 4 03:25:43 2026 +0000

    Update fuel cell readiness documentation and add scenario specification schema
    
    Replit-Commit-Author: Agent

diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
index 081a951..26f3c39 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -1606,6 +1606,18 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     # final normal-dispatch tick, the available normal energy may be less than
     # the BESS MW rating but must be exhausted before any held charge is used.
     _normal_bess_energy_exhausted = _bess_available_mw <= 1e-9
+    # BESS is a physical balance resource.  In particular, do not use the
+    # droop/FC command as its demand signal: a fuel-cell command can differ
+    # from measured output while the measured fleet already covers the site.
+    # That command-achieved difference remains a readiness/telemetry signal
+    # below, but must not create a baseline BESS discharge (or artificial
+    # charging surplus).
+    _physical_bess_shortfall_mw = max(
+        0.0,
+        p_dispatch_required_mw
+        - _post_loading_turbine_output_mw
+        - fuel_cell_output_mw,
+    )
     _emergency_release_authorized = False
     if _normal_bess_energy_exhausted:
         _grid_emergency_support_mw = (
@@ -1622,9 +1634,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         # output, and PCC import. Only the retained BESS reserve is released.
         _emergency_gap_mw = max(
             0.0,
-            _p_dispatch_droop_mw
-            - _post_loading_turbine_output_mw
-            - fuel_cell_output_mw
+            _physical_bess_shortfall_mw
             # Diesel coordination runs after BESS arbitration, so use the
             # previous tick's diesel output here.  A same-tick value is not
             # available without reordering the pipeline or making diesel
@@ -1654,12 +1664,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         _bess_dispatch_ceilings_mw = _bess_normal_dispatch_ceilings_mw
     _effective_bess_setpoint_mw = min(
         _planned_bess_setpoint_mw + _emergency_bess_target_mw,
-        max(
-            0.0,
-            _p_dispatch_droop_mw
-            - fuel_cell_output_mw
-            - _post_loading_turbine_output_mw,
-        ),
+        _physical_bess_shortfall_mw,
     )
     # The same reconciled threshold that shaped the upstream ceiling is the
     # downstream physical floor.  The existing emergency-release condition
@@ -1671,7 +1676,12 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         else _bess_reconciled_reserve_mwh
     )
     turbine_output_mw, bess_output_mw, _bess_setpoint_mw, _arb_candidates = state.arbitrator.tick(
-        _p_dispatch_droop_mw - fuel_cell_output_mw,
+        # Pass the signed physical net demand after achieved FC output, never
+        # a command-achieved residual.  Positive values let tick() discharge
+        # against an actual shortfall; negative values preserve its existing
+        # surplus-absorption path so fixed FC overproduction charges the BESS.
+        # tick() removes measured turbine output exactly once.
+        p_dispatch_required_mw - fuel_cell_output_mw,
         dt_seconds,
         bess_dispatch_target_mw=_effective_bess_setpoint_mw,
         bess_dispatch_ceilings_mw=_bess_dispatch_ceilings_mw,
@@ -2922,17 +2932,29 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     _compute_inlet_temp_c = _T_AMBIENT_BASE_C + _cooling_fraction * _T_RISE_MAX_C
 
     # ── Phase 6: Load-side served/shed producers ───────────────────────────────
-    # The served/unserved split is a load-side accounting result, not a
-    # supply-capped calculation. It must not reference _p_generation_mw: doing so
-    # would absorb a generation deficit into unserved load and make the physical
-    # ledger circular. Explicit UFLS/curtailment shed is the only unserved load.
+    # The served/unserved split includes explicit UFLS/curtailment shedding and,
+    # for an islanded site, any remaining physical supply deficit.  A power
+    # ceiling is not merely a telemetry constraint: demand above it is genuinely
+    # unserved.  This keeps a grid-forming BESS's anchor reserve out of normal
+    # dispatch (e.g. 60 MW rated - 1 MW anchor = 59 MW deliverable) instead of
+    # silently treating the withheld MW as served load.
     #
-    # Supply shortfall remains visible separately in _p_imbalance_mw, while the
-    # swing equation continues to use _balance_residual_mw directly.
+    # Grid-tied deficits are supplied through the PCC accounting path, so only
+    # islanded residuals are load-side unserved here.  The swing equation still
+    # uses _balance_residual_mw directly.
     # Per-subsystem shed is proportional to demand fraction because stage
     # definitions specify a block fraction of total demand only.
     _cumulative_shed_mw = state._cumulative_shed_mw  # monotonic run total
-    _p_unserved_mw = _cumulative_shed_mw
+    _islanded_supply_shortfall_mw = (
+        max(0.0, p_demand_mw - _p_gen_mw) if _islanded else 0.0
+    )
+    _p_unserved_mw = min(
+        p_demand_mw,
+        # UFLS is the intentional load reduction that closes a supply gap, not
+        # an additional deficit on top of that same gap.  Keep the larger
+        # independently observed amount rather than double-counting it.
+        max(_cumulative_shed_mw, _islanded_supply_shortfall_mw),
+    )
     _p_served_mw = p_demand_mw - _p_unserved_mw
     _p_imbalance_mw = _p_generation_mw - _p_served_mw
 
@@ -2953,14 +2975,15 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     # _grid_exchange_mw is negative on import (balance_residual < 0 when local gen
     # < demand), so we pass −_grid_exchange_mw here to match the convention.
     #
-    # DR-BAL-5 (C-3): p_unserved_mw = _cumulative_shed_mw (UFLS-shed load only).
-    # Generation deficit is NOT a "shed" for D4 purposes — it shows up as a non-zero
-    # defect (generation + import < served) rather than reducing the served load term.
+    # p_unserved_mw contains deliberate UFLS shed or an islanded physical
+    # generation deficit, whichever is larger.  In both cases it reduces served
+    # load for D4: an anchor-reserved MW above the BESS bridge ceiling cannot be
+    # reported as electrically served.
     # p_losses_mw defaults to 0.0 — the model does not represent losses.
     _balance_terms = _BalanceTerms(
         p_generation_mw=_p_gen_mw,            # local generation, including diesel
         p_demand_mw=p_demand_mw,
-        p_unserved_mw=_cumulative_shed_mw,     # UFLS-shed only; gen deficit ≠ shed
+        p_unserved_mw=_p_unserved_mw,
         grid_exchange_mw=-_grid_exchange_mw,   # negate: positive = import (POSITIVE_IS_IMPORT=True)
         island_mode=_BAL_ISLANDED if _islanded else _BAL_GRID_TIE,
     )

```

## Files and final repository checks

Repository outputs in this phase:
1. `tools/dr_isl/baseline_runner.py:1–188`, committed alone at
   86ab0efab0b8d8597182100cd88565e6036033f8.
2. `tools/dr_isl/PHASE_1C_REPORT.md:1–end`, this report, uncommitted.

Scratch scripts/data/report are under `/tmp/DR-ISL-phase1c/`.
Scratch worktrees and the identical unversioned support overlay are documented
in 1c.0 and `support_overlay.json`. No commit was made in either scratch worktree.

`git diff a28b898 -- <application package>` literal stdout:
```text
(empty)
```

`git diff a28b898 --name-status` literal stdout (tracked files):
```text
A	tools/dr_isl/baseline_runner.py
```

`git status --porcelain=v1 --untracked-files=all` literal stdout:
```text
?? tools/dr_isl/PHASE_1C_REPORT.md
```

STOP — end of Phase 1c. No implementation or Phase 3 started.
