# IMPL-ISL-17 — measurement-only validation of H2 start-event logging

**COMPLETE — overall verdict FAIL: one added full-suite failure.**
Application measured: `146b89f`; validation date: 2026-10-22.

## Authority, scope and provenance

- User approval: validate the separate-session P4b change as IMPL-ISL-17, not as approval to begin further Phase 4/4c work.
- Coordination boundary stated by the user: this session now leads this programme; further DR-2026-10-22-ISL-P4 / Phase 4c requests require this session's approval.
- Measured application HEAD: `146b89fd4aadcb8c5207f524435b8a78072cd231`.
- Phase 3 reference: `4e2f9b01dd8830572f3aab784588c6db51244b1a`.
- P4a design: `94c108a92e6007e33ebe142a19d2ee6388984d22`.
- `P` denotes `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim`.
- No application, test or scenario edits; no restart, publish, deployment or push.
- This report is the only file intended for the validation commit. The failing-ID file explicitly requested in V1 is a measurement output, not an application/test edit.

## V0 — design and implementation summary (11 lines)

1. Defect: successful pre-staging turbine starts updated native counters/fuel but omitted controller start events (`tools/dr_isl/PHASE_4_DESIGN.md:29–46`).
2. Phase 3 H2 baseline consequently recorded 6 events against 11 measured starts (`tools/dr_isl/PHASE_3_REPORT.md:145–151`).
3. Design: optional successful-start observer; existing turbine-transition adapter; event-time sink lookup (`PHASE_4_DESIGN.md:212–238`).
4. `P/core/dispatch.py:18,379–382`: callback type/import and default `None`.
5. `P/core/dispatch.py:622–641`: observe pre-command state/count; call observer only for OFFLINE→STARTING and one native start-count increment.
6. Existing command→pending-register order and eligibility call are preserved (`P/core/dispatch.py:593–594,624–641`).
7. `P/core/simulation_core.py:352–353,389–412`: wire observer and forward to existing adapter.
8. Metadata source is `predicted_step_staging` (PROPOSED_HERE); `controller_approved=None`; no runtime import into core.
9. Adapter resolves the optional sink when called; missing sink returns without action (`P/core/simulation_core.py:719–754`).
10. Source intent is observation-only: no new start, dispatch or physics decision; measured identity is assessed below, not assumed.
11. P4b reported 19 new TC-ISL-07a–g cases plus 17 focused existing cases: 36 passed, 5 warnings, 10.62 s (`tools/dr_isl/PHASE_4B_REPORT.md`).

## Measurement method

- Reused `/tmp/DR-ISL-phase3/finish_worker.py` in memory with its original pinning and native study-harness execution.
- Pinning: Python/NumPy/fabric seed 1729; configured kube/generator/corruption seeds as in `tools/dr_isl/baseline_runner.py`; per-diesel seed 1729+i; wall clock 1792454400.0; `PYTHONHASHSEED=1729`.
- H reference runs use their Phase 3 seed (`None`); base-demo study runs use seed 42, `reuse_cache=False`, no parameter overrides.
- For fresh Phase 3 comparisons, an isolated import loader obtains only `core/dispatch.py` and `core/simulation_core.py` from `git show 4e2f9b0:...` and compiles them in memory. These are the only production files changed by P4b. No checkout, worktree or application-file restoration is performed.
- Each Phase 3/HEAD pair streams corresponding full physical tick objects and native compact rows through pipes; objects are compared field by field. No full tick exports are written.
- Physical SHA-256 contract: compact sorted-key JSON plus LF per tick, NaN allowed; exclude exactly `advisory_telemetry`, `fabric_modal`, `wall_stamp_utc`, `insufficient_reserve_proposal_id`.
- Fresh Phase 3 hashes are also checked against the retained final Phase 3 evidence in `/tmp/DR-ISL-phase3/finish/*.json`.
- All 27 Phase 3 collector metric fields are compared. Start and commitment logs are compared separately, preserving literal added/removed entries.
- Native `compare_metrics` uses truthful per-version engine provenance, with matching engine/harness provenance between the baseline and informed arms within each comparison.
- Evidence output directory: `/tmp/IMPL-ISL-17/`. Each process has an enforced 200,000,000-byte single-file limit.
- Full suite runs in the real package using the retained incremental JUnit observer loaded in memory; pytest's cache provider and Python bytecode writes are disabled.

## V1 — full suite

Real-package invocation: `pytest.main(["-q", "-p", "no:cacheprovider",
"--junitxml=/tmp/IMPL-ISL-17/suite_native.xml"], plugins=[incremental_observer])`.
The retained Phase 3 observer was loaded in memory with only its output `ROOT`
changed to `/tmp/IMPL-ISL-17`; no plugin/application/test file was edited.

