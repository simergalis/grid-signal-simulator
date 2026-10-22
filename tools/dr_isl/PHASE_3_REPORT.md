# DR-2026-10-20-ISLAND-COLLAPSE — Phase 3 (D2), final resumption

## FINAL — D2-a resumption, 3.O–3.R COMPLETE (2026-10-22)

This section supersedes all STOP/current-state statements in the historical reports below.
Scope: Phase 3 only. Phase 4 was not started. No publish, deployment or push.
Entry HEAD was `f6d981195ca83c16ded7de9d127cbccf38009863`; application base was
`134538067d4eb4c2ce14232e483e9a91fd31276b`.
Stash `c52218ee0e35597eac442cabaa04e839ebc50273` was applied and retained.

`P` means `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim`.
Fresh evidence directory: `/tmp/DR-ISL-phase3/finish/`.
Previous summaries were retained in `/tmp/DR-ISL-phase3/d2a_previous/`.
All acceptance pairs were re-run, not substituted with the retained summaries.

### 3.O — restoration, D2-a test changes, focused tests

Before the test updates, `git diff c52218e -- P/core P/runtime` printed nothing:
the restored application was exactly the previous candidate.
The nullable logger safety check is at `P/core/simulation_core.py:654–663`.
Controller adjudication calls the shared predicate at
`P/runtime/turbine_commitment.py:1203–1210`; the duplicate minimum-down guard is absent.
The predicate and safety guard are at `P/core/asset_modules.py:1057–1084`.

Lloyd's D2-a approval accepts the controller veto of a reserved hot-standby
core-commit target. BASE approved that proposal, but direct delivery was
silently dropped; the separate later contingency release is not direct core delivery.
The diagnostic evidence remains in `tools/dr_isl/PHASE_3_TC125_DIAGNOSIS.md`.

TC125 (`P/tests/test_addendum_h_phase2a_commitment.py:588–613`) now takes the
existing spinning=1/hot=1 fixture and sets the second unit's `hot_standby=False`
before building. Its initial state is OFFLINE and minimum-down is disabled.
The approval assertions are retained: approved=True, action=`proposal_commit`,
source=`core_commitment_proposal`, controller_approved=True.
TC132 (`:824–827`) retains the False approval assertion and changes only the
reason substring to `start ineligible (min_down)`, with the D2 comment.
New TC-ISL-06e (`P/tests/test_dr_isl_hot_standby_veto.py:1–28`) asserts the
reserved target returns `(False, "hot_standby")`, adjudication=False,
refusal containing `hot_standby`, controller_approved=False.
The collision search found no other TC-ISL-06e.

Command, from P:
```text
pytest -q tests/test_dr_isl_start_eligibility.py tests/test_dr_isl_hot_standby_veto.py tests/test_addendum_h_phase2a_commitment.py::test_tc125_informed_core_proposal_is_logged_by_controller tests/test_addendum_h_phase2a_commitment.py::test_tc132_core_start_is_vetoed_during_minimum_down_window --junitxml=/tmp/DR-ISL-phase3/TC06_d2a.xml
........                                                                 [100%]
8 passed in 1.05s
```
These are TC-ISL-06a–e, the guard-boundary test, TC125 and TC132.
An initial new-test collection attempt failed with `ModuleNotFoundError:
No module named 'test_addendum_h_phase2a_commitment'`; its scratch log was
overwritten by the successful focused run. The new test import was corrected
to `tests.test_addendum_h_phase2a_commitment` before the passing run.
No production change was made for that collection error.

### 3.P — all acceptance gates PASS

Fresh comparison command chain: `finish_compare.py` for S10 and H2 informed,
then `/tmp/DR-ISL-phase3/finish_batch.py`, then `finish_acceptance.py`.
Printed result:
```json
{"passed": true, "failure": null, "checks": 36}
```
Evidence: `/tmp/DR-ISL-phase3/finish/acceptance.json`.
A second comparison, `/tmp/DR-ISL-phase3/d2a_gate.py`, checked every fresh
candidate trace (including all starts, rejected attempts, episodes, extrema,
balance failures and physical hash), all 27 metric fields and compact-tick
hashes against the retained previous candidate:
```json
{"checks": 17, "passed": true}
```
Evidence: `/tmp/DR-ISL-phase3/D2A_PRIOR_CANDIDATE_COMPARISON.json`.
Summary files have fresh modification times after the focused JUnit file.
Streaming workers wrote no full per-tick exports; compact rows were hashed in memory.
The maximum file found under the phase scratch directory was 33,382,373 bytes
(an existing full-suite artifact fixture), below 200,000,000 bytes.

#### B1 — physical prefixes and decision-only exceptions

S10: physical prefix ticks 1–1058 identical; first BASE rejection tick 1059.
H2 informed, repetitions 1 and 2: physical prefix ticks 1–10070 identical;
first BASE rejected command tick 10071.
H2 informed's only pre-rejection decision differences, in both repetitions:

| tick | sim time used by decision | BASE action/target/blocked_by | candidate action/target/blocked_by |
|---|---:|---|---|
|5081|25400.0|commit / gt-spin-02 / empty string|hold / null / no eligible turbine: gt-spin-02=min_down|
|5082|25405.0|commit / gt-spin-02 / empty string|hold / null / no eligible turbine: gt-spin-02=min_down|
|5083|25410.0|commit / gt-spin-02 / empty string|hold / null / no eligible turbine: gt-spin-02=min_down|

At each: BASE reason=`reserve floor violated: 25.0 MW < 27.0 MW`;
candidate reason=`commit condition met (U=0.079, floor_violated=True)`.
BASE target state=offline, hot_standby=False, min_down_enabled=True,
stop_time=25400.0, min_down=900.0, elapsed=0.0/5.0/10.0 respectively,
eligible=False, reason=min_down, adjudicated=True, accepted=False.
No other scenario/arm/repetition had a telemetry-only exception.
The seven app-path no-rejection scenarios below, H1 both arms twice,
H2 baseline and base demo both arms were whole-run identical to BASE.

#### B2 — S10 (fresh values identical to previous candidate)

| field | BASE | D2-a |
|---|---:|---:|
|ticks|17280|17280|
|rejected starts|1154 (1132 core, 22 pre-staging)|0|
|accepted starts|32|38|
|ineligibility episodes|0|8|
|collapse|null (no)|null (no)|
|minimum BESS SoC|0.0|0.0|
|minimum Hz|-737.1409980342337|-729.1075118080669|
|maximum Hz|998.9330534505464|998.9330534505464|
|unserved MWh|12.5194325350618|10.600341682490331|
|balance-failure ticks|0|0|

BASE physical SHA-256: `51dfe89b51138d85930b01684c95c58d60d7dcd1ed0c36801657c9d41840ef52`.
D2-a physical SHA-256: `4370c9ebfbfc90d2812cad93285c9749645974502508e8188c3567eb3e60d34d`.
The complete accepted-start timelines and episode records in the historical
B2 JSON below are unchanged; exact trace equality was independently checked
against that candidate. These unprotected frequency extrema remain findings,
not a claim of valid protection behavior; Phase 3 did not alter frequency.

#### B3/B4 — whole-run app-path hashes, BASE = D2-a

| scenario | ticks | physical SHA-256 (both versions) |
|---|---:|---|
|demo-islanded-ramp|2160|fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a|
|scenario-equinix-sj-1|720|328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84|
|scenario-turbine-01|720|006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a|
|scenario-hybrid-ai-100mw-addendum-i|120|9377f009785094697116d356ef554985107ce1ee4c92f01c672f4b30b5f7577a|
|scenario-100mw-fuel-cell-bess-diesel|252|565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b|
|scenario-fc100-islanded-v2|264|d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3|
|scenario-fc100-islanded-zero-hot-v2|264|d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2|

All seven have zero rejected starts before and after.

#### B5 — H references

H1, both arms, two repetitions each: all 27 metrics and compact ticks identical
to BASE; 17280 ticks each. Both repetitions have the following hashes:

| arm | physical SHA-256 (BASE = D2-a) | compact-tick SHA-256 (BASE = D2-a) |
|---|---|---|
|baseline|57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b|e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755|
|informed|60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9|19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2|

H2 baseline: physical SHA-256 remains
`f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1`.
All 27 metrics identical. The pre-existing start-reconciliation FAIL remains:
recorded_event_count=6, measured_event_count=11, measured_start_fuel_mmbtu=124.0,
tier_sum_mmbtu=124.0, passed=False, constraints_valid=False, five hard violations.
Each violation concerns gt-hot-01 asset start counts 2–6 versus log=1,
`untracked_path=production_command_or_cascade`.

H2 informed, two repetitions: identical to each other and the previous candidate.
The full metric records retained below were reverified field by field.

| metric | BASE | D2-a |
|---|---:|---:|
|load fuel MMBtu|5107.722017303|5106.733034717|
|no-load fuel MMBtu|64.866666667|64.855|
|hot-standby fuel MMBtu|3.761458333|3.761458333|
|start fuel MMBtu|152.0|152.0|
|total turbine fuel MMBtu|5328.350142303|5327.34949305|
|curtailment MWh|343.106291593|342.977539092|
|attributable curtailment fuel MMBtu|3608.878484911|3607.524008603|
|interval-exposure curtailment fuel MMBtu|4894.248370795|4892.43517635|
|unserved MWh|0.893328423|0.859772492|
|peak unserved MW|42.36838787|42.36838787|
|recorded/measured starts|14 / 14|14 / 14|
|rejected starts|6|0|
|start-fuel reconciliation|PASS|PASS|
|constraints_valid / hard_violations|True / []|True / []|
|BESS SoC minimum|0.950386947|0.950386947|
|BESS SoC final|0.999999987|0.999999987|
|forecast misses count / peak MW|39 / 13.130749226769357|39 / 13.130749226769357|
|stop-floor refusals|14890|14904|

The replacement start is gt-hot-02 at 50350.0 s, tick 10071, versus 50385.0 s,
tick 10078, in BASE. gt-hot-01 at 50380.0 s is retained.
No new rejected command or guard failure appears.
Physical hashes: BASE=`3b40147d28ee89f1ec312b7f57f1c9f77e82c99bd7e6ee4447ff5384f951dbdf`;
D2-a=`b7383d283f09d625f531ecc216b447b868792f50069bbc662b1636d2b988bbfb`.
Compact hashes: BASE=`6ae0ce3d7a1b300cd4402fbd640abc67addb953b453075454c39bdefad8b0711`;
D2-a=`0def2a33daa2770e5095d8cb63b2c5e7d01ab65c85aaf4db3bd732a89623a3c7`.

H2 compare_runs is FAIL before and after, solely `baseline_valid=False`.
The other nine conditions are True in both comparisons: build_parity,
informed_valid, baseline_energy_balance, informed_energy_balance,
baseline_fuel_reconciled, informed_fuel_reconciled, identical_compute_trace,
informed_unserved_energy_no_worse, informed_peak_unserved_no_worse.
The invalid baseline was not silently recertified.

#### B6 — base demo equals 2026-10-21 production record

| arm | curtailment MWh | turbine fuel MMBtu | unserved MWh | peak unserved MW |
|---|---:|---:|---:|---:|
|baseline|8.136511735|714.363019086|0.351692658|22.309362466|
|informed|5.278943188|665.398247704|0.020719074|7.52325057|

1440 ticks each. All 27 metrics and whole-run hashes equal BASE.
Baseline physical SHA-256: `90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1`.
Informed physical SHA-256: `ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6`.
compare_runs=PASS before/after; all ten conditions listed above are True,
including baseline_valid.

### 3.Q — full suite, real package, COMPLETE

Command, from P:
```text
PYTHONPATH=/tmp/DR-ISL-phase3/finish:$PWD pytest -q -p dr_isl_incremental --junitxml=/tmp/DR-ISL-phase3/finish/suite_d2a_native.xml
15 failed, 2152 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 719.19s (0:11:59)
PYTEST_EXIT=1
```
Native JUnit: tests=2196, failures=15, errors=0, skipped=26;
the native count includes 3 passing subtests, and skipped includes xfails.
Incremental parseable JUnit: `/tmp/DR-ISL-phase3/finish/suite_incremental.xml`.
Native JUnit: `/tmp/DR-ISL-phase3/finish/suite_d2a_native.xml`.
Log: `/tmp/DR-ISL-phase3/finish/suite_d2a.log`.

Set comparison against `tools/dr_isl/PHASE_2D_FAILING_TESTS.txt`:
**added=[], removed=[], remaining=15**.
`tools/dr_isl/PHASE_3_FAILING_TESTS.txt` is byte-identical to that 15-ID baseline.
TC125 and TC132 both pass in the full suite as well as the focused run.
The suite is not all-green: the 15 existing failures remain unmodified.
The historical 17-failure candidate suite below is superseded, not the final result.

### 3.R — local commits, changed paths and startup verification

Implementation commit:
`52ef570508fd9f3fd3b858761d7213ceddcf3b02`
`D2 (IMPL-ISL-5): single start-eligibility function; commitment picks the first eligible unit`

D2-a tests commit:
`c9d7907d2bb3c1f52aa67ed56f746c7ee0a46bc7`
`D2-a: tests follow single start-eligibility (hot-standby veto; shared min-down wording)`

Implementation paths (new-side hunk ranges, all relative to P):
- `core/asset_modules.py`: 1057–1068, 1081–1083, 1120–1122, 1140, 1151–1152.
- `core/commitment.py`: 329–341, 344.
- `core/dispatch.py`: 593–594 (start pre-staging guard only; no allocation-policy change).
- `core/models.py`: 748–752.
- `core/simulation_core.py`: 294, 602, 621–665, 676, 763, 2223, 2226–2229, 2285, 2358, 2578.
- `runtime/run_manager.py`: 1522–1524, 1526.
- `runtime/turbine_commitment.py`: 622–640, 836, 1204–1206, 1209.
- `tests/test_dr_isl_start_eligibility.py`: 1–140 (new, force-tracked).
D2-a test paths:
- `tests/test_addendum_h_phase2a_commitment.py`: 588–592, 595, 824–825.
- `tests/test_dr_isl_hot_standby_veto.py`: 1–28 (new, force-tracked).