Literal final output:
```text
16 failed, 2170 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 726.19s (0:12:06)
PYTEST_EXIT= 1
```

Native JUnit: tests=2215, failures=16, errors=0, skipped=26.
Incremental JUnit: tests=2212, failures=16, errors=0, skipped=26.
Native totals include three passing subtests; both skipped totals include xfails.

Set difference against `tools/dr_isl/PHASE_3_FAILING_TESTS.txt`:
added=1, removed=0, remaining=15. The added ID is literally:
```text
tests/test_step16_wiring.py::test_network_telemetry_returns_required_fields_for_active_run
```
Exact added assertion at `P/tests/test_step16_wiring.py:204`:
```text
>       assert len(body["switches"]) == 2
E       assert 0 == 2
E        +  where 0 = len([])
```
Native JUnit reports this test duration as 0.189 s.
The test immediately POSTs `/runs`, then GETs `/network-telemetry?run_id=...`
inside `TestClient` (`P/tests/test_step16_wiring.py:192–195`) before checking
for the two switch records. This is source context, not proof of a timing
cause or proof that P4b caused the failure. No standalone rerun, fix, test
update, or suite rerun was performed.

All 15 Phase 3 failing node IDs remain in the current set. The full 16-ID
list is saved, as explicitly requested in V1, to
`tools/dr_isl/IMPL_ISL_17_FAILING_TESTS.txt`.
It is left uncommitted to respect the instruction that the report be committed alone.

Evidence:
- `/tmp/IMPL-ISL-17/suite.log`
- `/tmp/IMPL-ISL-17/suite_native.xml`
- `/tmp/IMPL-ISL-17/suite_incremental.xml` (incrementally maintained throughout)
- `/tmp/IMPL-ISL-17/suite_failing_tests.txt`

V1 fails the zero-added-failures criterion. No causal classification of the
added failure is asserted from this one full-suite observation.

## V2 — H2-24h baseline, two repetitions

Both repetitions completed: 17,280 ticks each. Physical differing-tick count=0,
compact differing-tick count=0, first physical/compact difference=null.
Both fresh Phase 3 runs match the retained final Phase 3 hash and all 27
retained metric fields. Within each version, both repetitions' complete records
and physical hashes are identical.

| Field | Phase 3, both repetitions | HEAD, both repetitions |
|---|---|---|
| Physical SHA-256 | `f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1` | identical |
| Compact SHA-256 | `8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66` | identical |
| recorded_event_count | 6 | 11 |
| measured_event_count | 11 | 11 |
| measured_start_fuel_mmbtu | 124.0 | 124.0 |
| tier_sum_mmbtu | 124.0 | null |
| release_charged | true | true |
| start_fuel_reconciliation.passed | false | true |
| constraints_valid | false | true |
| hard_violations count | 5 | 0 |
| commitment-log records | 39 | 44 |
| commitment.distinct_event_count / visible_distinct_event_count | 39 / 39 | 44 / 44 |

The `null` tier sum is the literal native collector output on the successful
path; it is not substituted with a calculated value in this report. Measured
start fuel remains 124.0 MMBtu. The measured starts and their physics are unchanged.

The only four changed collector fields are `commitment`,
`constraints_valid`, `hard_violations`, and `start_fuel_reconciliation`.
The other 23 collector fields are unchanged.

Removed hard violations, literally (identical in both Phase 3 repetitions):
```text
start_count_reconciliation:gt-hot-01:asset=2:log=1:untracked_path=production_command_or_cascade
start_count_reconciliation:gt-hot-01:asset=3:log=1:untracked_path=production_command_or_cascade
start_count_reconciliation:gt-hot-01:asset=4:log=1:untracked_path=production_command_or_cascade
start_count_reconciliation:gt-hot-01:asset=5:log=1:untracked_path=production_command_or_cascade
start_count_reconciliation:gt-hot-01:asset=6:log=1:untracked_path=production_command_or_cascade
```

HEAD hard_violations=`[]`. Exactly five start records and five commitment-log
entries were added; no existing entries were removed or changed. Removing the
new entries from the HEAD commitment log reproduces the entire Phase 3 log
exactly, in its original order.

The five added entries all have these literal common fields:
```json
{"accepted":true,"action":"start","bess_soc_fraction":1.0,"changed_state":true,"controller_approved":null,"forecast_mw":0.0,"from_state":"offline","peak_forecast_mw":0.0,"refusal_reason":null,"source":"predicted_step_staging","suppressed_repeat_count":0,"synchronized_capacity_mw":50.0,"thermal_tier":"warm","to_state":"starting","unit_id":"gt-hot-01"}
```
The remaining fields for each entry are:

| sim_time_s | reason |
|---|---|
|36030.0|`predicted step delta_p_mw=0.02101199999999981, dt_lead_seconds=45.0`|
|43230.0|`predicted step delta_p_mw=0.02101200000000003, dt_lead_seconds=45.0`|
|50430.0|`predicted step delta_p_mw=0.02101200000000003, dt_lead_seconds=45.0`|
|57630.0|`predicted step delta_p_mw=0.02101199999999981, dt_lead_seconds=45.0`|
|64830.0|`predicted step delta_p_mw=0.02101200000000003, dt_lead_seconds=45.0`|

Evidence: `/tmp/IMPL-ISL-17/scenario-h2-slurm-24h-baseline-{1,2}.json`.

Native `study_harness.acceptance.compare_metrics` with the corresponding H2
informed run, separately for each repetition:

| Condition | Phase 3, both repetitions | HEAD, both repetitions |
|---|---|---|
| build_parity | true | true |
| baseline_valid | false | true |
| informed_valid | true | true |
| baseline_energy_balance | true | true |
| informed_energy_balance | true | true |
| baseline_fuel_reconciled | true | true |
| informed_fuel_reconciled | true | true |
| identical_compute_trace | true | true |
| informed_unserved_energy_no_worse | true | true |
| informed_peak_unserved_no_worse | true | true |
| verdict | FAIL (9/10) | PASS (10/10) |

Literal comparison values in both versions and repetitions:
baseline_unserved_mwh=5.011418076,
informed_unserved_mwh=0.859772492,
baseline_peak_unserved_mw=44.86838787,
informed_peak_unserved_mw=42.36838787.

## V3 — H2 informed and H1 both arms, two repetitions each

H2 informed, repetitions 1 and 2: 17,280 ticks each; physical differing-tick
count=0, compact differing-tick count=0, metric differences=`{}` across all
27 fields. Start-log and commitment-log added/removed entries=`[]` in both
repetitions; 14 start records and 65 commitment-log entries in both versions.
Physical SHA-256 (Phase 3 = HEAD):
`b7383d283f09d625f531ecc216b447b868792f50069bbc662b1636d2b988bbfb`.
No first differing physical tick or field exists.

H1 baseline and informed, two repetitions per arm: each run completed 17,280
ticks. Physical differing-tick count=0, compact differing-tick count=0,
all 27 metric differences=`{}`, and added/removed start/commitment log entries
are `[]` in every comparison.

| Arm | Physical SHA-256, Phase 3 = HEAD, both repetitions | Compact SHA-256, Phase 3 = HEAD, both repetitions | start / commitment records, both versions |
|---|---|---|---|
|H1 baseline|`57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b`|`e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755`|12 / 48|
|H1 informed|`60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9`|`19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2`|12 / 59|
|H2 informed|`b7383d283f09d625f531ecc216b447b868792f50069bbc662b1636d2b988bbfb`|`0def2a33daa2770e5095d8cb63b2c5e7d01ab65c85aaf4db3bd732a89623a3c7`|14 / 65|

The freshly replayed Phase 3 runs also match their corresponding retained
Phase 3 physical hashes and all 27 retained metrics. No first differing
physical tick or field exists for any V3 run. Evidence files:
`/tmp/IMPL-ISL-17/{scenario-h1-k8s-ray-24h,scenario-h2-slurm-24h}-{baseline,informed}-{1,2}.json`
(H2 baseline is reported under V2).

## V4 — base demo, both study arms

Both arms used seed 42, `reuse_cache=False`, no parameter overrides; 1,440
ticks per arm. All physical fields, compact rows and all 27 metric fields
are identical to Phase 3, with first physical difference=null and zero
physical/compact differing ticks. The requested production-record metrics
match exactly:

| Arm | dispatch_curtailment_mwh | turbine_fuel_mmbtu | unserved_mwh | peak_unserved_mw |
|---|---:|---:|---:|---:|
| baseline | 8.136511735 | 714.363019086 | 0.351692658 | 22.309362466 |
| informed | 5.278943188 | 665.398247704 | 0.020719074 | 7.52325057 |

| Arm | physical SHA-256, Phase 3 = HEAD | compact SHA-256, Phase 3 = HEAD |
|---|---|---|
|baseline|`90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1`|`a2370e5fd24c65cbfd2e70b41f154eeee8857060a689f05a7c7d6ef93c49fd48`|
|informed|`ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6`|`0197b5b22abae47ed48635835a25f0bdfb6580a0df61291c82fbfc246fcacc65`|