The full production diff and original TC-ISL-06a–d source are retained in the
historical sections below; application code was verified byte-identical to the
previous candidate before these test-only changes.
Reproduce the exact final diff with `git diff f6d9811..c9d7907 -- P`.
No scenario JSON or floor/diesel/frequency/protection code was edited.
The report-only commit includes this report and `PHASE_3_FAILING_TESTS.txt`;
its self-hash is reported separately in the delivery message.

The development workflow `artifacts/gridsignal: web` was restarted once after
validation: startup completed, Uvicorn listening on 0.0.0.0:22126, GET / = 200.
Evidence: `/tmp/logs/artifactsgridsignal_web_20261022_134413_687_880def02.log`.
Existing catalogue coverage warnings remain (including unset base_load_mw).
The app-preview screenshot rendered the operator sign-in page; its unauthenticated
browser also logged a 401. No signed-in UI journey is claimed by that check.
The separate Node API workflow's root 404 is not the simulator startup result.
Neither workflow restart nor these local commits published the app.

Automatic checkpoint `f6d9811` at entry was report-only. Earlier unvalidated
candidate checkpoints/restorations described below are historical; final
implementation validation applies to the explicit commit pair above.
The candidate stash is retained. No STOP condition occurred in this resumption.

## Historical reports — superseded status statements retained for audit

**STATUS: STOPPED at 3.4: added failures.**

Application baseline: `134538067d4eb4c2ce14232e483e9a91fd31276b`; initial HEAD: `24b177194aa979fc889e892195e8d5ba37603bb6`.
Observed HEAD while rendering: `24b177194aa979fc889e892195e8d5ba37603bb6`.
Implementation commit: `None`.
Retained original stash: `b416122acfa07c59d4a3521a90361d5be775d612`.
On STOP, recovered candidate stash: `c52218ee0e35597eac442cabaa04e839ebc50273`; BASE application diff empty: `True`.
No Phase 4, scenario edits, publish, deploy or push.
Candidate source was validated before commit as `24b1771-dirty-49b1b6d058516329`; the full eight-file diff SHA-256 is `49b1b6d0585163299191a8faea64ac84ba67940f2647c8ef132c5b97dcdbe402`. Provenance is not rewritten to pretend a pre-commit run used a later commit.
Prior automatic checkpoint `5716d22` was unvalidated and reverted before this resumption; the restored candidate is validated only by the gates below.

## 3.I restoration, one eligibility predicate, and 3.F
`git stash apply b416122` conflicted because the stash's parent already contained the checkpointed candidate.
The exact eight candidate paths were restored from the complete stash tree; `git diff b416122 -- P` was empty before the two authorized edits.
The stash was kept. P denotes `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim`.
TurbineModule.command_start's own guard conditions and their order remain hot-standby, state, minimum down time.
The informed adjudicator's duplicate minimum-down branch now calls the shared predicate and uses its reason.
No changes to dispatch policy, costs, reserve floors, diesel logic, frequency, protection or scenario JSON were made.

Candidate line references (from the stashed candidate on STOP, not active restored BASE; also preserved in the literal diff below):
- P/core/asset_modules.py:1057–1067: `start_eligibility`.
- P/core/asset_modules.py:1069–1118: `command_start`.
- P/core/asset_modules.py:1122–1153: `unit_availability`.
- P/core/simulation_core.py:621–634: `_offline_turbines_by_thermal_priority`.
- P/core/simulation_core.py:654–663: `_log_start_ineligibility_episode`.
- P/runtime/turbine_commitment.py:1182–1287: `adjudicate_core_proposal`.

3.F: `_log_start_ineligibility_episode` checks `isinstance(decision.blocked_by, str)` before `startswith`; ordinary holds with `None` do not log or raise.
TC-ISL-06a call-graph now includes runtime/turbine_commitment.py and rejects duplicate adjudicator guard attributes.
TC-ISL-06b alternate selection, TC-ISL-06c one log per episode, TC-ISL-06d ordinary-hold safety, and guard-boundary preservation passed.
Literal targeted output:
```
.....                                                                    [100%]
5 passed in 3.69s
```
The full base-demo baseline/informed and H2 informed runs below completed without exception.

## 3.J B1 — revised prefix acceptance
Full physical hash contract: SHA-256 over ticks in order, one compact sorted-key UTF-8 JSON object plus LF; NaN allowed; exclusions exactly `advisory_telemetry`, `fabric_modal`, `wall_stamp_utc`, `insufficient_reserve_proposal_id`.
The separate prefix digest additionally excludes only the four approved decision fields. It does not replace or redefine the full hash.
Every other prefix field is checked literally. Each changed decision tick also proves native BASE adjudication vetoed an ineligible target.

| Scenario / arm / repetition | Ticks | First BASE rejection cutoff | Decision exceptions | Prefix hash BASE = candidate |
|---|---:|---:|---|---|
| S10_mit_supercloud_2021-08-11/app/1 | 17280 | 1059 | [] | `32c73e35031a3d3eee9e64936a2bdd1d7a553c42f3598b5236886540aaa2e729` = `32c73e35031a3d3eee9e64936a2bdd1d7a553c42f3598b5236886540aaa2e729` |
| demo-islanded-ramp/app/1 | 2160 | never | [] | `ba31c790439bbf7319f11ffef63a3f17c9ce71f1973d032602b4eafe5ad8be7e` = `ba31c790439bbf7319f11ffef63a3f17c9ce71f1973d032602b4eafe5ad8be7e` |
| scenario-100mw-fuel-cell-bess-diesel/app/1 | 252 | never | [] | `1f78d166a2f78252c69801425c5e9a5bc9964df433fdae0a3e7da36a39142e6f` = `1f78d166a2f78252c69801425c5e9a5bc9964df433fdae0a3e7da36a39142e6f` |
| scenario-equinix-sj-1/app/1 | 720 | never | [] | `50e5021b2b5693add31d99a5a937b5784bcb768feb0ee9a7ebb1498952219247` = `50e5021b2b5693add31d99a5a937b5784bcb768feb0ee9a7ebb1498952219247` |
| scenario-fc100-islanded-v2/app/1 | 264 | never | [] | `2f6d60783aa249bdf50e7a1fac96613baf31a2f939747e93e4b3dc7221fda825` = `2f6d60783aa249bdf50e7a1fac96613baf31a2f939747e93e4b3dc7221fda825` |
| scenario-fc100-islanded-zero-hot-v2/app/1 | 264 | never | [] | `30715fa97b652b10f3c76a9f34a05fbc3c32f8f358d70c638140dcd1a18759ee` = `30715fa97b652b10f3c76a9f34a05fbc3c32f8f358d70c638140dcd1a18759ee` |
| scenario-h1-k8s-ray-24h/baseline/1 | 17280 | never | [] | `49b1865ac76c9472ccbc740c543b5e593aa310fc5aef564fe38aa0539bedf8a3` = `49b1865ac76c9472ccbc740c543b5e593aa310fc5aef564fe38aa0539bedf8a3` |
| scenario-h1-k8s-ray-24h/baseline/2 | 17280 | never | [] | `49b1865ac76c9472ccbc740c543b5e593aa310fc5aef564fe38aa0539bedf8a3` = `49b1865ac76c9472ccbc740c543b5e593aa310fc5aef564fe38aa0539bedf8a3` |
| scenario-h1-k8s-ray-24h/informed/1 | 17280 | never | [] | `3a061161b6f370fb90526dcbeac116de32b5bb85734ef94bafeb441d0d72aba0` = `3a061161b6f370fb90526dcbeac116de32b5bb85734ef94bafeb441d0d72aba0` |
| scenario-h1-k8s-ray-24h/informed/2 | 17280 | never | [] | `3a061161b6f370fb90526dcbeac116de32b5bb85734ef94bafeb441d0d72aba0` = `3a061161b6f370fb90526dcbeac116de32b5bb85734ef94bafeb441d0d72aba0` |
| scenario-h2-slurm-24h/baseline/1 | 17280 | never | [] | `4b187cafa41d30e4262ca83639bffb6037effdaae5d1b6719dffc351918cafff` = `4b187cafa41d30e4262ca83639bffb6037effdaae5d1b6719dffc351918cafff` |
| scenario-h2-slurm-24h/informed/1 | 17280 | 10071 | [5081, 5082, 5083] | `eb128312dd425180c297ed2bf2c106bc4a5a8ef9c79becdb7b70da077f05edf4` = `eb128312dd425180c297ed2bf2c106bc4a5a8ef9c79becdb7b70da077f05edf4` |
| scenario-h2-slurm-24h/informed/2 | 17280 | 10071 | [5081, 5082, 5083] | `eb128312dd425180c297ed2bf2c106bc4a5a8ef9c79becdb7b70da077f05edf4` = `eb128312dd425180c297ed2bf2c106bc4a5a8ef9c79becdb7b70da077f05edf4` |
| scenario-hybrid-ai-100mw-addendum-i/app/1 | 120 | never | [] | `9d273480e242cb3ca9b77eb3428d9a0a871ecd64f5e6dc80f73e58e4e530bc7b` = `9d273480e242cb3ca9b77eb3428d9a0a871ecd64f5e6dc80f73e58e4e530bc7b` |
| scenario-turbine-01/app/1 | 720 | never | [] | `a496be65b3531fe518438bd0fd4325b2b0ea2f10f19af7608b38f6ba3985d035` = `a496be65b3531fe518438bd0fd4325b2b0ea2f10f19af7608b38f6ba3985d035` |
| scenario-uneven-multisched-01/baseline/1 | 1440 | never | [] | `ea29b0ed08e868b69ecd54a206a74611d9d6e524bbd064bf01dd9940cbeb809f` = `ea29b0ed08e868b69ecd54a206a74611d9d6e524bbd064bf01dd9940cbeb809f` |
| scenario-uneven-multisched-01/informed/1 | 1440 | never | [] | `01b5437cf924d644abfeb899a076e5c559e608d099ed96a8a19486b06c00b7c3` = `01b5437cf924d644abfeb899a076e5c559e608d099ed96a8a19486b06c00b7c3` |

Every approved decision exception (both versions, all changed fields and native veto):
```json
{
  "scenario-h2-slurm-24h/informed/1": [
    {
      "tick": 5081,
      "diffs": {
        "commitment_blocked_by": {
          "base": "",
          "candidate": "no eligible turbine: gt-spin-02=min_down"
        },
        "commitment_target_unit_id": {
          "base": "gt-spin-02",
          "candidate": null
        },
        "commitment_action": {
          "base": "commit",
          "candidate": "hold"
        },
        "commitment_reason": {
          "base": "reserve floor violated: 25.0 MW < 27.0 MW",
          "candidate": "commit condition met (U=0.079, floor_violated=True)"
        }
      },
      "base_veto": {
        "unit": "gt-spin-02",
        "state": "offline",
        "eligible": false,
        "reason": "min_down",
        "time": 25400.0,
        "min_down_enabled": true,
        "stop_time": 25400.0,
        "min_down": 900.0,
        "elapsed": 0.0,
        "hot_standby": false,
        "adjudicated": true,
        "accepted": false
      }
    },
    {
      "tick": 5082,
      "diffs": {
        "commitment_blocked_by": {
          "base": "",
          "candidate": "no eligible turbine: gt-spin-02=min_down"
        },
        "commitment_target_unit_id": {
          "base": "gt-spin-02",
          "candidate": null
        },
        "commitment_action": {
          "base": "commit",
          "candidate": "hold"
        },
        "commitment_reason": {
          "base": "reserve floor violated: 25.0 MW < 27.0 MW",
          "candidate": "commit condition met (U=0.079, floor_violated=True)"
        }
      },
      "base_veto": {
        "unit": "gt-spin-02",
        "state": "offline",
        "eligible": false,
        "reason": "min_down",
        "time": 25405.0,
        "min_down_enabled": true,
        "stop_time": 25400.0,
        "min_down": 900.0,
        "elapsed": 5.0,
        "hot_standby": false,
        "adjudicated": true,
        "accepted": false
      }
    },
    {
      "tick": 5083,
      "diffs": {
        "commitment_blocked_by": {
          "base": "",
          "candidate": "no eligible turbine: gt-spin-02=min_down"
        },
        "commitment_target_unit_id": {
          "base": "gt-spin-02",
          "candidate": null
        },
        "commitment_action": {
          "base": "commit",
          "candidate": "hold"
        },
        "commitment_reason": {
          "base": "reserve floor violated: 25.0 MW < 27.0 MW",
          "candidate": "commit condition met (U=0.079, floor_violated=True)"
        }
      },
      "base_veto": {
        "unit": "gt-spin-02",
        "state": "offline",
        "eligible": false,
        "reason": "min_down",
        "time": 25410.0,
        "min_down_enabled": true,
        "stop_time": 25400.0,
        "min_down": 900.0,
        "elapsed": 10.0,
        "hot_standby": false,
        "adjudicated": true,
        "accepted": false
      }
    }
  ],
  "scenario-h2-slurm-24h/informed/2": [
    {
      "tick": 5081,
      "diffs": {
        "commitment_reason": {
          "base": "reserve floor violated: 25.0 MW < 27.0 MW",
          "candidate": "commit condition met (U=0.079, floor_violated=True)"
        },
        "commitment_target_unit_id": {
          "base": "gt-spin-02",
          "candidate": null
        },
        "commitment_blocked_by": {
          "base": "",
          "candidate": "no eligible turbine: gt-spin-02=min_down"
        },
        "commitment_action": {
          "base": "commit",
          "candidate": "hold"
        }
      },
      "base_veto": {
        "unit": "gt-spin-02",
        "state": "offline",
        "eligible": false,
        "reason": "min_down",
        "time": 25400.0,
        "min_down_enabled": true,
        "stop_time": 25400.0,
        "min_down": 900.0,
        "elapsed": 0.0,
        "hot_standby": false,
        "adjudicated": true,
        "accepted": false
      }
    },
    {
      "tick": 5082,
      "diffs": {
        "commitment_reason": {
          "base": "reserve floor violated: 25.0 MW < 27.0 MW",
          "candidate": "commit condition met (U=0.079, floor_violated=True)"
        },
        "commitment_target_unit_id": {
          "base": "gt-spin-02",
          "candidate": null
        },
        "commitment_blocked_by": {
          "base": "",
          "candidate": "no eligible turbine: gt-spin-02=min_down"
        },
        "commitment_action": {
          "base": "commit",
          "candidate": "hold"
        }
      },
      "base_veto": {
        "unit": "gt-spin-02",
        "state": "offline",
        "eligible": false,
        "reason": "min_down",
        "time": 25405.0,
        "min_down_enabled": true,
        "stop_time": 25400.0,
        "min_down": 900.0,
        "elapsed": 5.0,
        "hot_standby": false,
        "adjudicated": true,
        "accepted": false
      }
    },
    {
      "tick": 5083,
      "diffs": {
        "commitment_reason": {
          "base": "reserve floor violated: 25.0 MW < 27.0 MW",
          "candidate": "commit condition met (U=0.079, floor_violated=True)"
        },
        "commitment_target_unit_id": {
          "base": "gt-spin-02",
          "candidate": null
        },
        "commitment_blocked_by": {
          "base": "",
          "candidate": "no eligible turbine: gt-spin-02=min_down"
        },
        "commitment_action": {
          "base": "commit",
          "candidate": "hold"
        }
      },
      "base_veto": {
        "unit": "gt-spin-02",
        "state": "offline",
        "eligible": false,
        "reason": "min_down",
        "time": 25410.0,
        "min_down_enabled": true,
        "stop_time": 25400.0,
        "min_down": 900.0,
        "elapsed": 10.0,
        "hot_standby": false,
        "adjudicated": true,
        "accepted": false
      }
    }
  ]
}
```