Native compare_runs/compare_metrics verdict=PASS, 10/10:
```json
{"baseline_energy_balance":true,"baseline_fuel_reconciled":true,"baseline_valid":true,"build_parity":true,"identical_compute_trace":true,"informed_energy_balance":true,"informed_fuel_reconciled":true,"informed_peak_unserved_no_worse":true,"informed_unserved_energy_no_worse":true,"informed_valid":true}
```
The baseline has 2 start/8 commitment records; the informed arm has 2
start/11 commitment records. No start or commitment entries were added or
removed, and their ordered equality is checked in the closing evidence audit.
Evidence: `/tmp/IMPL-ISL-17/scenario-uneven-multisched-01-{baseline,informed}-1.json`.

## V5 — eight app-path regression scenarios

All eight completed through the pinned seeder-path/RunManager execution.
For every row: fresh Phase 3 hash = retained final Phase 3 hash = HEAD hash,
physical differing-tick count=0, first differing tick/field=null.

| Scenario | Ticks | Physical SHA-256, retained Phase 3 = fresh Phase 3 = HEAD |
|---|---:|---|
|S10_mit_supercloud_2021-08-11|17280|`4370c9ebfbfc90d2812cad93285c9749645974502508e8188c3567eb3e60d34d`|
|demo-islanded-ramp|2160|`fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a`|
|scenario-equinix-sj-1|720|`328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84`|
|scenario-turbine-01|720|`006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a`|
|scenario-hybrid-ai-100mw-addendum-i|120|`9377f009785094697116d356ef554985107ce1ee4c92f01c672f4b30b5f7577a`|
|scenario-100mw-fuel-cell-bess-diesel|252|`565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b`|
|scenario-fc100-islanded-v2|264|`d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3`|
|scenario-fc100-islanded-zero-hot-v2|264|`d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2`|

No physical difference exists to classify as a start-log/telemetry-only
difference. All native observed start attempts, transitions, extrema,
collapse/unserved/balance summaries and ineligibility-episode records in
the worker traces are also unchanged. The app worker does not collect a
study-harness commitment log; no claim of an additional app-log comparison
is made from its empty study-record object.

Evidence: `/tmp/IMPL-ISL-17/{scenario}-app-1.json`, each containing both
versions' bounded summaries and its retained Phase 3 reference path.

## V6 — verdict

**FAIL — V1 has one added full-suite failure.** The zero-added-failures gate
does not pass even though H2 baseline reconciliation closes, H2 comparison
becomes valid, and V2–V5 show physical identity. This report does not
attribute the added failure to P4b without further evidence.

| Criterion | Result |
|---|---|
| Observation-only physical behavior | PASS: 162,900 corresponding physical ticks, zero differences |
| H2 baseline start-event reconciliation | PASS: 11 recorded / 11 measured, both repetitions |
| H2 validity / compare_runs | PASS: zero hard violations, baseline_valid=true, 10/10 conditions |
| H2 informed / certified H1 preservation | PASS: physical fields, compact rows, all 27 metrics and ordered logs unchanged |
| Base-demo production record | PASS: requested values exact, compare_runs 10/10 |
| Eight app regressions | PASS: all physical hashes unchanged |
| Full-suite zero-added-failures gate | FAIL: one added node ID; 15 retained, none removed |

No fix or revert has been performed. No further Phase 4/4c work is authorized
or started by this validation.

## Closing evidence audit and commit boundary

Literal closing audit output:
```text
CLOSING EVIDENCE AUDIT: PASS, 18 pairs; 162900 physical tick pairs; all repeated H records identical.
Saved failing-ID list byte-identical; SHA-256 0b7fdf0a6cfc91854b93fcc233d358603effd3c991279540f1979c3bd2ba0337
Maximum scratch file scenario-h1-k8s-ray-24h-informed-2.json 13505568 bytes; directory files total 54470620 bytes.
```

The audit checked every comparison completed with worker return codes `[0,0]`,
zero physical/compact differing ticks, equal full native trace summaries,
fresh Phase 3 equality to retained hashes and metrics, native compact hashes
equal to retained hashes, and ordered start/commitment log equality outside
the five expected H2 baseline additions. For all four repeated H scenario/arm
sets, complete records and trace summaries were identical between repetitions
within each version.

One read-only progress reader initially attempted to parse an H1 summary
while it was still being written and received `JSONDecodeError`; reading the
closed file succeeded. No measurement run was repeated or substituted because
of that reader race.

`git diff 146b89f -- P/core P/runtime P/api P/tests P/config/scenarios` printed
nothing after all measurements. No automatic checkpoint changed HEAD during
validation. Before the report commit, the only working-tree additions were
this report and the requested failing-ID list; nothing was staged.

Only `tools/dr_isl/IMPL_ISL_17_VALIDATION.md` is to be committed. Its commit
hash is reported in the delivery message rather than self-referenced here.
`tools/dr_isl/IMPL_ISL_17_FAILING_TESTS.txt` is retained uncommitted, as the
user requested saving that evidence but explicitly restricted the commit
to the report alone.

**STOP — end of IMPL-ISL-17 validation.**