## B2 — S10

### base
```json
{
  "ticks": 17280,
  "rejected": 1154,
  "rejected_by_caller": {
    "stage_for_predicted_step": 22,
    "evaluate_tick": 1132
  },
  "rejected_by_unit": {
    "turbine-3": 576,
    "turbine-4": 483,
    "turbine-1": 94,
    "turbine-2": 1
  },
  "first_rejection": {
    "tick": 1059,
    "sim_time": 5288.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "offline",
    "reason": "min_down",
    "source": "stage_for_predicted_step"
  },
  "collapse": null,
  "bess_soc_min": 0.0,
  "frequency_hz": [
    -737.1409980342337,
    998.9330534505464
  ],
  "unserved_mwh": 12.5194325350618,
  "physical_sha256": "51dfe89b51138d85930b01684c95c58d60d7dcd1ed0c36801657c9d41840ef52",
  "balance_failures": [],
  "ineligibility_episodes": []
}
```
All accepted command-start times (sim_time is the command's argument; pre-staging may use an event time):
```json
[
  {
    "tick": 1,
    "sim_time": 0.0,
    "unit": "turbine-1",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 107,
    "sim_time": 527.0,
    "unit": "turbine-2",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 226,
    "sim_time": 1125.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 420,
    "sim_time": 2092.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 1216,
    "sim_time": 6075.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 1375,
    "sim_time": 6867.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 2012,
    "sim_time": 10055.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 2072,
    "sim_time": 10355.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 2906,
    "sim_time": 14525.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 3549,
    "sim_time": 17740.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 3609,
    "sim_time": 18040.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 5271,
    "sim_time": 26347.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 6667,
    "sim_time": 33330.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 6832,
    "sim_time": 34155.0,
    "unit": "turbine-1",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 6892,
    "sim_time": 34455.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 6964,
    "sim_time": 34815.0,
    "unit": "turbine-2",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 7479,
    "sim_time": 37390.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 8150,
    "sim_time": 40745.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 8639,
    "sim_time": 43186.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 10491,
    "sim_time": 52449.0,
    "unit": "turbine-2",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 10550,
    "sim_time": 52745.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 10622,
    "sim_time": 53105.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 11514,
    "sim_time": 57565.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 11574,
    "sim_time": 57865.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 14726,
    "sim_time": 73623.0,
    "unit": "turbine-2",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 14789,
    "sim_time": 73940.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 14859,
    "sim_time": 74290.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 15530,
    "sim_time": 77642.0,
    "unit": "turbine-2",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 15621,
    "sim_time": 78099.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 15810,
    "sim_time": 79044.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 16562,
    "sim_time": 82804.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 16720,
    "sim_time": 83593.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  }
]
```
### candidate
```json
{
  "ticks": 17280,
  "rejected": 0,
  "rejected_by_caller": {},
  "rejected_by_unit": {},
  "first_rejection": null,
  "collapse": null,
  "bess_soc_min": 0.0,
  "frequency_hz": [
    -729.1075118080669,
    998.9330534505464
  ],
  "unserved_mwh": 10.600341682490331,
  "physical_sha256": "4370c9ebfbfc90d2812cad93285c9749645974502508e8188c3567eb3e60d34d",
  "balance_failures": [],
  "ineligibility_episodes": [
    "Commitment engine: no eligible turbine: turbine-3=min_down; turbine-4=min_down at sim_time=5345.0",
    "Commitment engine: no eligible turbine: turbine-3=min_down at sim_time=9865.0",
    "Commitment engine: no eligible turbine: turbine-4=min_down at sim_time=13730.0",
    "Commitment engine: no eligible turbine: turbine-4=min_down at sim_time=16820.0",
    "Commitment engine: no eligible turbine: turbine-4=min_down at sim_time=36595.0",
    "Commitment engine: no eligible turbine: turbine-4=min_down at sim_time=39960.0",
    "Commitment engine: no eligible turbine: turbine-4=min_down; turbine-3=min_down at sim_time=56825.0",
    "Commitment engine: no eligible turbine: turbine-4=min_down at sim_time=59980.0"
  ]
}
```
All accepted command-start times (sim_time is the command's argument; pre-staging may use an event time):
```json
[
  {
    "tick": 1,
    "sim_time": 0.0,
    "unit": "turbine-1",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 107,
    "sim_time": 527.0,
    "unit": "turbine-2",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 226,
    "sim_time": 1125.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 420,
    "sim_time": 2092.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 1191,
    "sim_time": 5950.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 1375,
    "sim_time": 6867.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 1915,
    "sim_time": 9569.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 1987,
    "sim_time": 9930.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 2906,
    "sim_time": 14525.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 3524,
    "sim_time": 17615.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 3584,
    "sim_time": 17915.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 5271,
    "sim_time": 26347.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 6662,
    "sim_time": 33303.0,
    "unit": "turbine-2",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 6733,
    "sim_time": 33660.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 6805,
    "sim_time": 34020.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 6877,
    "sim_time": 34380.0,
    "unit": "turbine-1",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 7479,
    "sim_time": 37390.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 7539,
    "sim_time": 37690.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 8150,
    "sim_time": 40745.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 8639,
    "sim_time": 43186.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 9389,
    "sim_time": 46938.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 10491,
    "sim_time": 52449.0,
    "unit": "turbine-2",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 10550,
    "sim_time": 52745.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 10622,
    "sim_time": 53105.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 11489,
    "sim_time": 57440.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 11549,
    "sim_time": 57740.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 12154,
    "sim_time": 60765.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "evaluate_tick"
  },
  {
    "tick": 12517,
    "sim_time": 62576.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 14726,
    "sim_time": 73623.0,
    "unit": "turbine-2",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 14789,
    "sim_time": 73940.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 14859,
    "sim_time": 74290.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 15474,
    "sim_time": 77365.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 15558,
    "sim_time": 77785.0,
    "unit": "turbine-2",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 15621,
    "sim_time": 78099.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 16161,
    "sim_time": 80798.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 16254,
    "sim_time": 81262.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 16779,
    "sim_time": 83890.0,
    "unit": "turbine-4",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  },
  {
    "tick": 16868,
    "sim_time": 84335.0,
    "unit": "turbine-3",
    "before": "offline",
    "after": "starting",
    "reason": "eligible",
    "source": "stage_for_predicted_step"
  }
]
```

## B3/B4 — no-rejection regressions

| Scenario | Ticks | Rejections BASE / candidate | Full physical SHA-256 (identical) |
|---|---:|---:|---|
| demo-islanded-ramp | 2160 | 0 / 0 | `fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a` |
| scenario-100mw-fuel-cell-bess-diesel | 252 | 0 / 0 | `565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b` |
| scenario-equinix-sj-1 | 720 | 0 / 0 | `328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84` |
| scenario-fc100-islanded-v2 | 264 | 0 / 0 | `d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3` |
| scenario-fc100-islanded-zero-hot-v2 | 264 | 0 / 0 | `d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2` |
| scenario-hybrid-ai-100mw-addendum-i | 120 | 0 / 0 | `9377f009785094697116d356ef554985107ce1ee4c92f01c672f4b30b5f7577a` |
| scenario-turbine-01 | 720 | 0 / 0 | `006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a` |

## B5 — H1 certified identity and H2 baseline / informed

H1: both arms, two repetitions; all physical fields, native compact rows and all 27 collector metric fields are identical to BASE.
H2 baseline: physically and metrically identical, including its pre-existing start-fuel reconciliation failure.
Native records use seed None for H references and seed 42 for the base demo, `reuse_cache=False`; BASE/candidate pins are identical.
Native study `_expanded_spec`, `_probe`, `_run_mode`, MetricsCollector and compare_metrics were used. Cache/artifact writers were in-memory observers.
Before/after comparisons use honest per-version engine provenance and matching harness provenance, not fabricated cross-build parity.

| Scenario / arm / repetition | Full physical hash BASE | Full physical hash candidate | Native compact BASE | Native compact candidate |
|---|---|---|---|---|
| scenario-h1-k8s-ray-24h/baseline/1 | `57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b` | `57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b` | `e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755` | `e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755` |
| scenario-h1-k8s-ray-24h/baseline/2 | `57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b` | `57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b` | `e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755` | `e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755` |
| scenario-h1-k8s-ray-24h/informed/1 | `60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9` | `60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9` | `19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2` | `19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2` |
| scenario-h1-k8s-ray-24h/informed/2 | `60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9` | `60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9` | `19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2` | `19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2` |
| scenario-h2-slurm-24h/baseline/1 | `f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1` | `f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1` | `8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66` | `8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66` |
| scenario-h2-slurm-24h/informed/1 | `3b40147d28ee89f1ec312b7f57f1c9f77e82c99bd7e6ee4447ff5384f951dbdf` | `b7383d283f09d625f531ecc216b447b868792f50069bbc662b1636d2b988bbfb` | `6ae0ce3d7a1b300cd4402fbd640abc67addb953b453075454c39bdefad8b0711` | `0def2a33daa2770e5095d8cb63b2c5e7d01ab65c85aaf4db3bd732a89623a3c7` |
| scenario-h2-slurm-24h/informed/2 | `3b40147d28ee89f1ec312b7f57f1c9f77e82c99bd7e6ee4447ff5384f951dbdf` | `b7383d283f09d625f531ecc216b447b868792f50069bbc662b1636d2b988bbfb` | `6ae0ce3d7a1b300cd4402fbd640abc67addb953b453075454c39bdefad8b0711` | `0def2a33daa2770e5095d8cb63b2c5e7d01ab65c85aaf4db3bd732a89623a3c7` |

H2 informed — full metric table (each cell is the native literal value):
| Metric | BASE | Candidate |
|---|---|---|
| tick_count | `17280` | `17280` |
| interval_seconds | `5.0` | `5.0` |
| fuel_by_component_mmbtu | `{"load_fuel_mmbtu": 5107.722017303, "no_load_fuel_mmbtu": 64.866666667, "hot_standby_fuel_mmbtu": 3.761458333, "start_fuel_mmbtu": 152.0}` | `{"load_fuel_mmbtu": 5106.733034717, "no_load_fuel_mmbtu": 64.855, "hot_standby_fuel_mmbtu": 3.761458333, "start_fuel_mmbtu": 152.0}` |
| turbine_fuel_mmbtu | `5328.350142303` | `5327.34949305` |
| fuel_reconciled | `true` | `true` |
| start_fuel_reconciliation | `{"release_charged": true, "recorded_event_count": 14, "measured_event_count": 14, "measured_start_fuel_mmbtu": 152.0, "tier_sum_mmbtu": null, "passed": true}` | `{"release_charged": true, "recorded_event_count": 14, "measured_event_count": 14, "measured_start_fuel_mmbtu": 152.0, "tier_sum_mmbtu": null, "passed": true}` |
| dispatch_curtailment_mwh | `343.106291593` | `342.977539092` |
| dispatch_curtailment_interval_exposure_fuel_mmbtu | `4894.248370795` | `4892.43517635` |
| dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu | `{"load_fuel_mmbtu": 4677.688023572, "no_load_fuel_mmbtu": 60.918333333, "hot_standby_fuel_mmbtu": 3.642013889, "start_fuel_mmbtu": 152.0}` | `{"load_fuel_mmbtu": 4675.898162461, "no_load_fuel_mmbtu": 60.895, "hot_standby_fuel_mmbtu": 3.642013889, "start_fuel_mmbtu": 152.0}` |
| dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu | `{"gt-spin-01": 2152.666217898, "gt-spin-02": 1708.675833457, "gt-hot-01": 738.419791667, "gt-hot-02": 294.486527778}` | `{"gt-spin-01": 2152.666217898, "gt-spin-02": 1708.675833457, "gt-hot-01": 737.513194445, "gt-hot-02": 293.579930556}` |
| dispatch_curtailment_attributable_fuel_mmbtu | `3608.878484911` | `3607.524008603` |
| dispatch_curtailment_attributable_fuel_by_unit_mmbtu | `{"gt-spin-01": 1645.626267003, "gt-spin-02": 1260.837847434, "gt-hot-01": 537.463176576, "gt-hot-02": 164.951193898}` | `{"gt-spin-01": 1645.630131731, "gt-spin-02": 1260.841712162, "gt-hot-01": 536.782073718, "gt-hot-02": 164.270090991}` |
| unserved_mwh | `0.893328423` | `0.859772492` |
| peak_unserved_mw | `42.36838787` | `42.36838787` |
| served_mwh | `143.067046027` | `143.100601957` |
| unserved_intervals | `[{"start_sim_time_s": 29130.0, "end_sim_time_s": 29165.0, "peak_unserved_mw": 19.287968405751712}, {"start_sim_time_s": 29215.0, "end_sim_time_s": 29235.0, "peak_unserved_mw": 1.8802011558611156}, {"start_sim_time_s": 36310.0, "end_sim_time_s": 36350.0, "peak_unserved_mw": 38.394865912415625}, {"start_sim_time_s": 43510.0, "end_sim_time_s": 43555.0, "peak_unserved_mw": 39.4036584956214}, {"start_sim_time_s": 50710.0, "end_sim_time_s": 50730.0, "peak_unserved_mw": 29.140845418775996}, {"start_sim_time_s": 50750.0, "end_sim_time_s": 50760.0, "peak_unserved_mw": 1.25}, {"start_sim_time_s": 57910.0, "end_sim_time_s": 57940.0, "peak_unserved_mw": 42.36838786968556}, {"start_sim_time_s": 65110.0, "end_sim_time_s": 65140.0, "peak_unserved_mw": 37.890845418775996}]` | `[{"start_sim_time_s": 29130.0, "end_sim_time_s": 29165.0, "peak_unserved_mw": 19.287968405751712}, {"start_sim_time_s": 29215.0, "end_sim_time_s": 29235.0, "peak_unserved_mw": 1.8802011558611156}, {"start_sim_time_s": 36310.0, "end_sim_time_s": 36350.0, "peak_unserved_mw": 38.394865912415625}, {"start_sim_time_s": 43510.0, "end_sim_time_s": 43555.0, "peak_unserved_mw": 39.4036584956214}, {"start_sim_time_s": 50710.0, "end_sim_time_s": 50725.0, "peak_unserved_mw": 26.640845418775996}, {"start_sim_time_s": 57910.0, "end_sim_time_s": 57940.0, "peak_unserved_mw": 42.36838786968556}, {"start_sim_time_s": 65110.0, "end_sim_time_s": 65140.0, "peak_unserved_mw": 37.890845418775996}]` |
| energy_balance | `{"closure_status": true, "max_abs_physical_ledger_defect_mw": 0.0, "served_demand_mwh": 143.067046027, "unserved_demand_mwh": 0.893328423}` | `{"closure_status": true, "max_abs_physical_ledger_defect_mw": 0.0, "served_demand_mwh": 143.100601957, "unserved_demand_mwh": 0.859772492}` |
| bess_soc_min | `0.950386947` | `0.950386947` |
| bess_soc_max | `0.999999998` | `0.999999998` |
| bess_soc_final | `0.999999987` | `0.999999987` |
| commitment | `{"distinct_event_count": 67, "visible_distinct_event_count": 67, "suppressed_repeat_count": 11205, "log_complete": true, "omitted_record_count": 0, "reserve_floor_refusal_count": 14890, "reserve_floor_distinct_event_count": 14890, "reserve_floor_visible_distinct_event_count": 14890, "reserve_floor_suppressed_repeat_count": 0, "reserve_floor_log_complete": true, "reserve_floor_omitted_record_count": 0, "same_unit_restart_within_min_down_window_count": 0}` | `{"distinct_event_count": 65, "visible_distinct_event_count": 65, "suppressed_repeat_count": 11198, "log_complete": true, "omitted_record_count": 0, "reserve_floor_refusal_count": 14904, "reserve_floor_distinct_event_count": 14904, "reserve_floor_visible_distinct_event_count": 14904, "reserve_floor_suppressed_repeat_count": 0, "reserve_floor_log_complete": true, "reserve_floor_omitted_record_count": 0, "same_unit_restart_within_min_down_window_count": 0}` |
| forecast | `{"miss_count": 39, "miss_peak_mw": 13.130749227}` | `{"miss_count": 39, "miss_peak_mw": 13.130749227}` |
| compute_trace_sha256 | `"ea1916a426e67dde51a9a926dc4b64b0c2eb2470ee2e0076fe7f17b8d55f420b"` | `"ea1916a426e67dde51a9a926dc4b64b0c2eb2470ee2e0076fe7f17b8d55f420b"` |
| compute_trace_count | `17280` | `17280` |
| daily_breakdown | `[{"day": 1, "kind": "weekday", "fuel_by_component_mmbtu": {"load_fuel_mmbtu": 5107.722017303, "no_load_fuel_mmbtu": 64.866666667, "hot_standby_fuel_mmbtu": 3.761458333, "start_fuel_mmbtu": 152.0}, "fuel_mmbtu": 5328.350142303, "unserved_mwh": 0.893328423, "curtailed_mwh": 343.106291593, "bess_soc_end": 0.999999987}]` | `[{"day": 1, "kind": "weekday", "fuel_by_component_mmbtu": {"load_fuel_mmbtu": 5106.733034717, "no_load_fuel_mmbtu": 64.855, "hot_standby_fuel_mmbtu": 3.761458333, "start_fuel_mmbtu": 152.0}, "fuel_mmbtu": 5327.34949305, "unserved_mwh": 0.859772492, "curtailed_mwh": 342.977539092, "bess_soc_end": 0.999999987}]` |
| constraints_valid | `true` | `true` |
| hard_violations | `[]` | `[]` |

H2 informed guard results and replacement-start window:
```json
{
  "base": {
    "status": "PASS",
    "guard_failures": null,
    "rejected": [
      {
        "tick": 10071,
        "sim_time": 50350.0,
        "unit": "gt-hot-01",
        "before": "offline",
        "after": "offline",
        "reason": "min_down",
        "source": "drain_operator_commands"
      },
      {
        "tick": 10072,
        "sim_time": 50355.0,
        "unit": "gt-hot-01",
        "before": "offline",
        "after": "offline",
        "reason": "min_down",
        "source": "drain_operator_commands"
      },
      {
        "tick": 10073,
        "sim_time": 50360.0,
        "unit": "gt-hot-01",
        "before": "offline",
        "after": "offline",
        "reason": "min_down",
        "source": "drain_operator_commands"
      },
      {
        "tick": 10074,
        "sim_time": 50365.0,
        "unit": "gt-hot-01",
        "before": "offline",
        "after": "offline",
        "reason": "min_down",
        "source": "drain_operator_commands"
      },
      {
        "tick": 10075,
        "sim_time": 50370.0,
        "unit": "gt-hot-01",
        "before": "offline",
        "after": "offline",
        "reason": "min_down",
        "source": "drain_operator_commands"
      },
      {
        "tick": 10076,
        "sim_time": 50375.0,
        "unit": "gt-hot-01",
        "before": "offline",
        "after": "offline",
        "reason": "min_down",
        "source": "drain_operator_commands"
      }
    ],
    "starts_50350_to_50380": [
      {
        "tick": 10077,
        "sim_time": 50380.0,
        "unit": "gt-hot-01",
        "before": "offline",
        "after": "starting",
        "reason": "eligible",
        "source": "drain_operator_commands"
      }
    ],
    "removed_duplicate_guard_equivalence_checks": 0
  },
  "candidate": {
    "status": "PASS",
    "guard_failures": null,
    "rejected": [],
    "starts_50350_to_50380": [
      {
        "tick": 10071,
        "sim_time": 50350.0,
        "unit": "gt-hot-02",
        "before": "offline",
        "after": "starting",
        "reason": "eligible",
        "source": "drain_operator_commands"
      },
      {
        "tick": 10077,
        "sim_time": 50380.0,
        "unit": "gt-hot-01",
        "before": "offline",
        "after": "starting",
        "reason": "eligible",
        "source": "drain_operator_commands"
      }
    ],
    "removed_duplicate_guard_equivalence_checks": 1
  }
}
```
H2 baseline's unchanged reconciliation:
```json
{
  "base": {
    "status": "FAIL",
    "reconciliation": {
      "release_charged": true,
      "recorded_event_count": 6,
      "measured_event_count": 11,
      "measured_start_fuel_mmbtu": 124.0,
      "tier_sum_mmbtu": 124.0,
      "passed": false
    },
    "guard_failures": [
      {
        "type": "StartFuelReconciliationError",
        "message": "start fuel does not reconcile with recorded start events: reported=124.000000000, measured=124.000000000, recorded_events=6, measured_events=11, hot_standby_release_charged=True"
      }
    ]
  },
  "candidate": {
    "status": "FAIL",
    "reconciliation": {
      "release_charged": true,
      "recorded_event_count": 6,
      "measured_event_count": 11,
      "measured_start_fuel_mmbtu": 124.0,
      "tier_sum_mmbtu": 124.0,
      "passed": false
    },
    "guard_failures": [
      {
        "type": "StartFuelReconciliationError",
        "message": "start fuel does not reconcile with recorded start events: reported=124.000000000, measured=124.000000000, recorded_events=6, measured_events=11, hot_standby_release_charged=True"
      }
    ]
  }
}
```
Native H2 compare_runs/compare_metrics, before and after:
```json
{
  "base": {
    "conditions": {
      "build_parity": true,
      "baseline_valid": false,
      "informed_valid": true,
      "baseline_energy_balance": true,
      "informed_energy_balance": true,
      "baseline_fuel_reconciled": true,
      "informed_fuel_reconciled": true,
      "identical_compute_trace": true,
      "informed_unserved_energy_no_worse": true,
      "informed_peak_unserved_no_worse": true
    },
    "condition_order": [
      "build_parity",
      "baseline_valid",
      "informed_valid",
      "baseline_energy_balance",
      "informed_energy_balance",
      "baseline_fuel_reconciled",
      "informed_fuel_reconciled",
      "identical_compute_trace",
      "informed_unserved_energy_no_worse",
      "informed_peak_unserved_no_worse"
    ],
    "verdict": "FAIL",
    "informed_vs_baseline": {
      "baseline_unserved_mwh": 5.011418076,
      "informed_unserved_mwh": 0.893328423,
      "baseline_peak_unserved_mw": 44.86838787,
      "informed_peak_unserved_mw": 42.36838787
    }
  },
  "candidate": {
    "conditions": {
      "build_parity": true,
      "baseline_valid": false,
      "informed_valid": true,
      "baseline_energy_balance": true,
      "informed_energy_balance": true,
      "baseline_fuel_reconciled": true,
      "informed_fuel_reconciled": true,
      "identical_compute_trace": true,
      "informed_unserved_energy_no_worse": true,
      "informed_peak_unserved_no_worse": true
    },
    "condition_order": [
      "build_parity",
      "baseline_valid",
      "informed_valid",
      "baseline_energy_balance",
      "informed_energy_balance",
      "baseline_fuel_reconciled",
      "informed_fuel_reconciled",
      "identical_compute_trace",
      "informed_unserved_energy_no_worse",
      "informed_peak_unserved_no_worse"
    ],
    "verdict": "FAIL",
    "informed_vs_baseline": {
      "baseline_unserved_mwh": 5.011418076,
      "informed_unserved_mwh": 0.859772492,
      "baseline_peak_unserved_mw": 44.86838787,
      "informed_peak_unserved_mw": 42.36838787
    }
  }
}
```

## B6 — base demo, production record unchanged
| Arm | Curtailment MWh | Turbine fuel MMBtu | Unserved MWh | Peak unserved MW | Full physical hash |
|---|---:|---:|---:|---:|---|
| baseline | 8.136511735 | 714.363019086 | 0.351692658 | 22.309362466 | `90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1` |
| informed | 5.278943188 | 665.398247704 | 0.020719074 | 7.52325057 | `ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6` |
Both rows equal their BASE physical hashes and every collector metric, and exactly match the requested 2026-10-21 production figures.
Native comparison, before and after:
```json
{
  "base": {
    "conditions": {
      "build_parity": true,
      "baseline_valid": true,
      "informed_valid": true,
      "baseline_energy_balance": true,
      "informed_energy_balance": true,
      "baseline_fuel_reconciled": true,
      "informed_fuel_reconciled": true,
      "identical_compute_trace": true,
      "informed_unserved_energy_no_worse": true,
      "informed_peak_unserved_no_worse": true
    },
    "condition_order": [
      "build_parity",
      "baseline_valid",
      "informed_valid",
      "baseline_energy_balance",
      "informed_energy_balance",
      "baseline_fuel_reconciled",
      "informed_fuel_reconciled",
      "identical_compute_trace",
      "informed_unserved_energy_no_worse",
      "informed_peak_unserved_no_worse"
    ],
    "verdict": "PASS",
    "informed_vs_baseline": {
      "baseline_unserved_mwh": 0.351692658,
      "informed_unserved_mwh": 0.020719074,
      "baseline_peak_unserved_mw": 22.309362466,
      "informed_peak_unserved_mw": 7.52325057
    }
  },
  "candidate": {
    "conditions": {
      "build_parity": true,
      "baseline_valid": true,
      "informed_valid": true,
      "baseline_energy_balance": true,
      "informed_energy_balance": true,
      "baseline_fuel_reconciled": true,
      "informed_fuel_reconciled": true,
      "identical_compute_trace": true,
      "informed_unserved_energy_no_worse": true,
      "informed_peak_unserved_no_worse": true
    },
    "condition_order": [
      "build_parity",
      "baseline_valid",
      "informed_valid",
      "baseline_energy_balance",
      "informed_energy_balance",
      "baseline_fuel_reconciled",
      "informed_fuel_reconciled",
      "identical_compute_trace",
      "informed_unserved_energy_no_worse",
      "informed_peak_unserved_no_worse"
    ],
    "verdict": "PASS",
    "informed_vs_baseline": {
      "baseline_unserved_mwh": 0.351692658,
      "informed_unserved_mwh": 0.020719074,
      "baseline_peak_unserved_mw": 22.309362466,
      "informed_peak_unserved_mw": 7.52325057
    }
  }
}
```

## 3.4 — full suite
Command: from P, `python -m pytest -q tests --maxfail=0 --tb=short -p dr_isl_incremental --basetemp=/tmp/DR-ISL-phase3/finish/pytest-baseruns --junitxml=/tmp/DR-ISL-phase3/finish/suite_final.xml`.
The scratch plugin maintains a parseable incremental JUnit after each primary test; native final JUnit additionally represents subtests.
```json
{
  "literal_summary": "17 failed, 2149 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 669.81s (0:11:09)",
  "added": [
    "tests/test_addendum_h_phase2a_commitment.py::test_tc125_informed_core_proposal_is_logged_by_controller",
    "tests/test_addendum_h_phase2a_commitment.py::test_tc132_core_start_is_vetoed_during_minimum_down_window"
  ],
  "removed": [],
  "remaining": [
    "tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation",
    "tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config",
    "tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar",
    "tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment",
    "tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve",
    "tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names",
    "tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel",
    "tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited",
    "tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context",
    "tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants",
    "tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude",
    "tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait",
    "tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes",
    "tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load",
    "tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip"
  ],
  "failing": [
    "tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation",
    "tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config",
    "tests/test_addendum_h_phase2a_commitment.py::test_tc125_informed_core_proposal_is_logged_by_controller",
    "tests/test_addendum_h_phase2a_commitment.py::test_tc132_core_start_is_vetoed_during_minimum_down_window",
    "tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar",
    "tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment",
    "tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve",
    "tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names",
    "tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel",
    "tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited",
    "tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context",
    "tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants",
    "tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude",
    "tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait",
    "tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes",
    "tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load",
    "tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip"
  ],
  "native_junit": "/tmp/DR-ISL-phase3/finish/suite_final.xml",
  "incremental_junit": "/tmp/DR-ISL-phase3/finish/suite_incremental.xml",
  "added_failure_assertions": {
    "tests/test_addendum_h_phase2a_commitment.py::test_tc125_informed_core_proposal_is_logged_by_controller": "tests/test_addendum_h_phase2a_commitment.py:599: in test_tc125_informed_core_proposal_is_logged_by_controller\n    assert controller.adjudicate_core_proposal(\nE   AssertionError: assert False is True\nE    +  where False = adjudicate_core_proposal(state=SimulationState(run_id='tc125-core-proposal', site=SiteConfig(site_id='site-for-tc125-core-proposal', frequency_nomina..._open_s=nan, _ufls_timer_s=[], _ufls_fired=[], _cumulative_shed_mw=0.0, _relay_81u_timer_s=0.0, _relay_81u_fired=False), decision=namespace(action='commit', target_unit_id='turbine-1', reason='measured reserve shortfall', floor_violated=True), sim_time_s=0.0, synchronized_capacity_mw=10.0, bess_soc_fraction=0.5)\nE    +    where adjudicate_core_proposal = ForecastDrivenTurbineController(mode='informed', forecast_lead_seconds=600.0, background_window_seconds=900.0, hot_sta...unserved_energy_mwh=0.0, peak_unserved_mw=0.0, unserved_intervals=[], forecast_miss_count=0, forecast_miss_peak_mw=0.0).adjudicate_core_proposal\nE    +    and   SimulationState(run_id='tc125-core-proposal', site=SiteConfig(site_id='site-for-tc125-core-proposal', frequency_nomina..._open_s=nan, _ufls_timer_s=[], _ufls_fired=[], _cumulative_shed_mw=0.0, _relay_81u_timer_s=0.0, _relay_81u_fired=False) = RunContext(run_id='tc125-core-proposal', sim_state=SimulationState(run_id='tc125-core-proposal', site=SiteConfig(site_...nserved_energy_mwh=0.0, peak_unserved_mw=0.0, unserved_intervals=[], forecast_miss_count=0, forecast_miss_peak_mw=0.0)).sim_state",
    "tests/test_addendum_h_phase2a_commitment.py::test_tc132_core_start_is_vetoed_during_minimum_down_window": "tests/test_addendum_h_phase2a_commitment.py:819: in test_tc132_core_start_is_vetoed_during_minimum_down_window\n    assert \"minimum down time\" in (\nE   AssertionError: assert 'minimum down time' in (('forecast controller veto: start ineligible (min_down)'))\nE    +  where 'forecast controller veto: start ineligible (min_down)' = CommitmentLogRecord(sim_time_s=200.0, unit_id='turbine-0', action='proposal_commit', thermal_tier='controller', reason...to: start ineligible (min_down)', from_state=None, to_state=None, controller_approved=False, suppressed_repeat_count=0).refusal_reason"
  },
  "native_junit_counts": {
    "name": "pytest",
    "errors": "0",
    "failures": "17",
    "skipped": "26",
    "tests": "2195",
    "time": "669.782",
    "timestamp": "2026-10-22T08:52:54.539289+00:00",
    "hostname": "repl"
  },
  "incremental_primary_test_counts": {
    "name": "Phase3-incremental",
    "tests": "002192",
    "failures": "000017",
    "errors": "000000",
    "skipped": "000026"
  }
}
```
Two added failures were observed while the suite was already running. No application/test edit or retry followed; the existing suite was allowed to finish as explicitly requested, then the candidate was stashed and BASE restored.
TC125's fixture uses `_spec(mode="informed", spinning=1, hot=1).model_dump()` at P/tests/test_addendum_h_phase2a_commitment.py:590. Its assertion at :599–605 expects True but got False. No root-cause fix or stale-test waiver is asserted here.
TC132 at P/tests/test_addendum_h_phase2a_commitment.py:819 expects the phrase `minimum down time`; the actual refusal is `forecast controller veto: start ineligible (min_down)`. The test was left unchanged.

## 3.5 — commits, changed files and status
Implementation commit: `None`.
Restored backend verification (startup only; no new simulation or test after STOP):
```json
{
  "workflow": "artifacts/gridsignal: web",
  "log_file": "/tmp/logs/artifactsgridsignal_web_20261022_090549_283_41777aa5.log",
  "printed_startup_values": [
    {
      "line": 40,
      "text": "INFO:     Application startup complete."
    },
    {
      "line": 41,
      "text": "INFO:     Uvicorn running on http://0.0.0.0:22126 (Press CTRL+C to quit)"
    },
    {
      "line": 42,
      "text": "INFO:     127.0.0.1:39100 - \"GET / HTTP/1.1\" 200 OK"
    }
  ],
  "preview": "Operator sign-in page rendered; unauthenticated API request returned 401; no sign-in attempted"
}
```
The candidate's new test file under ignored P was explicitly force-added; on STOP it remains in the candidate stash, not active BASE code. Existing tests and scenario JSON are unchanged.
No existing test updates were made. Added failures are preserved literally for review, not waived. The report-only commit hash and post-commit clean status are supplied in the final response.
Literal status at rendering:
```
M .agents/memory/ignored-simulator-source.md
 M .agents/memory/s1-study-harness.md
 M tools/dr_isl/PHASE_3_EVIDENCE.json
 M tools/dr_isl/PHASE_3_REPORT.md
 M tools/dr_isl/PHASE_3_TC06.xml
?? tools/dr_isl/PHASE_3_FAILING_TESTS.txt
```
Changed application/test hunk ranges relative to BASE:
```
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
@@ -1054,6 +1054,18 @@ class TurbineModule(AssetModule):
@@ -1066,19 +1078,10 @@ class TurbineModule(AssetModule):
@@ -1114,7 +1117,9 @@ class TurbineModule(AssetModule):
@@ -1132,6 +1137,7 @@ class TurbineModule(AssetModule):
@@ -1142,6 +1148,8 @@ class TurbineModule(AssetModule):
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
@@ -326,9 +326,22 @@ def evaluate_commitment(
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
@@ -590,7 +590,8 @@ class DispatchArbitrator:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
@@ -745,6 +745,11 @@ class UnitAvailability:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -291,6 +291,7 @@ class SimulationState:
@@ -598,7 +599,7 @@ _STANDBY_THERMAL_PRIORITY = {
@@ -617,6 +618,51 @@ def _offline_turbines_by_thermal_priority(
@@ -627,7 +673,7 @@ def _promote_reserve_standby_labels(
@@ -714,11 +760,7 @@ def _release_hot_standby_for_contingency(
@@ -2178,12 +2220,13 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
@@ -2239,11 +2282,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
@@ -2316,6 +2355,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
@@ -2535,7 +2575,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
@@ -1519,9 +1519,11 @@ class RunContext:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
@@ -619,20 +619,25 @@ class ForecastDrivenTurbineController:
@@ -828,7 +833,7 @@ class ForecastDrivenTurbineController:
@@ -1196,19 +1201,12 @@ class ForecastDrivenTurbineController:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py
@@ -0,0 +1,140 @@
```

## Full application/test diff
```diff
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
index 1b2b974..11ec12b 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
@@ -1054,6 +1054,18 @@ class TurbineModule(AssetModule):
         self._last_setpoint_mw = float(new_output_mw)   # store before rate-clip
         self._current_output_mw = max(0.0, min(new_output_mw, self.config.rated_mw))
 
+    def start_eligibility(self, sim_time: float) -> tuple[bool, str]:
+        """DR D2 / IMPL-ISL-5: the single, unchanged turbine start interlock."""
+        if self.config.hot_standby:
+            return False, "hot_standby"
+        if self.state != TurbineState.OFFLINE:
+            return False, "state"
+        if self.config.min_down_enabled and not math.isnan(self._stop_time_s):
+            elapsed = sim_time - self._stop_time_s
+            if elapsed < self.config.t_min_down_s:
+                return False, "min_down"
+        return True, "eligible"
+
     def command_start(self, sim_time: float) -> None:
         """Transition OFFLINE → STARTING.  Phase 2 commitment-logic entry point.
 
@@ -1066,19 +1078,10 @@ class TurbineModule(AssetModule):
 
         No output is produced while STARTING (_current_output_mw stays 0.0).
         """
-        if self.config.hot_standby:
+        # DR D2 / IMPL-ISL-5: retain the safety check, using the same predicate
+        # as selection and the availability boundary (no second guard copy).
+        if not self.start_eligibility(sim_time)[0]:
             return
-        if self.state != TurbineState.OFFLINE:
-            return
-
-        # R6: enforce minimum down-time when the constraint is enabled.
-        # Phase E closeout Item 1 / D-03: gated on min_down_enabled so tests
-        # that create TurbineConfig() directly (min_down_enabled=False default)
-        # are unaffected.
-        if self.config.min_down_enabled and not math.isnan(self._stop_time_s):
-            elapsed = sim_time - self._stop_time_s
-            if elapsed < self.config.t_min_down_s:
-                return  # cooling window not yet satisfied
 
         # Determine thermal state from time offline since last synchronisation.
         # First start (never stopped): use config.initial_thermal_state so the
@@ -1114,7 +1117,9 @@ class TurbineModule(AssetModule):
                 ThermalState.COLD: self.config.fuel.start_fuel_mmbtu_cold,
             }[self._thermal_state]
 
-    def unit_availability(self) -> "UnitAvailability":
+    # PROPOSED_HERE: epoch default preserves existing no-argument boundary
+    # callers; runtime selection always passes the actual simulation time.
+    def unit_availability(self, sim_time: float = 0.0) -> "UnitAvailability":
         """Build a UnitAvailability boundary object from current state.
 
         Called by simulation_core.py each tick to build the availability list
@@ -1132,6 +1137,7 @@ class TurbineModule(AssetModule):
         else:
             time_to_online = None
 
+        eligible, reason = self.start_eligibility(sim_time)
         return UnitAvailability(
             unit_id=self.config.asset_id,
             state=self.state,
@@ -1142,6 +1148,8 @@ class TurbineModule(AssetModule):
             time_to_online_s=time_to_online,
             out_of_service_reason=self._out_of_service_reason,
             hot_standby=self.config.hot_standby,
+            start_eligible=eligible,
+            start_ineligibility_reason=None if eligible else reason,
         )
 
     def command_stop(self, sim_time: float) -> Optional[str]:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
index c6b6401..85c7a7c 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
@@ -326,9 +326,22 @@ def evaluate_commitment(
                 ),
                 floor_mw=floor_mw, floor_violated=floor_violated,
             )
+        # DR D2 / IMPL-ISL-5: consume the one asset predicate's snapshot,
+        # preserving caller priority, rather than retrying offline[0].
+        eligible = next((unit for unit in offline if unit.start_eligible), None)
+        if eligible is None:
+            return CommitmentDecision(
+                action="hold",
+                target_unit_id=None,
+                reason=f"commit condition met (U={utilisation:.3f}, floor_violated={floor_violated})",
+                blocked_by="no eligible turbine: " + "; ".join(
+                    f"{unit.unit_id}={unit.start_ineligibility_reason}" for unit in offline
+                ),
+                floor_mw=floor_mw, floor_violated=floor_violated,
+            )
         return CommitmentDecision(
             action="commit",
-            target_unit_id=offline[0].unit_id,
+            target_unit_id=eligible.unit_id,
             reason=(
                 f"floor_violated={floor_violated}, U={utilisation:.3f}"
                 f" ≥ {cfg.commit_utilisation}" if not floor_violated else
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
index 4bd7cac..9507e45 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
@@ -590,7 +590,8 @@ class DispatchArbitrator:
         if not _active_turbines and not _active_fuel_cells:
             required_ramp_s = float("inf")
         else:
-            _offline = [t for t in _active_turbines if t.state == TurbineState.OFFLINE]
+            # DR D2 / IMPL-ISL-5: staging shares command_start's interlock.
+            _offline = [t for t in _active_turbines if t.start_eligibility(sim_time)[0]]
             _on_bus  = [t for t in _active_turbines if t.state != TurbineState.OFFLINE]
 
             # ── Stage offline turbines: N_needed + 1 N-1 spare ──────────────────
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
index cf0140b..3044d09 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
@@ -745,6 +745,11 @@ class UnitAvailability:
     time_to_online_s: Optional[float]    # 0.0 = SYNCHRONISED; None = OUT_OF_SERVICE
     out_of_service_reason: Optional[str] # None unless OUT_OF_SERVICE
     hot_standby: bool = False            # True → excluded from ramp credit and dispatch
+    # DR D2 / IMPL-ISL-5: verdict evaluated by TurbineModule.start_eligibility.
+    # PROPOSED_HERE: True preserves explicitly supplied PMS/test snapshots;
+    # live turbine snapshots always supply their time-resolved verdict.
+    start_eligible: bool = True
+    start_ineligibility_reason: Optional[str] = None
 
     @property
     def is_starting(self) -> bool:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
index 60596e0..c30fc99 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -291,6 +291,7 @@ class SimulationState:
     _commit_cfg:    CommitmentConfig    = field(init=False)
     _pending_start: PendingStartRegister = field(init=False)
     _commit_cond:   SustainedCondition  = field(init=False)
+    _start_ineligible_episode_logged: bool = field(default=False, init=False)
     _decommit_cond: SustainedCondition  = field(init=False)
     # Contingency-triggered standby release is deliberately separate from
     # evaluate_commitment().  The condition is armed again only after one
@@ -598,7 +599,7 @@ _STANDBY_THERMAL_PRIORITY = {
 }
 
 
-def _offline_turbines_by_thermal_priority(
+def _offline_turbine_roster(
     turbines: list[TurbineModule],
 ) -> list[TurbineModule]:
     """Return offline turbines in hot → warm → cold, then roster order."""
@@ -617,6 +618,51 @@ def _offline_turbines_by_thermal_priority(
     )
 
 
+def _offline_turbines_by_thermal_priority(
+    turbines: list[TurbineModule], sim_time: float, *, include_blocked: bool = False,
+) -> list[TurbineModule]:
+    """DR D2 / IMPL-ISL-5: one start predicate, unchanged thermal/roster order.
+
+    The commitment boundary includes blocked non-reserved units so it can
+    report why an episode has no candidate. Reserve labels use the raw roster.
+    """
+    candidates = []
+    for turbine in _offline_turbine_roster(turbines):
+        eligible, reason = turbine.start_eligibility(sim_time)
+        if eligible or (include_blocked and reason != "hot_standby"):
+            candidates.append(turbine)
+    return candidates
+
+
+def _releasable_hot_standby_turbines(
+    turbines: list[TurbineModule], sim_time: float,
+) -> list[TurbineModule]:
+    """Evaluate unchanged interlocks under the existing explicit release authority."""
+    candidates = []
+    for turbine in _offline_turbine_roster(turbines):
+        if turbine.config.hot_standby:
+            turbine.config.hot_standby = False
+            try:
+                eligible, _ = turbine.start_eligibility(sim_time)
+            finally:
+                turbine.config.hot_standby = True
+            if eligible:
+                candidates.append(turbine)
+    return candidates
+
+
+def _log_start_ineligibility_episode(
+    state: SimulationState, decision: CommitmentDecision, sim_time: float,
+) -> None:
+    """DR D2: one commitment-log reason per contiguous blocked episode."""
+    blocked = isinstance(decision.blocked_by, str) and decision.blocked_by.startswith(
+        "no eligible turbine:"
+    )
+    if blocked and not state._start_ineligible_episode_logged:
+        _log.info("Commitment engine: %s at sim_time=%.1f", decision.blocked_by, sim_time)
+    state._start_ineligible_episode_logged = blocked
+
+
 def _promote_reserve_standby_labels(
     turbines: list[TurbineModule],
 ) -> tuple[str, ...]:
@@ -627,7 +673,7 @@ def _promote_reserve_standby_labels(
     """
     remaining = [
         turbine
-        for turbine in _offline_turbines_by_thermal_priority(turbines)
+        for turbine in _offline_turbine_roster(turbines)
         if turbine.config.hot_standby
     ]
     desired = [ThermalState.HOT, ThermalState.WARM]
@@ -714,11 +760,7 @@ def _release_hot_standby_for_contingency(
     ):
         return None
 
-    hot_standby_units = [
-        turbine
-        for turbine in _offline_turbines_by_thermal_priority(state.turbines)
-        if turbine.config.hot_standby
-    ]
+    hot_standby_units = _releasable_hot_standby_turbines(state.turbines, sim_time)
     if not hot_standby_units:
         return None
 
@@ -2178,12 +2220,13 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     # reserve; using them here would make the commitment decision disagree with
     # the operator-facing reserve summary during the controlled rundown.
     _avail_on_bus = [
-        t.unit_availability() for t in state.turbines if t.contributes_to_reserve
+        t.unit_availability(sim_time) for t in state.turbines if t.contributes_to_reserve
     ]
     _avail_offline = [
-        t.unit_availability()
-        for t in _offline_turbines_by_thermal_priority(state.turbines)
-        if not t.config.hot_standby
+        t.unit_availability(sim_time)
+        for t in _offline_turbines_by_thermal_priority(
+            state.turbines, sim_time, include_blocked=True,
+        )
     ]
 
     # ── Cascade commit trigger (site.cascade_commit_fraction) ─────────────
@@ -2239,11 +2282,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
                 # command_start().  Fix: clear the flag, THEN call command_start()
                 # (the guard is gone so it transitions OFFLINE → STARTING normally,
                 # using initial_thermal_state="hot" → hot_start_s duration).
-                _hs_units = [
-                    t
-                    for t in _offline_turbines_by_thermal_priority(state.turbines)
-                    if t.config.hot_standby
-                ]
+                _hs_units = _releasable_hot_standby_turbines(state.turbines, sim_time)
                 if _hs_units and state._pending_start.is_empty:
                     _next_hs = _hs_units[0]
                     _before_state = _next_hs.state
@@ -2316,6 +2355,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         decommit_enabled     = _bess_rundown_enabled and not _generation_baseload_active,
         decommit_reason_context = _bess_rundown_reason,
     )
+    _log_start_ineligibility_episode(state, _commit_decision, sim_time)
     if (
         _commit_decision.action == "commit"
         and _commit_decision.target_unit_id is not None
@@ -2535,7 +2575,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     # UNLOADING units are pinned at MSL with no upward headroom — counting their
     # nameplate overstates reserve precisely when the fleet is shrinking.
     # Distinct from on_bus_output_mw which INCLUDES UNLOADING (they do produce).
-    _avail_reserve        = [t.unit_availability() for t in state.turbines if t.contributes_to_reserve]
+    _avail_reserve        = [t.unit_availability(sim_time) for t in state.turbines if t.contributes_to_reserve]
     _committed_rated_mw_cs = sum(u.rated_mw for u in _avail_reserve)
     _fleet_utilisation_cs = (
         _commitment_demand_mw / _committed_rated_mw_cs
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
index 6eec6e0..4f3fadb 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
@@ -1519,9 +1519,11 @@ class RunContext:
                         unit_id, self.sim_time, self.run_id,
                     )
                 elif action == "start":
-                    was_offline = turbine.state == _TurbineState.OFFLINE
+                    # DR D2 / IMPL-ISL-5: explicit operator commands retain
+                    # their target; eligibility is not independently reimplemented.
+                    eligible, _ = turbine.start_eligibility(self.sim_time)
                     turbine.command_start(self.sim_time)
-                    accepted = was_offline and turbine.state == _TurbineState.STARTING
+                    accepted = eligible and turbine.state == _TurbineState.STARTING
                     if not accepted:
                         refusal_reason = (
                             "start refused: unit is not offline or minimum down time "
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
index ca8445f..a7af66b 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
@@ -619,20 +619,25 @@ class ForecastDrivenTurbineController:
         )
         return allowance, soc
 
-    def _candidate_start(self, turbines: list[Any]) -> Optional[Any]:
-        standby = [
-            turbine for turbine in turbines
-            if turbine.state == TurbineState.OFFLINE
-            and getattr(turbine.config, "hot_standby", False)
-        ]
-        if standby:
-            return standby[0]
-        offline = [
-            turbine for turbine in turbines
-            if turbine.state == TurbineState.OFFLINE
-            and not getattr(turbine.config, "hot_standby", False)
-        ]
-        return offline[0] if offline else None
+    def _candidate_start(self, turbines: list[Any], sim_time_s: float) -> Optional[Any]:
+        # DR D2 / IMPL-ISL-5: preserve standby-first/roster priority, but use
+        # the same interlock as the core and command path. A reserved candidate
+        # is evaluated under this controller's existing explicit release authority.
+        ordered = (
+            [t for t in turbines if getattr(t.config, "hot_standby", False)]
+            + [t for t in turbines if not getattr(t.config, "hot_standby", False)]
+        )
+        for turbine in ordered:
+            reserved = bool(turbine.config.hot_standby)
+            if reserved:
+                turbine.config.hot_standby = False
+            try:
+                eligible, _ = turbine.start_eligibility(sim_time_s)
+            finally:
+                turbine.config.hot_standby = reserved
+            if eligible:
+                return turbine
+        return None
 
     def _candidate_stop(self, turbines: list[Any]) -> Optional[Any]:
         synchronized = [
@@ -828,7 +833,7 @@ class ForecastDrivenTurbineController:
         start_horizon = self.hot_start_lookahead_seconds + self.ramp_to_load_seconds
         start_peak = forecast.peak_over(start_horizon)
         if start_peak > synchronized_capacity + bess_allowance:
-            candidate = self._candidate_start(turbines)
+            candidate = self._candidate_start(turbines, float(ctx.sim_time))
             if candidate is not None:
                 self._queue(
                     ctx,
@@ -1196,19 +1201,12 @@ class ForecastDrivenTurbineController:
         accepted = True
         refusal_reason: Optional[str] = None
         if decision.action == "commit":
-            if turbine.state != TurbineState.OFFLINE:
-                accepted = False
-                refusal_reason = (
-                    "forecast controller veto: unit is not offline and cannot start"
-                )
-            elif (
-                turbine.config.min_down_enabled
-                and not math.isnan(float(getattr(turbine, "_stop_time_s", float("nan"))))
-                and sim_time_s - turbine._stop_time_s < turbine.config.t_min_down_s
-            ):
+            # DR D2: one eligibility function owns every turbine start guard.
+            eligible, eligibility_reason = turbine.start_eligibility(sim_time_s)
+            if not eligible:
                 accepted = False
                 refusal_reason = (
-                    "forecast controller veto: minimum down time has not elapsed"
+                    f"forecast controller veto: start ineligible ({eligibility_reason})"
                 )
             horizon = self.hot_start_lookahead_seconds + self.ramp_to_load_seconds
             if accepted and forecast is not None and not decision.floor_violated:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py
new file mode 100644
index 0000000..bb7af6a
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py
@@ -0,0 +1,140 @@
+"""DR D2 / IMPL-ISL-5, TC-ISL-06: one unchanged turbine start interlock."""
+import ast
+from dataclasses import replace
+import inspect
+import logging
+import textwrap
+from types import SimpleNamespace
+
+from core.asset_modules import TurbineModule
+from core.commitment import (
+    CommitmentConfig, PendingStartRegister, SustainedCondition, evaluate_commitment,
+)
+from core.dispatch import DispatchArbitrator
+from core.models import TurbineConfig, TurbineState
+from core.simulation_core import (
+    _log_start_ineligibility_episode, _offline_turbines_by_thermal_priority,
+    _releasable_hot_standby_turbines,
+)
+from runtime.run_manager import RunContext
+import runtime.turbine_commitment as turbine_commitment_runtime
+from runtime.turbine_commitment import ForecastDrivenTurbineController
+
+
+def _calls(fn):
+    return {
+        node.func.attr for node in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(fn))))
+        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
+    }
+
+
+def _unit(name, stopped=False):
+    # PROPOSED_HERE: synthetic fixture timestamps straddle the existing 900 s
+    # minimum-down interlock; these are not new operational settings.
+    unit = TurbineModule(TurbineConfig(
+        asset_id=name, min_down_enabled=True, t_min_down_s=900.0,
+    ))
+    if stopped:
+        unit._stop_time_s = 0.0
+    return unit
+
+
+def _decision(units, time):
+    roster = _offline_turbines_by_thermal_priority(units, time, include_blocked=True)
+    return evaluate_commitment(
+        on_bus=[], offline=[u.unit_availability(time) for u in roster],
+        p_demand_mw=20.0, pending=PendingStartRegister(),
+        commit_cond=SustainedCondition(), decommit_cond=SustainedCondition(),
+        cfg=replace(CommitmentConfig.from_catalogue(), inter_start_settle_s=0.0),
+        dt_s=5.0, sim_time=time,
+    )
+
+
+def test_tc_isl_06a_single_guard_call_graph():
+    for fn in (TurbineModule.command_start, TurbineModule.unit_availability,
+               _offline_turbines_by_thermal_priority, _releasable_hot_standby_turbines):
+        assert "start_eligibility" in _calls(fn)
+    # Inspect the entire arbitrator: staging must call the same predicate.
+    assert "start_eligibility" in _calls(DispatchArbitrator)
+    assert "start_eligibility" in _calls(ForecastDrivenTurbineController._candidate_start)
+    assert "start_eligibility" in _calls(ForecastDrivenTurbineController.adjudicate_core_proposal)
+    # DR D2: include the runtime module in the single-predicate call graph.
+    assert "start_eligibility" in _calls(turbine_commitment_runtime)
+    adjudicator = ast.parse(textwrap.dedent(inspect.getsource(
+        ForecastDrivenTurbineController.adjudicate_core_proposal,
+    )))
+    assert not {
+        node.attr for node in ast.walk(adjudicator)
+        if isinstance(node, ast.Attribute)
+    } & {"min_down_enabled", "_stop_time_s", "t_min_down_s"}
+    assert "eligibility_reason" in inspect.getsource(
+        ForecastDrivenTurbineController.adjudicate_core_proposal,
+    )
+    assert "start_eligibility" in _calls(RunContext.drain_operator_commands)
+    source = inspect.getsource(TurbineModule.command_start)
+    assert "self.config.hot_standby" not in source
+    assert "elapsed < self.config.t_min_down_s" not in source
+    assert "self.state != TurbineState.OFFLINE" not in source
+    assert "unit.start_eligible" in inspect.getsource(evaluate_commitment)
+    assert "target_unit_id=offline[0]" not in inspect.getsource(evaluate_commitment)
+
+
+def test_tc_isl_06b_skip_min_down_start_alternate():
+    cooling, alternate = _unit("cooling", True), _unit("alternate")
+    assert cooling.start_eligibility(100.0) == (False, "min_down")
+    assert alternate.start_eligibility(100.0) == (True, "eligible")
+    decision = _decision([cooling, alternate], 100.0)
+    assert decision.action == "commit"
+    assert decision.target_unit_id == "alternate"
+    alternate.command_start(100.0)
+    assert alternate.state == TurbineState.STARTING
+    assert cooling.state == TurbineState.OFFLINE
+    # The certified study's forecast selector must skip the same interlock.
+    alternate.state = TurbineState.OFFLINE
+    assert ForecastDrivenTurbineController._candidate_start(
+        None, [cooling, alternate], 100.0,
+    ) is alternate
+
+
+def test_tc_isl_06c_no_eligible_one_log_per_episode(caplog):
+    units = [_unit("one", True), _unit("two", True)]
+    state = SimpleNamespace(_start_ineligible_episode_logged=False)
+    with caplog.at_level(logging.INFO, logger="core.simulation_core"):
+        for time in (100.0, 105.0, 110.0):
+            decision = _decision(units, time)
+            assert decision.action == "hold"
+            assert decision.target_unit_id is None
+            assert "one=min_down" in decision.blocked_by
+            assert "two=min_down" in decision.blocked_by
+            _log_start_ineligibility_episode(state, decision, time)
+        logs = [r for r in caplog.records if "no eligible turbine:" in r.message]
+        assert len(logs) == 1
+        assert all(u.state == TurbineState.OFFLINE and u._start_count == 0 for u in units)
+        # Clearing the blocked condition rearms the logger, not the guard.
+        _log_start_ineligibility_episode(state, _decision(units, 900.0), 900.0)
+        _log_start_ineligibility_episode(state, _decision(units, 100.0), 100.0)
+        assert sum("no eligible turbine:" in r.message for r in caplog.records) == 2
+        assert not any("silently dropped" in r.message for r in caplog.records)
+
+
+def test_tc_isl_06d_ordinary_hold_is_not_an_ineligibility_episode(caplog):
+    state = SimpleNamespace(_start_ineligible_episode_logged=True)
+    with caplog.at_level(logging.INFO, logger="core.simulation_core"):
+        for reason in (None, "", "minimum run time", 123):
+            decision = SimpleNamespace(blocked_by=reason)
+            _log_start_ineligibility_episode(state, decision, 100.0)
+            assert state._start_ineligible_episode_logged is False
+    assert not caplog.records
+
+
+def test_tc_isl_06_guard_boundaries_unchanged():
+    unit = _unit("boundary", True)
+    assert unit.start_eligibility(899.0) == (False, "min_down")
+    assert unit.start_eligibility(900.0) == (True, "eligible")
+    unit.config.min_down_enabled = False
+    assert unit.start_eligibility(0.0) == (True, "eligible")
+    unit.config.hot_standby = True
+    unit.state = TurbineState.STARTING
+    assert unit.start_eligibility(0.0) == (False, "hot_standby")
+    unit.config.hot_standby = False
+    assert unit.start_eligibility(0.0) == (False, "state")

```

## Evidence and storage
Persisted evidence: tools/dr_isl/PHASE_3_EVIDENCE.json (finished_phase3_2026_10_22), tools/dr_isl/PHASE_3_TC06.xml; failing IDs: tools/dr_isl/PHASE_3_FAILING_TESTS.txt.
The full report is /tmp/DR-ISL-phase3/PHASE_3_REPORT.md and tools/dr_isl/PHASE_3_REPORT.md.
No full per-tick exports were written. Ticks were compared/hashed as streaming JSON pipes; only summaries, requested decision exceptions, start events and metrics were retained.
Each scratch writer has a 200,000,000-byte file limit. Native compact tick lists exist only in memory.
Canonical physical hashes still include the decision fields; only the explicitly labeled B1 prefix comparison excludes the four approved fields.

## Scratch observer sources (reproducibility; no production monkeypatch persists)
### /tmp/DR-ISL-phase3/finish_worker.py
```python
"""Phase 3 acceptance observer: stdout tick pipe, bounded summaries, no tick files."""
import argparse, asyncio, copy, hashlib, importlib.util, inspect, json, logging
import math, os, random, resource, sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

resource.setrlimit(resource.RLIMIT_FSIZE, (200_000_000, 200_000_000))
R = Path("/home/runner/workspace")
P = Path("attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim")
T = Path("/tmp/DR-ISL-phase3/finish")
ap = argparse.ArgumentParser()
ap.add_argument("version", choices=["base", "candidate"])
ap.add_argument("scenario")
ap.add_argument("arm")
ap.add_argument("repetition", type=int)
a = ap.parse_args()
pkg = R/P if a.version == "candidate" else T.parent/"base"/P
sys.path.insert(0, str(pkg)); sys.dont_write_bytecode = True; os.chdir(pkg)
import numpy as np
from api.schemas import ScenarioSpec
from core.asset_modules import TurbineModule
from core.models import TurbineState
import core.simulation_core as core
from runtime.fabric_engine import FabricEngine
from runtime.run_manager import RunContext, RunManager, WebSocketHub, InMemoryTimeseriesSink
from runtime.turbine_commitment import ForecastDrivenTurbineController as Controller
from study_harness import executor
loader = importlib.util.spec_from_file_location("pin", R/"tools/dr_isl/baseline_runner.py")
pin = importlib.util.module_from_spec(loader); loader.loader.exec_module(pin)
plain, enc = pin.plain, pin.encoded
orig_build = executor.build_run_context_from_spec
orig_fabric, orig_step = FabricEngine.__init__, RunContext.step
orig_start, orig_core = TurbineModule.command_start, core.evaluate_commitment
orig_adjudicate = Controller.adjudicate_core_proposal
active = None
trace = None
proof = None
veto_checks = 0
engine = "1345380" if a.version == "base" else os.environ["DR_CANDIDATE_LABEL"]

def guard(t, time):
    # Diagnostic evaluation of BASE guards; never substitutes for engine guards.
    if t.config.hot_standby: return False, "hot_standby"
    if t.state != TurbineState.OFFLINE: return False, "state"
    if t.config.min_down_enabled and not math.isnan(t._stop_time_s):
        if time-t._stop_time_s < t.config.t_min_down_s: return False, "min_down"
    return True, "eligible"

def target_proof(t, time):
    eligible, reason = guard(t, time)
    return dict(unit=t.config.asset_id, state=t.state.value,
                eligible=eligible, reason=reason, time=time,
                min_down_enabled=t.config.min_down_enabled,
                stop_time=t._stop_time_s, min_down=t.config.t_min_down_s,
                elapsed=time-t._stop_time_s, hot_standby=t.config.hot_standby)

def build(run_id, spec, **kw):
    global active
    spec=copy.deepcopy(spec); pin.pin_spec(spec)
    active=orig_build(run_id, spec, **kw)
    for i,u in enumerate(active.sim_state.diesel_units): u._rng.seed(1729+i)
    return active

def fabric(self,*pos,**kw):
    kw["seed"]=1729
    return orig_fabric(self,*pos,**kw)

def start(self,time):
    before=self.state
    item=target_proof(self,time) if trace is not None else None
    result=orig_start(self,time)
    if trace is not None:
        trace["attempts"].append(dict(tick=active.sim_state.tick_index+1,
            sim_time=time, unit=self.config.asset_id, before=before.value,
            after=self.state.value, reason=item["reason"],
            source=inspect.currentframe().f_back.f_code.co_name))
    return result

def decision(*pos,**kw):
    global proof
    result=orig_core(*pos,**kw)
    if trace is not None and result.action=="commit":
        t=next(t for t in active.sim_state.turbines if t.config.asset_id==result.target_unit_id)
        proof=target_proof(t,kw["sim_time"])
        proof["adjudicated"]=False
    return result

def adjudicate(self,*pos,**kw):
    global veto_checks, proof
    t=next(t for t in kw["state"].turbines if t.config.asset_id==kw["decision"].target_unit_id)
    observed=target_proof(t,kw["sim_time_s"])
    if a.version=="candidate" and kw["decision"].action=="commit":
        # Old candidate's shared-predicate check + redundant min-down elif
        # vetoes exactly the same set as the now single shared predicate.
        shared, reason=t.start_eligibility(kw["sim_time_s"])
        redundant=(t.config.min_down_enabled and not math.isnan(t._stop_time_s)
                   and kw["sim_time_s"]-t._stop_time_s < t.config.t_min_down_s)
        assert (not shared or redundant) == (not shared), observed
        veto_checks += 1
    result=orig_adjudicate(self,*pos,**kw)
    if trace is not None and kw["decision"].action=="commit":
        proof=dict(observed, adjudicated=True, accepted=result)
    return result

class Log(logging.Handler):
    def emit(self,record):
        if trace is not None and "no eligible turbine:" in record.getMessage():
            trace["episodes"].append(record.getMessage())

def reset():
    return dict(ticks=0, digest=hashlib.sha256(), attempts=[], episodes=[],
                collapse=None, min_soc=1.0, frequency=[float("inf"),-float("inf")],
                unserved=0.0, balance_failures=[])

def send_tick(tick):
    row=plain(tick); physical={k:v for k,v in row.items() if k not in pin.EXCLUDED}
    trace["digest"].update(enc(physical))
    print(json.dumps(dict(kind="tick", tick=tick.tick_index, physical=physical,
                          proof=proof),separators=(",",":"),allow_nan=True),flush=True)

def step(self,*pos,**kw):
    global proof
    proof=None
    tick=orig_step(self,*pos,**kw)
    if trace is not None:
        trace["ticks"]+=1
        trace["min_soc"]=min(trace["min_soc"],tick.bess_soc_fraction)
        trace["frequency"]=[min(trace["frequency"][0],tick.frequency_hz),
                            max(trace["frequency"][1],tick.frequency_hz)]
        trace["unserved"]+=tick.p_unserved_mw*5/3600
        if tick.island_collapsed and trace["collapse"] is None:
            trace["collapse"]=dict(tick=tick.tick_index,reason=tick.collapse_reason)
        if not tick.physical_balance.passed: trace["balance_failures"].append(tick.tick_index)
        if a.arm!="app": send_tick(tick)
    return tick

class Sink(InMemoryTimeseriesSink):
    async def append(self,tick): send_tick(tick)
class Writer:
    def write(self,*,identity,record,summary,tick_rows):
        h=hashlib.sha256()
        for row in tick_rows: h.update(enc(row))
        record["diagnostic_compact_sha256"]=h.hexdigest()
        return SimpleNamespace(as_dict=lambda:{})
class Cache:
    def put(self,identity,record): return record

async def run():
    global trace
    random.seed(1729); np.random.seed(1729)
    if a.arm=="app":
        spec=ScenarioSpec.model_validate_json(
            (pkg/"config/scenarios"/(a.scenario+".json")).read_bytes()).model_dump(mode="json")
        ctx=build(a.scenario,spec,playback_speed=0.0);ctx.sink=Sink()
        trace=reset();manager=RunManager(WebSocketHub())
        await manager.start_run(ctx);await manager._tasks[ctx.run_id]
        record={}
    else:
        ex=executor.StudyRunExecutor(output_dir=T/"unused",engine_commit=engine,
                                    harness_commit="1345380")
        ex.writer,ex.cache=Writer(),Cache()
        spec=ex._expanded_spec(a.scenario,None,None);pin.pin_spec(spec)
        replay,demand=ex._probe(spec,run_id=f"{a.scenario}-study-s1-probe")
        trace=reset()
        record=ex._run_mode(scenario_id=a.scenario,mode=a.arm,spec=spec,
            replay_events=replay,demand_replay=demand,
            seed=None if a.scenario.startswith("scenario-h") else 42,
            allow_guard_failure=True,reuse_cache=False)
    trace["physical_sha256"]=trace.pop("digest").hexdigest()
    print(json.dumps(dict(kind="summary",trace=trace,record=plain(record),
                          veto_equivalence_checks=veto_checks,
                          version=a.version,scenario=a.scenario,arm=a.arm,
                          repetition=a.repetition),allow_nan=True),flush=True)

logging.basicConfig(level=logging.ERROR)
logging.getLogger("core.simulation_core").addHandler(Log())
logging.getLogger("core.simulation_core").setLevel(logging.INFO)
with patch("time.time",return_value=1792454400.0), \
     patch.object(FabricEngine,"__init__",fabric), \
     patch.object(TurbineModule,"command_start",start), \
     patch.object(RunContext,"step",step), \
     patch.object(core,"evaluate_commitment",decision), \
     patch.object(Controller,"adjudicate_core_proposal",adjudicate), \
     patch.object(executor,"build_run_context_from_spec",build):
    asyncio.run(run())

```
### /tmp/DR-ISL-phase3/finish_compare.py
```python
"""Revised B1 comparison: strict physical fields; enumerated vetoed decision deltas."""
import argparse, hashlib, json, os, resource, subprocess, sys
from pathlib import Path
resource.setrlimit(resource.RLIMIT_FSIZE,(200_000_000,200_000_000))
T=Path("/tmp/DR-ISL-phase3/finish");T.mkdir(exist_ok=True)
p=argparse.ArgumentParser();p.add_argument("scenario");p.add_argument("arm")
p.add_argument("repetition",type=int);a=p.parse_args()
label=f"{a.scenario}-{a.arm}-{a.repetition}"
env=dict(os.environ,PYTHONHASHSEED="1729",PYTHONDONTWRITEBYTECODE="1")
logs=[(T/f"{label}-{v}.log").open("w") for v in ("base","candidate")]
jobs=[subprocess.Popen([sys.executable,str(T.parent/"finish_worker.py"),v,a.scenario,a.arm,
                        str(a.repetition)],stdout=subprocess.PIPE,stderr=logs[i],
                        text=True,env=env) for i,v in enumerate(("base","candidate"))]
allowed={"commitment_action","commitment_target_unit_id","commitment_blocked_by","commitment_reason"}
cut=1059 if a.scenario.startswith("S10") else 10071 if (a.scenario=="scenario-h2-slurm-24h" and a.arm=="informed") else float("inf")
out=dict(scenario=a.scenario,arm=a.arm,repetition=a.repetition,ticks=0,
         cutoff=None if cut==float("inf") else cut,telemetry_exceptions=[],failure=None)
hashes=[hashlib.sha256(),hashlib.sha256()]
def encoded(x):return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=True).encode()+b"\n"
try:
    while True:
        raw=[j.stdout.readline() for j in jobs]
        if any(not r for r in raw):raise RuntimeError("worker exited; see stderr")
        rows=[json.loads(r) for r in raw]
        if any(r["kind"]=="summary" for r in rows):
            if not all(r["kind"]=="summary" for r in rows):raise RuntimeError("stream lengths differ")
            out["summaries"]=dict(zip(("base","candidate"),rows));break
        b,c=rows;out["ticks"]+=1
        if b["tick"]!=c["tick"]:raise RuntimeError("tick indices differ")
        if b["tick"]<cut:
            bp,cp=b["physical"],c["physical"]
            for i,r in enumerate(rows):
                hashes[i].update(encoded({k:v for k,v in r["physical"].items() if k not in allowed}))
            dif={k:dict(base=bp.get(k),candidate=cp.get(k)) for k in set(bp)|set(cp)
                 if encoded(bp.get(k))!=encoded(cp.get(k))}
            if dif:
                proof=b["proof"]
                valid=(set(dif)<=allowed and bp.get("commitment_action")=="commit"
                       and proof and not proof["eligible"] and proof["adjudicated"]
                       and not proof["accepted"])
                if not valid:
                    out["failure"]=dict(tick=b["tick"],diffs=dif,proof=proof,base=bp,candidate=cp)
                    raise AssertionError("B1 STOP "+str(out["failure"]["tick"]))
                out["telemetry_exceptions"].append(dict(tick=b["tick"],diffs=dif,base_veto=proof))
    out["physics_prefix_hashes"]=[h.hexdigest() for h in hashes]
    out["returncodes"]=[j.wait() for j in jobs]
    assert out["returncodes"]==[0,0]
    out["B1_passed"]=True
except BaseException as exc:
    out["B1_passed"]=False;out["error"]=repr(exc)
    raise
finally:
    (T/f"{label}.json").write_text(json.dumps(out,indent=2,allow_nan=True))
    for j in jobs:
        if j.poll() is None:j.terminate()
    for f in logs:f.close()
print("PASS",label,"ticks",out["ticks"],"telemetry_exceptions",len(out["telemetry_exceptions"]),flush=True)

```
### /tmp/DR-ISL-phase3/finish_acceptance.py
```python
"""Evaluate completed acceptance evidence only; never starts a simulation."""
import json, sys
from pathlib import Path
R=Path("/home/runner/workspace")
T=Path("/tmp/DR-ISL-phase3/finish")
P=R/"attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim"
sys.path.insert(0,str(P))
from study_harness.acceptance import compare_metrics
old=json.loads((R/"tools/dr_isl/PHASE_3_EVIDENCE.json").read_text())
metric_keys=list(next(iter(old["completed_H_records"].values()))["metrics"])
data={}
out=dict(checks=[],failure=None)
def check(name,passed,values):
 out["checks"].append(dict(check=name,passed=bool(passed),values=values))
 if not passed:
  out["failure"]=out["checks"][-1]
  raise AssertionError(name)
def get(s,a,r=1):
 key=(s,a,r)
 if key not in data:data[key]=json.loads((T/f"{s}-{a}-{r}.json").read_text())
 return data[key]
def metric(x,v):
 rec=x["summaries"][v]["record"]
 return {k:rec.get(k) for k in metric_keys}
def hashof(x,v):return x["summaries"][v]["trace"]["physical_sha256"]
def trace(x,v):return x["summaries"][v]["trace"]
def rec(x,v):return x["summaries"][v]["record"]
def same(x):return hashof(x,"base")==hashof(x,"candidate")
def starts(x,v):
 return [a for a in trace(x,v)["attempts"] if a["after"]=="starting"]
cases=[
 ("S10_mit_supercloud_2021-08-11","app",1),
 ("scenario-h2-slurm-24h","informed",1),
 *[(s,"app",1) for s in ["demo-islanded-ramp","scenario-equinix-sj-1","scenario-turbine-01",
  "scenario-hybrid-ai-100mw-addendum-i","scenario-100mw-fuel-cell-bess-diesel",
  "scenario-fc100-islanded-v2","scenario-fc100-islanded-zero-hot-v2"]],
 *[("scenario-h1-k8s-ray-24h",a,r) for a in ["baseline","informed"] for r in [1,2]],
 ("scenario-h2-slurm-24h","baseline",1),
 ("scenario-h2-slurm-24h","informed",2),
 ("scenario-uneven-multisched-01","baseline",1),
 ("scenario-uneven-multisched-01","informed",1),
]
try:
 for s,a,r in cases:
  x=get(s,a,r)
  check(f"B1 {s}/{a}/{r}",x["B1_passed"] and x["physics_prefix_hashes"][0]==x["physics_prefix_hashes"][1],
        dict(ticks=x["ticks"],cutoff=x["cutoff"],exceptions=x["telemetry_exceptions"],
             physics_prefix_hashes=x["physics_prefix_hashes"]))
 x=get("S10_mit_supercloud_2021-08-11","app")
 rejected={v:[a for a in trace(x,v)["attempts"] if a["reason"]!="eligible"] for v in ["base","candidate"]}
 check("B2 S10 rejected starts",len(rejected["base"])==1154 and len(rejected["candidate"])==0,
       dict(counts={k:len(v) for k,v in rejected.items()},first_base_rejection=rejected["base"][0],
            starts={v:starts(x,v) for v in ["base","candidate"]}))
 for s,a,r in cases[2:9]:
  x=get(s,a,r);check(f"B3/B4 {s}",same(x),
                     {v:hashof(x,v) for v in ["base","candidate"]})
 for arm in ["baseline","informed"]:
  runs=[get("scenario-h1-k8s-ray-24h",arm,r) for r in [1,2]]
  for i,x in enumerate(runs,1):
   diff={k:dict(base=metric(x,"base")[k],candidate=metric(x,"candidate")[k])
         for k in metric_keys if metric(x,"base")[k]!=metric(x,"candidate")[k]}
   compact_equal=rec(x,"base")["diagnostic_compact_sha256"]==rec(x,"candidate")["diagnostic_compact_sha256"]
   check(f"B5 H1 {arm}/{i}",same(x) and not diff and compact_equal,
         dict(metric_differences=diff,physical={v:hashof(x,v) for v in ["base","candidate"]},
              compact={v:rec(x,v)["diagnostic_compact_sha256"] for v in ["base","candidate"]}))
  check(f"B5 H1 {arm} repetitions",all(hashof(runs[0],v)==hashof(runs[1],v) and metric(runs[0],v)==metric(runs[1],v) for v in ["base","candidate"]),
        dict(repetitions=2))
 hb=get("scenario-h2-slurm-24h","baseline")
 check("B5 H2 baseline",same(hb) and metric(hb,"base")==metric(hb,"candidate"),
       dict(physical={v:hashof(hb,v) for v in ["base","candidate"]},
            start_fuel_reconciliation=rec(hb,"candidate").get("start_fuel_reconciliation"),
            status=rec(hb,"candidate").get("status")))
 h2=[get("scenario-h2-slurm-24h","informed",r) for r in [1,2]]
 check("B5 H2 informed repetitions",
       all(hashof(h2[0],v)==hashof(h2[1],v) and metric(h2[0],v)==metric(h2[1],v) for v in ["base","candidate"]),
       dict(repetitions=2,metrics={v:metric(h2[0],v) for v in ["base","candidate"]}))
 check("B5 H2 informed rejections",
       all(not [a for a in trace(x,"candidate")["attempts"] if a["reason"]!="eligible"] for x in h2),
       dict(rejections=[sum(a["reason"]!="eligible" for a in trace(x,"candidate")["attempts"]) for x in h2]))
 out["H2_compare_runs"]={v:compare_metrics(rec(hb,v),rec(h2[0],v)) for v in ["base","candidate"]}
 expected={
  "baseline":dict(dispatch_curtailment_mwh=8.136511735,turbine_fuel_mmbtu=714.363019086,
                  unserved_mwh=0.351692658,peak_unserved_mw=22.309362466),
  "informed":dict(dispatch_curtailment_mwh=5.278943188,turbine_fuel_mmbtu=665.398247704,
                  unserved_mwh=0.020719074,peak_unserved_mw=7.52325057),
 }
 for arm,reference in expected.items():
  x=get("scenario-uneven-multisched-01",arm)
  actual={k:rec(x,"candidate").get(k) for k in reference}
  check(f"B6 base demo {arm}",actual==reference and same(x) and metric(x,"base")==metric(x,"candidate"),
        dict(expected=reference,actual=actual,physical={v:hashof(x,v) for v in ["base","candidate"]}))
 out["B6_compare_runs"]={
  v:compare_metrics(rec(get("scenario-uneven-multisched-01","baseline"),v),
                    rec(get("scenario-uneven-multisched-01","informed"),v))
  for v in ["base","candidate"]}
 out["passed"]=True
finally:
 (T/"acceptance.json").write_text(json.dumps(out,indent=2,allow_nan=True))
 print(json.dumps(dict(passed=out.get("passed",False),failure=out["failure"],
                       checks=len(out["checks"]))))

```
### /tmp/DR-ISL-phase3/finish/dr_isl_incremental.py
```python
"""Scratch-only pytest observer: parseable, incrementally updated JUnit evidence."""
import os
import resource
from pathlib import Path
import xml.etree.ElementTree as ET

resource.setrlimit(resource.RLIMIT_FSIZE, (200_000_000, 200_000_000))
ROOT = Path("/tmp/DR-ISL-phase3/finish")
TAIL = b"</testsuite></testsuites>\n"
states = {}
failed = set()
counts = dict(tests=0, failures=0, errors=0, skipped=0)
stream = None
offset = 0

def header():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<testsuites><testsuite name="Phase3-incremental" '
        + " ".join(f'{k}="{v:06d}"' for k,v in counts.items()) + ">"
    ).encode()

def pytest_sessionstart(session):
    global stream, offset
    stream=(ROOT/"suite_incremental.xml").open("w+b")
    head=header();stream.write(head+TAIL);offset=len(head);stream.flush()

def pytest_runtest_logreport(report):
    global offset
    states.setdefault(report.nodeid, []).append(report)
    if report.failed:
        failed.add(report.nodeid)
        (ROOT/"suite_failing_tests.txt").write_text("".join(x+"\n" for x in sorted(failed)))
    if report.when!="teardown":
        return
    reports=states.pop(report.nodeid)
    node=ET.Element("testcase",name=report.nodeid,
                    classname=report.nodeid.split("::")[0],
                    time=str(sum(r.duration for r in reports)))
    counts["tests"]+=1
    errors=[r for r in reports if r.failed and r.when!="call"]
    failures=[r for r in reports if r.failed and r.when=="call"]
    skipped=[r for r in reports if r.skipped]
    if errors:
        counts["errors"]+=1
        ET.SubElement(node,"error",message="setup/teardown failed").text="\n".join(r.longreprtext for r in errors)
    elif failures:
        counts["failures"]+=1
        ET.SubElement(node,"failure",message="call failed").text="\n".join(r.longreprtext for r in failures)
    elif skipped:
        counts["skipped"]+=1
        ET.SubElement(node,"skipped").text="\n".join(str(r.longrepr) for r in skipped)
    payload=ET.tostring(node,encoding="utf-8")+b"\n"
    stream.seek(offset);stream.write(payload+TAIL);offset+=len(payload)
    stream.truncate();stream.seek(0);stream.write(header());stream.flush()

def pytest_sessionfinish(session,exitstatus):
    if stream is not None:
        stream.flush();stream.close()
    (ROOT/"suite_failing_tests.txt").write_text("".join(x+"\n" for x in sorted(failed)))

```

## Report-only file inventory

Full-file line ranges below describe report/evidence files, not a claim that all preserved historical lines changed.

| File | Full-file line range |
|---|---|
| tools/dr_isl/PHASE_3_REPORT.md | 1–2517 |
| .agents/memory/ignored-simulator-source.md | 1–34 |
| .agents/memory/s1-study-harness.md | 1–49 |
| tools/dr_isl/PHASE_3_EVIDENCE.json | 1–64107 |
| tools/dr_isl/PHASE_3_TC06.xml | 1–1 |
| tools/dr_isl/PHASE_3_FAILING_TESTS.txt | 1–17 |

Exact memory-document addition ranges:
```diff
diff --git a/.agents/memory/ignored-simulator-source.md b/.agents/memory/ignored-simulator-source.md
index 9bb5614..e867fba 100644
--- a/.agents/memory/ignored-simulator-source.md
+++ b/.agents/memory/ignored-simulator-source.md
@@ -22 +22,13 @@ An unsuccessful staging command does not prove that the index is unchanged.
-**How to apply:** Inspect `git diff --cached` and short status before retrying. Do not broaden a force-add merely because the first command reported failure.
\ No newline at end of file
+**How to apply:** Inspect `git diff --cached` and short status before retrying. Do not broaden a force-add merely because the first command reported failure.
+
+A stash made after an automatic checkpoint is a delta against that checkpoint,
+not necessarily a patch containing the entire candidate implementation.
+
+**Why:** After application files had been restored to a pre-candidate base,
+applying the later stash restored only follow-on edits and produced conflicts,
+rather than restoring all candidate files.
+
+**How to apply:** Inspect the stash parent and full tree before recovery. When
+restoring a complete candidate is authorized, verify the listed candidate paths
+against the full stash tree; do not assume a successful delta application proves
+the complete candidate is present.
\ No newline at end of file
diff --git a/.agents/memory/s1-study-harness.md b/.agents/memory/s1-study-harness.md
index 43b86d2..6866cc1 100644
--- a/.agents/memory/s1-study-harness.md
+++ b/.agents/memory/s1-study-harness.md
@@ -33 +33,17 @@ tick-identical) from H2-24h informed (not certified and permitted to change
-under turbine start-eligibility correction, with before/after deltas reported).
\ No newline at end of file
+under turbine start-eligibility correction, with before/after deltas reported).
+
+For the approved start-eligibility comparison, pre-rejection differences may
+affect only commitment decision telemetry (action, target, blocked-by, reason),
+and only when the baseline proposed an ineligible unit and actually vetoed it.
+Every such tick must be enumerated with both values and the veto evidence.
+Physical fields must still match; canonical full hashes retain their contract.
+
+**Why:** The baseline exposes a core proposal in tick telemetry even when the
+informed controller vetoes it before any start command. Moving eligibility
+earlier can therefore change decision telemetry before the first rejected
+command without changing physical state. The reviewer approved this limited
+acceptance amendment on 2026-10-22, not a general waiver for prefix differences.
+
+**How to apply:** Keep the full hash and the decision-excluded prefix comparison
+separate, prove each allowed exception against the native baseline veto, and
+preserve the certified H1 physical/metric identity requirement.
\ No newline at end of file
```
