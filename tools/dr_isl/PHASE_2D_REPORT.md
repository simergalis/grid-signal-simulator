# DR-2026-10-20-ISLAND-COLLAPSE — FOURTH RESUMPTION: A1/A2 PASS; A3 STOP

CURRENT STATUS: STOPPED at the literal A3 source-diff criterion. NOT FINISHED.
Measurement base: ebeeb186c53352eb109fdd572fa2370e00031394, containing the T2
candidate. No application code, configuration, scenario, test or model parameter
was changed during this resumption. No publication, deployment, push or Phase 3.
The revised acceptance supersedes the third-resumption T3 STOP criterion.

P = attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/.
T = /tmp/DR-ISL-phase2d/. Source line numbers below are at ebeeb18.
Literal A1/A2 results, sample tick sets and A3 AST comparisons are preserved in
tools/dr_isl/PHASE_2D_FOURTH_EVIDENCE.json.
The full A3 two-file diff is tools/dr_isl/PHASE_2D_A3_DIFF.md.

## Fourth resumption — reconstructed diagnostic and reference checkout

The earlier /tmp/DR-ISL-phase2d directory did not survive. The unchanged persisted
tools/dr_isl/baseline_runner.py supplied pin_spec, plain, encoded, the four hash
exclusions, SEED=1729 and WALL_CLOCK=1792454400.0. It was not edited.
Scratch scripts: T/fourth_a1.py and T/fourth_a2.py.
Reference scratch worktree: T/fourth-old at 01ce053. The six previously authorized
support files were restored into that scratch checkout from c9c4f2e only.
No source file was copied into or changed in the main application's package.

Base-demo arms use StudyRunExecutor._expanded_spec and its real _probe, then
exactly the context/replay construction at P/study_harness/executor.py:336–375:
mode baseline/informed, kube_clusters/slurm_config removed, recorded workload
events installed, demand_replay_trace installed, same run id convention,
seed 42, no parameter overrides, no cached execution or artifact serialization.
The other scenarios use ScenarioSpec validation/model_dump, pin_spec, factory,
corruption schedule when configured and RunManager. Slurm GPU-peaks is seeded
by P/api/routes/scenarios.py:1103–1348,1481–1484, not a standalone JSON;
its actual _build_persistent_slurm_gpu_peak_scenario() is used in both versions.

Pinning: Python/NumPy/fabric 1729, wall 1792454400.0, per-diesel 1729+i,
kube and configured generator/corruption pinning via the persisted helper.
Physical-field comparison excludes exactly advisory_telemetry, fabric_modal,
wall_stamp_utc, insufficient_reserve_proposal_id, as the existing hash contract.
All other TickResult dataclass fields, recursively including nested fields, are
compared exactly after normalization; no numeric tolerance is used for A1.

Only summaries and selected sample/window evidence are written to disk.
A1 tick objects transit bounded pipes (queue depth 2), not full tick exports.
All scratch Python processes use RLIMIT_FSIZE=200000000.
The first Slurm A1 attempt exceeded the foreground shell's 300 s limit and
returned no result; its processes ended. The background bounded-stream retry
completed. This timeout is not relabelled a physical-identity failure.
Scratch-only field/stride corrections were made before valid A2 results:
TickResult's curtailment field is p_dispatch_curtailed_mw, and stride=1 must
select all eligible ticks. Zero-sample attempts are not counted as passes.

## Fourth resumption — A1 PASS, all seven cases

First on-bus means SYNCHRONISED or UNLOADING before/after the physics step.
A1 compares through the tick immediately BEFORE that first tick in either
version. Prefix execution ends after obtaining the first on-bus tick; no
first-on-bus tick is included in the required equality claim.

| Scenario/path | 01ce053 first on-bus tick / decision seconds | ebeeb18 first on-bus tick / decision seconds | Required ticks compared | First differing field | Result |
|---|---|---|---:|---|---|
| base demo, conventional | 68 / 335.0 | 68 / 335.0 | 67 | null | PASS, exact |
| base demo, informed | 70 / 345.0 | 70 / 345.0 | 69 | null | PASS, exact |
| hybrid | 3 / 10.0 | 3 / 10.0 | 2 | null | PASS, exact |
| fc-bess-diesel | never during completed run | never during completed run | 252 | null | PASS, exact |
| fc100-v2 | never during completed run | never during completed run | 264 | null | PASS, exact |
| fc100-zero-hot-v2 | never during completed run | never during completed run | 264 | null | PASS, exact |
| Slurm GPU-peaks | 761 / 3800.0 | 761 / 3800.0 | 760 | null | PASS, exact |

For the three never-on-bus cases, the compared tick counts are the complete
RunManager-produced runs, not a claim that the engine reached a longer
configured horizon. All captured A1 ticks have 0 physical-balance failures.
For other cases A1 is a prefix, not a full-run balance acceptance test.
Hashes over the complete never-on-bus runs (old = HEAD):
- fc-bess-diesel: 29e518216802048738f35f06677b48332cc00da4c073e2809b1dd9c92d07aa6a
- fc100-v2: 98ede81f8d3f4b3c7608fcb8ca0b33a50c254b620312ca2639b7c49d0cb06e6b
- fc100-zero-hot-v2: 786dfb56ee4bf7be3dca3af227cd4915b6ce8a54107b06a0bdb5da13f2f2f00b
These new paired A1 hashes are not substituted for the persisted Phase 2c/A4
reference hashes. A4 has not been performed.

## Fourth resumption — A2 PASS, all seven cases; float-exact

At the old RunContext's evaluate_tick entry, AFTER due events/controller commands
have been applied, snapshot the complete SimulationState, SimClock and Python/
NumPy RNG states using pickle. Restore that identical object graph separately
in 01ce053 and ebeeb18; set the plane guard, restore RNG states and call one
evaluate_tick. No field-by-field reconstruction or state stripping is used.
State snapshots are transmitted in pipes and discarded, never exported to disk.
The old full-trajectory allocation output is also checked against the restored
old allocation output, guarding the fidelity of capture/restore itself.

Samples are spread over the original horizon with stride ceil(total_ticks/198),
plus base-demo ticks 66 and 1111. Require diesel off bus both before and after
the donor's tick, excluding startup-completion transition ticks. Maximum 200
samples per case. Both special base-demo ticks are present in BOTH arm results.

The measured pre-diesel residual is intercepted directly at the coordinator
step argument, not recomputed from a second balancing formula.
Compare turbine_output_mw, bess_output_mw, fuel_cell_output_mw,
p_dispatch_curtailed_mw and the pre-diesel residual.

| Scenario/path | Restored states | Max GT MW | Max BESS MW | Max FC MW | Max curtailment MW | Max residual MW | Result |
|---|---:|---:|---:|---:|---:|---:|---|
| base demo, conventional | 131 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | PASS, float-exact |
| base demo, informed | 136 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | PASS, float-exact |
| hybrid | 2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | PASS, float-exact |
| fc-bess-diesel | 126 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | PASS, float-exact |
| fc100-v2 | 132 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | PASS, float-exact |
| fc100-zero-hot-v2 | 132 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | PASS, float-exact |
| Slurm GPU-peaks | 127 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | PASS, float-exact |
| TOTAL | 786 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | PASS, float-exact |

Maxima cover all three pairwise comparisons: donor output, restored old output,
restored HEAD output. No first_difference and no errors in any valid result.
The 1e-12 MW allowance is not needed. Full sample tick lists are in the evidence
JSON. A2 donor summaries do NOT compute full-run physical hashes or balance
counts; their null fields must not be interpreted as zero failure counts.

## Fourth resumption — A3 source audit and literal STOP condition

Requested condition: the diff on the listed lifecycle functions "shows only
the approved IMPL-ISL-14/15 changes".
That condition is NOT literally true for the full listed method bodies.
They also contain existing D10 delivery/capability bookkeeping and sequencing
changes. This is a scope/acceptance mismatch, NOT a finding that a new START
predicate was introduced and NOT a claim that D10 was globally unapproved.
No attempt is made to remove or relabel those D10 hunks as IMPL-ISL-14/15.

AST comparison (including literals/control flow, excluding line attributes):
| Method | 01ce053 lines | HEAD lines | AST identical? |
|---|---|---|---|
| DieselFleetCoordinator.step | diesel_fleet.py:180–245 | :180–257 | no |
| _begin_episode | :247–256 | :259–268 | yes |
| _start_due_primary_units | :258–272 | :270–284 | yes |
| _begin_unloading | :328–331 | :340–343 | yes |
| _finish_unloading | :333–345 | :345–357 | yes |
| _complete_cooldown_if_ready | :347–361 | :359–373 | yes |
| DieselModule.command_start | asset_modules.py:1421–1445 | :1422–1446 | yes |
| DieselModule.can_start | :1408–1419 | :1409–1420 | yes |
| DieselModule.advance | :1447–1512 | :1448–1520 | no |
| DieselModule.command_stop | :1517–1531 | :1554–1568 | yes |
| DieselModule.resume_from_unloading | :1533–1540 | :1570–1580 | no |

Every zero-context hunk in the two-file diff is classified below. Changes not
inside listed lifecycle bodies are included so the audit hides no source hunk.
Paths are under P/core; ranges refer to ebeeb18. Literal full diff is preserved.
| Hunk | Classification / literal change |
|---|---|
| asset_modules.py:1360 | D10, new _dispatch_ceiling_mw state, not IMPL-ISL-14/15. |
| :1448 | D10, advance(dispatch_controlled=False) keyword, not IMPL-ISL-14/15. |
| :1468 | D10, initialize delivery ceiling on successful synchronization. Existing success/state-transition condition unchanged. |
| :1475 | D10, retain delivered output before advancing SYNCHRONISED capability. |
| :1502–1506 | D10, retain advanced capability, restore delivered output if dispatch-controlled; not IMPL-ISL-14/15. |
| :1525–1553 | D10, dispatch floor/ceiling and target application; synchronized 0.30 proxy, unchanged unloading tail output. |
| :1575–1577 | D10, expose actual unloading tail as ceiling when resuming; resume guard/state assignment/timer reset unchanged. |
| diesel_fleet.py:115 | IMPL-ISL-14, on-bus output docstring. |
| :120 | IMPL-ISL-14, include UNLOADING in measured fleet output. |
| :187–188 | D10, advance_units/consume_fuel flags, not IMPL-ISL-14/15. |
| :200–203 | D10, conditional lifecycle/fuel phase calls replacing unconditional calls. |
| :233 | IMPL-ISL-15, attempt due synchronized stops before counting restored time. |
| :235–239 | IMPL-ISL-15, count restoration only when UNLOADING and no synchronized stop remains refused. |
| :241–242 | IMPL-ISL-15, reset restoration time otherwise. |
| :247–250 | IMPL-ISL-15, require every unloading ramp to complete before finish. |
| :375–383 | D10, advance_units/record_dispatch_fuel helpers; achieved dispatch drives fuel. |
| :390 | IMPL-ISL-14, UNLOADING fuel counted by the on-bus filter. |

Two decisive additional D10 hunks within explicitly listed functions:
```
# asset_modules.py:1448
-    def advance(self, sim_time: float, dt_seconds: float) -> None:
+    def advance(self, sim_time: float, dt_seconds: float, *, dispatch_controlled: bool = False) -> None:

# asset_modules.py:1502–1506
+            self._dispatch_ceiling_mw = self._current_output_mw
+            if dispatch_controlled:
+                # D10: advance machine capability, not delivered power.  A
+                # subsequent accepted stop must capture actual dispatched MW.
+                self._current_output_mw = _delivered_before_advance
```
START predicates in step and the AST-identical start/can-start methods are not
changed. However, a claim that the full named methods differ ONLY for
IMPL-ISL-14/15 would be false. STOP at A3 as written; the separately classified
D10 output-only/sequencing hunks require clarification of that condition
before A3 can be recorded as passed.

## Fourth resumption — remaining scope NOT EXECUTED after A3 STOP

- A4: no Phase 2c no-diesel reference acceptance or H 24h repeated metric/tick
  matrix was run in this resumption.
- A5: no complete post-on-bus, first-40-tick and later lifecycle divergence
  report was produced. A1 prefix differences at the first on-bus tick are
  permitted and are not treated as a new failure.
- R3: no current-versus-01ce053 test-signature runs or stale-test updates.
- 2d.5: no accepted complete A/B metric table, app-path parity check or five-
  diesel-scenario before/after table. A2 donor trajectories are instrumentation
  inputs, not a substitute for those metric/guard/repetition checks.
- 2d.6: no full suite, no counts, no added/removed failure-set comparison and
  no newly finalized PHASE_2D_FAILING_TESTS.txt.
- 2d.7: no successful D10 implementation acceptance commit. ebf2ea9, fb185a6
  and ebeeb18 remain existing, unvalidated automatic implementation checkpoints;
  1f76f87 is the third-resumption report-only commit. This resumption changes
  only the report/evidence and the superseded acceptance-scope memory note.

No further simulations or tests were started after the A3 STOP decision.
The existing historical reports follow, unchanged except for status headings.
Their START-list/off-bus trajectory criteria are superseded, not current gates.
Final report-only commit hash and git status are printed in the final response.

---

# Historical report — THIRD RESUMPTION: T3 STOP

**CURRENT STATUS: STOPPED at the first T3 verification pair. NOT FINISHED.**
Base: fb185a6e8fbf8ba62752ebc65dc4b58bc9136241.
P = attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/.
T = /tmp/DR-ISL-phase2d/.
This section supersedes earlier status sections, which remain below.
No further scenario run, test, suite, workflow restart, publication, deployment,
push or Phase 3 was started after the T3 result was returned.

## Third resumption — T0 corrected START detector and completed measurements

Scratch tool: T/gap_gate.py. Detection now uses DieselState enum members:
`before_enums[unit.asset_id] != DieselState.STARTING and unit.state == DieselState.STARTING`.
No string literal determines whether a START was accepted. Enum values are used
only when printing states. Accepted transitions are captured around the real
DieselFleetCoordinator.step invocation.

| Path | 01ce053 accepted START ticks (decision seconds) | fb185a6 accepted START ticks (decision seconds) | Ticks / balance failures, each |
|---|---|---|---|
| Base demo, harness conventional, seed 42 | 66 (325.0), 371 (1850.0) | 66 (325.0) | 1440 / 0 |
| Base demo, harness informed, seed 42 | 68 (335.0), 371 (1850.0) | 68 (335.0) | 1440 / 0 |
| scenario-fc100-islanded-v2, RunManager | none | none | 264 / 0 |

All starts above are diesel-000. Each T0 version/path ran once.
FC100-v2 before/after physical SHA-256:
d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3,
identical. Its maximum turbine/BESS/FC/gap differences are all 0.0 MW.
The pre-conform conventional off-bus maxima were GT 17.5, BESS 30.0, FC 0.0,
gap 2.5 MW; informed: GT 5.0, BESS 13.124560130547284, FC 0.0, gap 5.0 MW.

Harness paths use the actual StudyRunExecutor._expanded_spec, _probe and
_run_mode, with seed 42, reuse_cache=False and no parameter overrides.
The probe is not included in reported START lists. Writer/cache persistence is
output-only intercepted; no full physical or compact tick export is written.
Python/NumPy/fabric 1729, wall clock 1792454400.0, configured kube/generator/
corruption pinning and per-diesel 1729+i use the persisted baseline helper.
The same helper file is unchanged. Historical 01ce053 scratch execution uses
only the six authorized support files restored from the tracking commit.

## Third resumption — T1 pre-edit hunk audit

Literal full diff is preserved in tools/dr_isl/PHASE_2D_T1_DIFF.md and
T/T1_allocator_before_conform.diff. It compares exactly 01ce053..fb185a6 on the
five requested files. The table identifies EVERY zero-context hunk by its
fb185a6 line(s); source line numbers in this section refer to fb185a6, not the
subsequent candidate. "Yes/zero" means the statement or call executes with an
off-bus fleet but its diesel numerical contribution is zero.

| File under P/core; fb185a6 hunk line(s) | Executes with NO diesel on bus? / effect |
|---|---|
| asset_modules.py:1360 | Yes, instance-field initialization; no primary allocation effect. |
| asset_modules.py:1448 | Signature/interface definition; advance is called for off-bus units. |
| asset_modules.py:1468 | At STARTING-to-SYNCHRONISED completion; not a steady off-bus output. |
| asset_modules.py:1475 | No: inside SYNCHRONISED branch. |
| asset_modules.py:1502–1506 | No: inside SYNCHRONISED branch. |
| asset_modules.py:1525–1553 | Properties are queried off bus and return 0; apply target writes SYNCHRONISED only. |
| asset_modules.py:1575–1577 | No: resume from UNLOADING, which is on bus. |
| diesel_fleet.py:115 | Docstring only. |
| diesel_fleet.py:120 | Yes: aggregate filter executes, yielding 0 with no on-bus units. |
| diesel_fleet.py:187–188 | Signature/default flags; no direct primary output. |
| diesel_fleet.py:200–203 | Yes: lifecycle/fuel advancement dispatch; fuel filter skips off-bus units. |
| diesel_fleet.py:233 | Condition evaluates; unloading request requires SYNCHRONISED. |
| diesel_fleet.py:235–239 | Condition evaluates; restore-time increment requires UNLOADING. |
| diesel_fleet.py:241–242 | Yes: resets restore timer in the other branch; no primary allocation. |
| diesel_fleet.py:247–250 | Unloading completion guard; not reached without an UNLOADING unit. |
| diesel_fleet.py:375–383 | Methods called for configured fleets; advancement can complete startup; fuel skips off-bus units. |
| diesel_fleet.py:390 | Yes: fuel filter, skips off-bus units. |
| loading.py:36–37 | Optional-bound interface; no independent dispatch path. |
| loading.py:69–74 | YES at tick 66: replaces MSL/rated envelopes with supplied ramp bounds. |
| loading.py:107 | Yes; sequential limit uses ceiling_i, equal to rated when bounds=None. |
| loading.py:122 | Yes; headroom uses ceiling_i, equal to rated when bounds=None. |
| loading.py:146–153 | Yes: pure ramp helper, same prior clamp arithmetic. |
| loading.py:158–159 | Optional-bound interface. |
| loading.py:170–172 | YES at tick 66: forwards the changed bounds into the same allocator. |
| loading.py:174 | Yes: applies the same ramp arithmetic through the helper. |
| loading.py:203 | Yes when explicit targets are used; same prior clamp arithmetic. |
| power_source_priority.py:42 | Enum definition at import; no numerical allocation. |
| simulation_core.py:32–35 | Imports/interface only. |
| simulation_core.py:786 | Optional diesel availability argument, default 0. |
| simulation_core.py:830–845 | No when diesel availability is 0: diesel ranking source is not appended. |
| simulation_core.py:852 | Yes: zero diesel allocation entry initialized. |
| simulation_core.py:1696–1733 | YES: gated by configured fleet, not on-bus fleet; changes GT envelopes before first START. |
| simulation_core.py:1783–1799 | Yes: advances configured units and queries zero floor/headroom while off bus. |
| simulation_core.py:1802 | YES: configured-fleet branch changes allocation demand envelope even when off bus. |
| simulation_core.py:1805 | Comment only. |
| simulation_core.py:1807 | Yes/zero: subtracts diesel floor. |
| simulation_core.py:1813 | Yes/zero: supplies diesel headroom to the single ranker. |
| simulation_core.py:1815–1823 | Yes/zero: diesel target and per-unit application, no off-bus output write. |
| simulation_core.py:1836 | Yes/zero: subtracts diesel target from conventional following target. |
| simulation_core.py:1870–1871 | YES: passes bounds to turbine loading even while diesel is off bus. |
| simulation_core.py:1975 | Comment only. |
| simulation_core.py:1977 | Yes/zero: subtracts diesel target from BESS shortfall. |
| simulation_core.py:1998 | YES: configured-fleet test suppresses previous diesel delivery even while off bus. |
| simulation_core.py:2038 | Yes/zero: subtracts diesel target from BESS arbitration demand. |
| simulation_core.py:2044–2046 | Residual documentation only. |
| simulation_core.py:2055–2065 | Yes: actual residual controls lifecycle, fuel and snapshot; START predicate unchanged. |

Tick-66 values, conventional T0 (before any diesel is on bus):
GT must-run 17.5 MW in both; unbounded incremental capacity 32.5 MW becomes
5.0 MW with bounds {"gt-spin-01":[8.75,11.25],"gt-spin-02":[8.75,11.25]}.
BESS allocation 29.0 MW in both. Turbine economic allocation:
11.801943799295508 versus 5.0 MW; thermal target 29.301943799295508 versus
22.5 MW; achieved GT 20.0 versus 22.5 MW. Residual 9.301943799295508 versus
6.801943799295508 MW. Diesel floor/headroom/target are 0.0 MW.
The causative chain is simulation_core.py:1696–1733 → :1813 → :1870–1871,
loading.py:69–74/:107/:122. Applying this envelope while diesel is OFF BUS is
NOT required to load-follow an on-bus diesel, rank it last, back it down first
or enforce its SYNCHRONISED minimum. T2 was therefore attempted.

## Third resumption — T2 candidate, not accepted by T3

Only P/core/simulation_core.py changed, compared with fb185a6:
- :1696–1704 advances diesel lifecycle once before reading on-bus status and
  installs diesel-specific primary bounds only when a unit is on bus.
- :1789–1796 removes the later duplicate location of that same advance call.
- :1800–1803 uses the canonical primary request envelope while diesel is off bus.
- :2002 uses previous-diesel emergency-support accounting while diesel is off bus.
The original single ranker and single loading application remain. D10-gap stays
the actual post-primary, post-emergency-BESS residual. No START predicate,
timer, minimum-load value, dispatch cost, reserve formula, frequency/protection,
scenario JSON or test was changed. No numerical runtime constant was added.
The full candidate diff is in tools/dr_isl/PHASE_2D_T2_DIFF.md.

## Third resumption — T3 FAILED, first verification pair only

Pair: base demo, harness conventional, seed 42, no overrides, reuse_cache=False.
Before = 01ce053. After = fb185a6 plus the T2 candidate. Once each.
Both completed 1440 ticks with 0 physical-balance failures.
The tick-66/pre-diesel discrepancy is absent after T2: the first overall gap
difference now occurs at tick 126 while diesel IS on bus.

| Metric | Before | After |
|---|---|---|
| Physical SHA-256 | 314adcaf836d34add6dc5f3dc5637586664e80b0045c943da4bec0c0214dd21e | 90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1 |
| Accepted diesel START ticks | 66, 371 | 66 |
| START decision seconds | 325.0, 1850.0 | 325.0 |
| Off-bus maximum absolute GT-output difference | — | 17.5 MW |
| Off-bus maximum absolute BESS-output difference | — | 30.0 MW |
| Off-bus maximum absolute FC-output difference | — | 0.0 MW |
| Off-bus maximum absolute residual difference | — | 0.0 MW |

Off-bus maxima above use aligned ticks where NEITHER version has diesel on bus,
checked before and after the coordinator invocation. This subset already fails
the requested zero-output-difference criterion; no broader equality is claimed.

First overall residual difference: tick 126, decision time 625.0 s.
| Term | Before | After |
|---|---|---|
| Diesel state | synchronised | synchronised |
| Demand MW | 22.23416977389537 | 22.23416977389537 |
| GT MW | 45.0 | 45.0 |
| BESS MW | -22.76583022610463 | -28.76583022610463 |
| FC MW | 0.0 | 0.0 |
| Diesel dispatch target MW | no D10 target variable | 6.0 |
| Pre-diesel residual MW | 0.0 | 6.0 |

The candidate residual equals its 6.0 MW diesel target here:
22.23416977389537 - 45.0 - (-28.76583022610463) = 6.0.
That positive gap takes the branch resetting restore time and requesting due
starts in P/core/diesel_fleet.py:222–230, instead of the zero-gap unloading
branch :232–234. These are printed terms and source ordering, not a claim that
every later lifecycle difference has been independently traced.

First aligned BOTH-OFF-BUS output difference: tick 1111, decision time 5550.0 s.
| Term | Before | After |
|---|---|---|
| Diesel state, before/after coordination | offline / offline | offline / offline |
| Demand MW | 4.757366853202085 | 4.757366853202085 |
| Turbine MW | 35.0 | 35.0 |
| BESS MW | -30.0 | -0.0 |
| FC / residual MW | 0.0 / 0.0 | 0.0 / 0.0 |
| BESS setpoint MW | -30.242633146797914 | -30.242633146797914 |
| BESS physical/normal ceiling MW | 29.0 / 29.0 | 29.0 / 29.0 |
| BESS energy ceiling MW | 39977.176733389046 | 41368.37047956742 |
| GT must-run MW | 35.0 | 35.0 |
| GT incremental available MW | 65.0 | 48.75 |
| Synchronised loading fleet target MW | 35.0 | 26.25 |
| Diesel floor/headroom/target MW | no D10 variables | 0.0 / 0.0 / 0.0 |
| Diesel-specific output bounds | absent | null |

Matching current primary dispatch code with diesel terms zero does not establish
identical complete histories: the measured post-on-bus BESS energy and turbine
populations differ at tick 1111. No additional change to reconcile those
histories, the residual, lifecycle, commitment or BESS physics was attempted.

## Third resumption — STOP consequences, storage and commits

T3 conventional failed. T3 informed, hybrid, fc-bess-diesel, fc100-v2,
zero-hot-v2, Slurm GPU-peaks were NOT run after T2. T0 FC100-v2 equality above
is a PRE-T2 measurement and is not relabelled a T3 acceptance result.
No-diesel hash checks, H1/H2 two-repetition acceptance checks, R3 signatures,
remaining 2d.5 metrics/app comparison and 2d.6 full suite were NOT run.
No new PHASE_2D_FAILING_TESTS.txt exists; suite counts and failure-set deltas
remain unavailable.

ebf2ea987b89b9f55c6c19ddc24cad3970c7de9b and
fb185a6e8fbf8ba62752ebc65dc4b58bc9136241 are automatic UNVALIDATED checkpoints.
T2 remains an uncommitted, unvalidated candidate because the gate failed before
2d.7. No successful-conformance implementation commit is claimed.
The report-only commit contains this report, its T1/T2 literal diff appendices
and the acceptance-scope memory note. Its hash and final git status are printed
in the final response.

All scratch scripts set RLIMIT_FSIZE=200000000; physical hashes are streamed.
T0/T3 store summaries and only first-difference windows, not full tick exports.
Evidence: T/T0-scenario-uneven-multisched-01-baseline.json,
T/T0-scenario-uneven-multisched-01-informed.json,
T/T0-scenario-fc100-islanded-v2-app.json,
T/T3-scenario-uneven-multisched-01-baseline.json, T/gap_gate.py,
T/T1_allocator_before_conform.diff and T/PHASE_2D_REPORT.md.
The six support-file tracking changes remain content-identical and committed
as c9c4f2e694dc267da456e4f1c971ff660b196a74. No .gitignore edit.

---

# Historical report — SECOND RESUMPTION: G1 STOP / G2 PASS

**CURRENT STATUS: STOPPED at 2d.G1. NOT FINISHED.**
This section supersedes the historical status sections below. Base was
153783a2ad02680db7bb8920874e16c8c4f3058c. No Phase 3, publication, deployment,
push, workflow restart, or subsequent scenario/test run was performed after
the G1 mismatch was returned.

Package alias P = `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`.
Scratch alias T = `/tmp/DR-ISL-phase2d/`.

## Second resumption — 2d.G2 completed before the G1 comparison

Tracking-only commit: **c9c4f2e694dc267da456e4f1c971ff660b196a74**.
Message: `DR-ISL IMPL-ISL-16: track six support files under ignored attached_assets/ (no content change)`.
Exactly the six authorized files were force-added; .gitignore was not changed.
Each was untracked before this commit. The first hash column was printed before
staging; after, committed-blob and clean-checkout hashes were checked separately.

| File relative to P | SHA-256 before | SHA-256 after / committed / clean checkout |
|---|---|---|
| runtime/reference_forecast.py | 2fa438a2380a84e954a20a29574aa3b269be2133654f890fef2ca74ef4518e8d | 2fa438a2380a84e954a20a29574aa3b269be2133654f890fef2ca74ef4518e8d |
| runtime/fuel_cell_defaults.py | 208107e53c3a3e985001ffb4126c61035955ac1a049327fb8b0693e71854f07f | 208107e53c3a3e985001ffb4126c61035955ac1a049327fb8b0693e71854f07f |
| core/infrastructure_admission.py | d86ee3c2697f4d21f6f042685f27d00bb2b4ea65c2058129e9cc05f88225d825 | d86ee3c2697f4d21f6f042685f27d00bb2b4ea65c2058129e9cc05f88225d825 |
| config/scenarios/S10_mit_supercloud_2021-08-11.json | 8126ee38ef2206f55d28ea9f4da029df836fbf7c4daf7d65e266d821f323f7ad | 8126ee38ef2206f55d28ea9f4da029df836fbf7c4daf7d65e266d821f323f7ad |
| config/scenarios/scenario-100mw-fuel-cell-bess-diesel.json | 2573809039859f38bce0d83ca227ca8dd9d34a7e88ceb795cbcbf3eca864d388 | 2573809039859f38bce0d83ca227ca8dd9d34a7e88ceb795cbcbf3eca864d388 |
| config/scenarios/scenario-kubernetes-scheduler-demo.json | d08196037183229e46e90882372df4b587821ebba698acb1d217d462c6e3d36f | d08196037183229e46e90882372df4b587821ebba698acb1d217d462c6e3d36f |

Worktree: T/g2-checkout, detached at c9c4f2e. No files were copied into it.
`import api.main` returned `ModuleNotFoundError: No module named 'api.main'`.
The actual entry is `api.app:app` (P/scripts/start_prod.sh:115).
The actual-entry import returned **G2_APP_ENTRY_IMPORT=PASS FastAPI**.
Seeder-path build returned:
`G2_BUILD_SJ1=PASS {"end_sim_time":3600.0,"diesel_units":0,"turbines":0}`.
No missing dependency/file was reported by the actual-entry import or SJ-1 build.
Import was checked without entering the app lifespan; no API request was made.

Committed file line ranges: runtime/reference_forecast.py:1–23;
runtime/fuel_cell_defaults.py:1–4; core/infrastructure_admission.py:1–765;
S10 JSON:1; scenario-100mw-fuel-cell-bess-diesel.json:1–727;
scenario-kubernetes-scheduler-demo.json:1–84.

## Second resumption — 2d.G1 candidate and failed equality gate

The availability gap/call was removed at P/core/simulation_core.py:1783–1792.
The existing physical residual after turbine loading and BESS arbitration,
including emergency release, is computed once at :2044–2053 and passed to the
coordinator at :2056–2059. No second dispatch or reserve calculation was added.
This is a candidate working-tree change, NOT a validated implementation.
No scenario content, dispatch cost, floor formula, commitment, frequency,
protection, baseline runner, or test was edited.

Literal candidate diff against c9c4f2e:
```diff
@@ -1783,22 +1783,9 @@
     _diesel_dispatch_floor_mw = 0.0
     _diesel_dispatch_headroom_mw = 0.0
     if state.diesel_units:
-        # Approved D10 signal amendment: primary-only achievable shortfall,
-        # using this allocation's ramp/policy/AC-energy bounds, not the primary
-        # MW displaced by a live diesel minimum. This is a capacity diagnostic,
-        # not a second dispatch. START condition and every timer stay unchanged.
         state.diesel_fleet_coordinator.advance_units(
             sim_time, dt_seconds, dispatch_controlled=True,
         )
-        _diesel_control_gap_mw = max(
-            0.0, p_dispatch_required_mw - fuel_cell_output_mw
-            - _turbine_must_run_mw - _turbine_incremental_available_mw
-            - _bess_available_mw,
-        )
-        state.diesel_fleet_coordinator.step(
-            gap_mw=_diesel_control_gap_mw, sim_time=sim_time,
-            dt_seconds=dt_seconds, advance_units=False, consume_fuel=False,
-        )
         _diesel_dispatch_floor_mw = sum(t.dispatch_floor_mw for t in state.diesel_units)
         _diesel_dispatch_headroom_mw = sum(
             t.dispatch_ceiling_mw - t.dispatch_floor_mw for t in state.diesel_units
@@ -2054,9 +2041,9 @@
         bess_dispatch_ceilings_mw=_bess_dispatch_ceilings_mw,
         bess_soc_floors_mwh=_bess_soc_floors_mwh,
     )
-    # Coordinate diesel from the measured residual after primary source
-    # arbitration. Diesel must not reduce the BESS planner's input and then
-    # leave the same MW in the turbine dispatch demand.
+    # DR D10-gap: this allocation's achieved pre-diesel residual includes the
+    # emergency BESS release and supersedes the availability-based gap. Compute
+    # it once, after non-diesel delivery, for coordination and deficit reporting.
     _gap_before_diesel_mw = max(
         0.0,
         p_dispatch_required_mw
@@ -2066,6 +2053,10 @@
     )
     diesel_enabled = bool(state.diesel_units)
     if diesel_enabled:
+        state.diesel_fleet_coordinator.step(
+            gap_mw=_gap_before_diesel_mw, sim_time=sim_time,
+            dt_seconds=dt_seconds, advance_units=False, consume_fuel=False,
+        )
         state.diesel_fleet_coordinator.record_dispatch_fuel(dt_seconds)
         _diesel_snapshot = state.diesel_fleet_coordinator.snapshot()
     else:
```

### Completed comparison and first mismatch

Scenario: **scenario-uneven-multisched-01**, canonical seeder-path RunManager,
not a study-harness arm. Both versions ran at instant playback, once each.
Before: scratch worktree T/01ce053 at 01ce053, with only the six G2 support
files restored from c9c4f2e to make the historical checkout runnable.
After: main working tree at c9c4f2e plus the candidate diff above.
T/gap_gate.py uses ScenarioSpec.model_validate_json → model_dump(mode="json"),
the persisted runner's pin_spec, fixed wall clock 1792454400.0, fabric/Python/
NumPy 1729, per-diesel 1729+i, configured corruption pinning, RunManager and
a streaming sink. tools/dr_isl/baseline_runner.py is unchanged.
This is a diagnostic comparison, not the twice-each acceptance matrix.

| Result | Before 01ce053 | After candidate |
|---|---|---|
| Ticks completed | 1440 | 1440 |
| Captured coordinator gap ticks | 1440 | 1440 |
| Balance failures | 0 | 0 |
| Physical SHA-256 | 4a3232ee26b604f48b9e48346680993b12bd04c338134a6be0ae6520a94268f4 | b4d926e5324e26beaefac726e0edd6543752f447cc1057039249283b67c9ad49 |

**Maximum absolute gap difference = 11.5 MW.**
**First differing tick = 66; decision sim_time = 325.0 s.**
Before gap = **9.301943799295508 MW**; after gap = **6.801943799295508 MW**.
At this tick both captured state transitions are diesel-000 **offline → starting**.
The complete captured allocation terms at that first difference follow.
`absent` means the local did not exist in that version, not numerical zero.

| Captured local | Before | After |
|---|---|---|
| _effective_admitted | 4502 | 4502 |
| _effective_total | 4502 | 4502 |
| p_compute_demand_mw | 47.64044579999999 | 47.64044579999999 |
| p_cooling_demand_mw | 10.661497999295522 | 10.661497999295522 |
| p_demand_mw | 58.30194379929551 | 58.30194379929551 |
| p_renewable_mw | 0 | 0 |
| _p_renewable_curtailed_mw | 0.0 | 0.0 |
| p_dispatch_required_mw | 58.30194379929551 | 58.30194379929551 |
| _droop_max_f_err_hz | null | null |
| _p_dispatch_droop_mw | 58.30194379929551 | 58.30194379929551 |
| _droop_correction_mw | 0.0 | 0.0 |
| fuel_cell_output_mw | 0.0 | 0.0 |
| _turbine_must_run_mw | 17.5 | 17.5 |
| _turbine_incremental_available_mw | 32.5 | 5.0 |
| _diesel_loading_bounds | absent | {"gt-spin-01":[8.75,11.25],"gt-spin-02":[8.75,11.25]} |
| _bess_physical_ceilings_mw | [29.0] | [29.0] |
| _bess_normal_dispatch_ceilings_mw | [29.0] | [29.0] |
| _bess_reconciled_reserve_mwh | [1.4583333333333333] | [1.4583333333333333] |
| _bess_power_ceiling_mw | 29.0 | 29.0 |
| _bess_energy_ceiling_mw | 38142.25771686377 | 38142.25771686377 |
| _physical_ceiling_mw | 29.0 | 29.0 |
| _bess_available_mw | 29.0 | 29.0 |
| _diesel_dispatch_floor_mw | absent | 0.0 |
| _diesel_dispatch_headroom_mw | absent | 0.0 |
| _allocation_demand_mw | absent | 58.30194379929551 |
| _economic_demand_mw | 40.80194379929551 | 40.80194379929551 |
| _economic_allocations | {"bess-fleet":29.0,"turbine-fleet":11.801943799295508,"fuel-cell-fleet":0.0} | {"bess-fleet":29.0,"turbine-fleet":5.0,"fuel-cell-fleet":0.0,"diesel-fleet":0.0} |
| _diesel_dispatch_target_mw | absent | 0.0 |
| _diesel_extra_mw | absent | 0.0 |
| _planned_bess_setpoint_mw | 29.0 | 29.0 |
| _thermal_dispatch_target_mw | 29.301943799295508 | 22.5 |
| _p_sync_fleet_mw | 29.301943799295508 | 22.5 |
| _reserve_bess_ceilings_mw | [0.0] | [0.0] |
| _physical_bess_shortfall_mw | 38.30194379929551 | 35.80194379929551 |
| _emergency_release_authorized | false | false |
| _emergency_bess_target_mw | 0.0 | 0.0 |
| _bess_dispatch_ceilings_mw | [29.0] | [29.0] |
| _effective_bess_setpoint_mw | 29.0 | 29.0 |
| _bess_soc_floors_mwh | [1.4583333333333333] | [1.4583333333333333] |
| turbine_output_mw | 20.0 | 22.5 |
| bess_output_mw | 29.0 | 29.0 |
| _bess_setpoint_mw | 29.0 | 29.0 |

The residual identities at this tick are:
`58.30194379929551 − 20.0 − 29.0 − 0.0 = 9.301943799295508`
versus
`58.30194379929551 − 22.5 − 29.0 − 0.0 = 6.801943799295508`.
Thus non-diesel delivery is NOT unchanged by the existing D10 implementation,
even while diesel's allocation, minimum and headroom at this tick are all 0.0.
Current P/core/simulation_core.py:1696–1728 installs turbine output/ramp bounds
whenever the diesel fleet is configured, :1808–1814 allocates against them and
:1869–1872 passes those bounds to apply_loading. Before 01ce053, loading is at
:1781–1783 without output_bounds. These are existing D10 changes, not additional
changes made in this resumption. No turbine-loading repair was attempted.

### START-list instrumentation limitation

The diagnostic's START detector compared enum `.value` against uppercase
`"STARTING"`; actual captured values are lowercase `"starting"`. Consequently
the empty `starts` arrays and `start_ticks_identical=true` fields in
T/G1_gate.json are INVALID as complete START evidence. They must not be used
to claim that neither version started diesel or that all START ticks match.
The captured first-difference states directly prove a start on tick 66 in both
versions. Complete START lists are NOT certified by this run. No rerun was
started after the independent, valid gap-equality STOP result.
Before the completed pair, an initial scratch instrument used the nonexistent
SimClock.tick_index and stopped before appending a tick; it was corrected to
SimulationState.tick_index+1. Those failed instrumentation attempts are not
scenario results. The gap and physical-hash measurements in the completed pair
do not use the faulty START-string detector.

## Second resumption — STOP consequences / uncompleted work

- G1 all-scenario residual equality FAILED on the first scenario compared.
  No G1 acceptance result is claimed for H1/H2, SJ-1, islanded-ramp, S10,
  turbine-01, hybrid, fc-bess-diesel, fc100-v2, zero-hot-v2 or Slurm GPU-peaks.
- R3 tests and before/after failure-signature classifications were not run.
- 2d.5 remaining H/no-diesel checks, base-demo A/B acceptance, app-versus-harness
  comparisons and five-diesel metric comparisons were not run.
- 2d.6 full suite was not started. Counts, added/removed/remaining and a new
  failing-ID list are NOT available; PHASE_2D_FAILING_TESTS.txt was not invented.
- ebf2ea987b89b9f55c6c19ddc24cad3970c7de9b remains an unvalidated automatic
  implementation checkpoint.
- G2 alone is committed as c9c4f2e694dc267da456e4f1c971ff660b196a74.
  The G1 production diff remains UNCOMMITTED and UNVALIDATED. No commit with
  the requested “START timing preserved” message was made because that claim
  has not passed its gate.
- A report-only commit records this report and the superseded gap-approval
  scope note; its hash and final git status are printed in the final response.

Storage: initial /tmp 2.8M used / 4.0G; after diagnostic pair 253M / 4.0G,
7% used, 3.8G available. Two scratch worktrees are approximately 125M each.
find T -type f -size +200000000c returned no paths. Child gap rows were consumed
in memory; physical ticks went directly into SHA-256 and counters, not files.
Saved scratch files: T/gap_gate.py, T/G1_gate.json, T/G2_tracking.json,
and the complete T/PHASE_2D_REPORT.md copy. No full tick export was written.
No numerical runtime constant was added.

---

# Historical report preserved below — prior resumption, superseded status

# DR-2026-10-20-ISLAND-COLLAPSE — Phase 2d resumed R0–R2 STOP report
**STATUS: STOPPED at 2d.R2. NOT FINISHED.**
The current implementation changes accepted diesel START timing in scenario-fc100-islanded-v2: before = no starts over 264 ticks; after = diesel-000 starts at tick 1, decision time 0.0 s, tick time 5.0 s. Therefore the user's explicit START-timing STOP gate applies. No repair was attempted; R3, the remaining 2d.5 runs and 2d.6 suite were not started in this resumption.
Package alias P = `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`. Scratch alias T = `/tmp/DR-ISL-phase2d/`.
Implementation remains automatic checkpoint ebf2ea987b89b9f55c6c19ddc24cad3970c7de9b (not validated). The only subsequent test-file commit is the authorized content-preserving tracking commit below. No application/config/scenario/test content or baseline-runner content was edited in this resumption. No workflow restart, publish, deployment, push or Phase 3.
## 2d.R0 — storage
Initial measured df -h:

```
Filesystem      Size Used Avail Use% Mounted on
tmpfs           4.0G 2.0G  2.1G  50% /tmp
/dev/vdd        256G 2.6G  252G   2% /home/runner/workspace
```
Initial requested du top-20 (literal sizes/paths from the first storage inspection):

```
24K /tmp/kube_debug_run-097f4e19c6a4.csv
24K /tmp/kube_debug_run-2a4fb8a0167f.csv
24K /tmp/kube_debug_run-4d5e3bedda73.csv
24K /tmp/kube_debug_run-613c1ed74628.csv
24K /tmp/kube_debug_run-65cad257b58a.csv
24K /tmp/kube_debug_run-876d175b61ae.csv
24K /tmp/kube_debug_run-b4f8d0e336e5.csv
24K /tmp/kube_debug_run-d18715d15f9b.csv
24K /tmp/kube_debug_scenario-equinix-sj-1.csv
24K /tmp/kube_debug_scenario-turbine-01.csv
24K /tmp/kube_debug_sj1-three-deficit-peaks.csv
48K /tmp/kube_debug_scenario-uneven-multisched-01.csv
68K /tmp/kube_debug_demo-islanded-ramp.csv
148K /tmp/logs
1.2M /tmp/DR-ISL-phase1e
1.3M /tmp/shell-exec-output
2.8M /tmp/node-compile-cache
72M /tmp/cmt001_diag.log
332M /tmp/DR-ISL-phase2d
1.6G /tmp/DR-ISL-phase2c
```
Deleted only existing programme full-tick export files under /tmp/DR-ISL-phase*: .ticks.jsonl, .ticks.jsonl.gz, .physical.jsonl.gz, .all-ticks.csv. No external scratch, scenario source or application file was deleted. Every matched *_REPORT.md retained the same SHA-256 at cleanup.
- Removed file-content bytes: **1549429552** across **42** files.
- Actual /tmp allocation freed: **1,549,516,800 bytes** (2,121,764,864 used before; 572,248,064 immediately after). File bytes and allocation differ due to filesystem blocks.
- Preserved report files at cleanup: **12**; report_hashes_unchanged = **true**. Updating this report is intentional; the previous ENOSPC report is preserved verbatim at T/PHASE_2D_STOP3_REPORT.md and in the historical appendix below.
- Complete removal manifest, before/after df -B1 and report hashes: T/R0-cleanup.json:1 onward.
Storage at report generation:

```
Filesystem      Size  Used Avail Use% Mounted on
tmpfs           4.0G  547M  3.5G  14% /tmp
/dev/vdd        256G  2.6G  252G   2% /home/runner/workspace
```

```
24K	/tmp/kube_debug_run-097f4e19c6a4.csv
24K	/tmp/kube_debug_run-2a4fb8a0167f.csv
24K	/tmp/kube_debug_run-4d5e3bedda73.csv
24K	/tmp/kube_debug_run-613c1ed74628.csv
24K	/tmp/kube_debug_run-65cad257b58a.csv
24K	/tmp/kube_debug_run-876d175b61ae.csv
24K	/tmp/kube_debug_run-b4f8d0e336e5.csv
24K	/tmp/kube_debug_run-d18715d15f9b.csv
24K	/tmp/kube_debug_scenario-equinix-sj-1.csv
24K	/tmp/kube_debug_scenario-turbine-01.csv
24K	/tmp/kube_debug_sj1-three-deficit-peaks.csv
48K	/tmp/kube_debug_scenario-uneven-multisched-01.csv
68K	/tmp/kube_debug_demo-islanded-ramp.csv
148K	/tmp/logs
1.2M	/tmp/DR-ISL-phase1e
1.4M	/tmp/shell-exec-output
2.8M	/tmp/node-compile-cache
73M	/tmp/cmt001_diag.log
193M	/tmp/DR-ISL-phase2c
276M	/tmp/DR-ISL-phase2d
```
Files > 200,000,000 bytes under programme scratch: **[]**. T/R0-final-storage.json records this inventory.
New run scripts set RLIMIT_FSIZE = 200,000,000 bytes. They stream physical hashes; no new full physical/compact tick exports were written. Only summaries, event lists, hashes and the specific base start windows were saved. The harness artifact writer and cache persistence were output-only intercepted in scratch; engine inputs and step code were unchanged.
## 2d.R1 — programme tracking
Tracking-only commit: **3c0d0186973cc1a9c0ed0a747be130b69014a962**
Message: "DR-ISL: track programme files under ignored attached_assets/ (no content change)".
Only tests/test_dr_isl_diesel_dispatch.py was force-added. It already existed; its 5,108 bytes were not edited. Before/on-disk/committed SHA-256 all equal **a0c678792c08fc7ebc228bcd12ce3d6bb0cf7508fa19aa1a21ac7bf301ef090e**. .gitignore was not changed.
Inventory includes every explicitly named file plus every added path from git log 55b2184..ebf2ea9. Literal git ls-files --error-unmatch exit status before/after:
| File | Bytes before | Before exit | After exit |
|---|---:|---:|---:|
| .agents/memory/diesel-dispatch-scope.md | 1482 | 0 | 0 |
| .agents/memory/headless-export-storage.md | 1028 | 0 | 0 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py | 1669 | 0 | 0 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_diesel_dispatch.py | 5108 | 1 | 0 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2b.py | 2226 | 0 | 0 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py | 3550 | 0 | 0 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_isl_factory_regression.py | 2482 | 0 | 0 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_isl_grid_forming_viability.py | 4441 | 0 | 0 |
| tools/dr_isl/H_IDENTITY_MAP_D9c.md | 1865 | 0 | 0 |
| tools/dr_isl/PHASE_1C_REPORT.md | 83958 | 0 | 0 |
| tools/dr_isl/PHASE_1D_REPORT.md | 1709886 | 0 | 0 |
| tools/dr_isl/PHASE_1E_REPORT.md | 346799 | 0 | 0 |
| tools/dr_isl/PHASE_2B_REPORT.md | 213516 | 0 | 0 |
| tools/dr_isl/PHASE_2C_FAILING_TESTS.txt | 1448 | 0 | 0 |
| tools/dr_isl/PHASE_2C_REPORT.md | 236069 | 0 | 0 |
| tools/dr_isl/PHASE_2C_STOP1_REPORT.md | 7231 | 0 | 0 |
| tools/dr_isl/PHASE_2D_REPORT.md | 53568 | 0 | 0 |
| tools/dr_isl/baseline_runner.py | 8128 | 0 | 0 |
Exit 0 = tracked; exit 1 = untracked. Full commands/stdout/stderr are retained in T/R1-tracking-before.json; post-tracking statuses in T/R1-tracking-after.json.
### Six unversioned runtime/catalogue support inputs — REPORT ONLY
The Phase 1d /tmp checkout no longer exists and its saved report does not enumerate a six-file copy manifest. Therefore a historical claim about exactly which copies it made cannot be independently verified. The six current runtime/catalogue inputs below are verified on disk, are present in the retained Phase 2d scratch-copy manifest, and are consumed by tracked code. They were NOT added or changed.
| File under P | Bytes | ls-files exit | Tracked consumer under P | Use |
|---|---:|---:|---|---|
| runtime/reference_forecast.py | 736 | 1 | api/routes/reference_forecast.py:12 | Python import |
| runtime/fuel_cell_defaults.py | 181 | 1 | api/schemas.py:25 | Python import |
| core/infrastructure_admission.py | 30829 | 1 | core/ray_cluster_engine.py:16 | Python import |
| config/scenarios/S10_mit_supercloud_2021-08-11.json | 151176 | 1 | api/routes/scenarios.py:1436 | catalogue data load, not a Python import |
| config/scenarios/scenario-100mw-fuel-cell-bess-diesel.json | 23262 | 1 | api/routes/scenarios.py:1411 | catalogue data load, not a Python import |
| config/scenarios/scenario-kubernetes-scheduler-demo.json | 2442 | 1 | api/routes/scenarios.py:1396 | catalogue data load, not a Python import |
Full status/size/hash evidence: T/R1-unversioned-support.json. JSON assets are loaded by the catalogue, not imported as Python modules. No assertion is made that these are all ignored files in the repository; ignored tests/monitor scripts also exist.
## 2d.R2 — literal signal change and approval
Before (01ce053, P/core/simulation_core.py:1956–1967):

```python
_gap_before_diesel_mw = max(
    0.0,
    p_dispatch_required_mw
    - turbine_output_mw
    - bess_output_mw
    - fuel_cell_output_mw,
)
_diesel_snapshot = state.diesel_fleet_coordinator.step(
    gap_mw=_gap_before_diesel_mw if diesel_enabled else 0.0,
    sim_time=sim_time,
    dt_seconds=dt_seconds,
)
```
After (ebf2ea9/current P/core/simulation_core.py:1790–1801):

```python
state.diesel_fleet_coordinator.advance_units(
    sim_time, dt_seconds, dispatch_controlled=True,
)
_diesel_control_gap_mw = max(
    0.0, p_dispatch_required_mw - fuel_cell_output_mw
    - _turbine_must_run_mw - _turbine_incremental_available_mw
    - _bess_available_mw,
)
state.diesel_fleet_coordinator.step(
    gap_mw=_diesel_control_gap_mw, sim_time=sim_time,
    dt_seconds=dt_seconds, advance_units=False, consume_fuel=False,
)
```
The old value is a measured-primary residual after arbitration; the new value is a feasible-primary-capacity residual before the shared allocation. It is supplied when the coordinator is idle as well as when diesel is already operating (P/core/simulation_core.py:1785–1801).
Approval was supplied by the user in this conversation under Lloyd's Phase 2d authorization. Literal question/answer:

```
Question: "May I amend the coordinator’s gap signal for unified dispatch?"
Answer: "Authorize a dispatch-aware gap signal (recommended)"
```
Unloading question/answer:

```
Question: "How should the 30% minimum apply during unloading?"
Answer: "Allow the existing unloading ramp below 30% (recommended)"
```
This did not authorize changed diesel START timing. The resumed prompt explicitly requires STOP if that timing changes.
The episode-creation predicate remains `gap_mw > 0.0 and self._positive_gap_s >= self.debounce_s and math.isnan(self._cooldown_until_s)`: before P/core/diesel_fleet.py:208–214; after :211–217. The positive-gap accumulator remains before :203–206 / after :206–209; actual start dispatch is before :219–227 / after :222–231. The gap INPUT changed, so preserving the Boolean predicate and timers is not sufficient to preserve starts.
### Base-demo START ticks — unchanged
Before: retained Phase 2c actual-harness diesel-diagnosis/{baseline,informed}.events.json; new runs use the actual current _expanded_spec/_probe/_run_mode path, seed 42, no overrides/reuse_cache false. Fabric 1729, wall clock 1792454400.0, Python/NumPy 1729. Historical identity metadata remains pinned to 869d55b exactly as in Phase 2c; this is not a claim that the source is that commit.
| Arm | Before accepted start ticks | After accepted start ticks | Decision seconds | Tick seconds |
|---|---|---|---|---|
| baseline | [66, 371] | [66, 371] | [325.0, 1850.0] | [330.0, 1855.0] |
| informed | [68, 371] | [68, 371] | [335.0, 1850.0] | [340.0, 1855.0] |
Each new base arm completed 1,440 ticks; balance-failure set = []. This was a START-gate diagnosis, not completion of 2d.5's twice-each acceptance. Summaries/physical hashes/inputs for ticks 63–71 are in T/R2-baseline.json and T/R2-informed.json; T/R2-gate.log prints the start values.
### Counterexample — STOP
scenario-fc100-islanded-v2, same pinned seeder path and RunManager, streaming sink:
| Version | Ticks | Accepted diesel starts | Balance failures | Physical SHA-256 |
|---|---:|---|---|---|
| Before, bb59f6e scratch source | 264 | [] | [] | d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3 |
| After, current source | 264 | tick 1, diesel-000, decision 0.0 s, tick time 5.0 s | [] | 13b57633b67326d84dbfc61087caab28eeb7bfe8b2f9b761b75af6fd863dd8da |
The complete tracked package diff 01ce053..bb59f6e is empty (0 bytes); the scratch pre-change application is therefore the Phase 2c implementation. Its streaming physical hash also matches the independently retained pre-change baseline summary. Required unversioned support inputs were supplied in scratch, not added to Git.
Literal complete streamed results:

```json
{
  "scenario": "scenario-fc100-islanded-v2",
  "stage": "before",
  "ticks": 264,
  "physical_sha256": "d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3",
  "balance_failures": [],
  "starts": []
}
```

```json
{
  "scenario": "scenario-fc100-islanded-v2",
  "stage": "after",
  "ticks": 264,
  "physical_sha256": "13b57633b67326d84dbfc61087caab28eeb7bfe8b2f9b761b75af6fd863dd8da",
  "balance_failures": [],
  "starts": [
    {
      "unit": "diesel-000",
      "decision_sim_time": 0.0,
      "from": "offline",
      "to": "starting",
      "tick": 1,
      "sim_time": 5.0
    }
  ]
}
```
Evidence: T/R2-before-scenario-fc100-islanded-v2.json and T/R2-after-scenario-fc100-islanded-v2.json; runner adapter T/resume_stream_start.py. These runs collected no full tick files and used the persisted baseline runner's unchanged pin_spec/plain/encoded/hash exclusions, ScenarioSpec model_validate_json/model_dump, factory and RunManager path.
**R2 verdict: FAIL — actual START timing is not preserved. STOP applies even though the base-demo START ticks match. No START-trigger/timing fix was attempted.**
## 2d.R3 and remaining 2d.5–2d.7
- R3 failure-signature comparison/test updates: NOT STARTED after this gate. No existing test assertion was changed.
- Remaining H/no-diesel comparisons, base-demo twice-each acceptance, app-vs-harness and five-diesel full metric comparisons: NOT CONTINUED. Earlier partial evidence is preserved in the historical appendix, not relabeled complete.
- Full suite: NOT RUN in this resumption. Earlier attempt was incomplete/0-byte JUnit. No final counts or added/removed/remaining set difference is available; no PHASE_2D_FAILING_TESTS.txt was fabricated.
- Implementation checkpoint ebf2ea9 remains NOT VALIDATED. Tracking commit 3c0d0186973cc1a9c0ed0a747be130b69014a962 adds only the previously existing test. A separate documentation-only commit will record this report and two project-memory scope notes; its hash is given in the final response.
- Project-memory notes clarify the user's 200 MB streaming rule and actual START-neutrality constraint; they are documentation, not a new runtime behavior or fix.
- No publish/deploy/push/Phase 3. No new run was started after the counterexample was returned.
## Retained evidence / source content checks
Current baseline runner SHA-256: 12320f7c74c42406cc6eca862b9621621f733c2d9ad94e3ecb0c80652af6593a
Runtime/config/scenario source diff ebf2ea9..tracking HEAD:

```json
{
  "command": [
    "git",
    "diff",
    "--stat",
    "ebf2ea9..HEAD",
    "--",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config"
  ],
  "exit": 0,
  "stdout": "",
  "stderr": ""
}
```
New ignored test was tracked unchanged (1–120); no further test-code delta. Report line range and the two memory-note ranges are listed in the final response. Source/historical full implementation diff is retained below.
## Historical ENOSPC STOP report — verbatim, superseded status
The following is the preserved prior report. Its bb59f6e/uncommitted statements describe that earlier instant and are NOT current Git status. Current checkpoint/tracking state and current R2 STOP are above.
# DR-2026-10-20-ISLAND-COLLAPSE — Phase 2d STOP report
**STOPPED, NOT FINISHED: scratch filesystem exhausted (ENOSPC).**
Implementation commit: NONE. Current HEAD: `bb59f6eeccf6456c0bf838d4ee6331c0fc0524dd`.
No new tests or simulations were started after the storage failure. No implementation commit, workflow restart, publish, deploy or push. Phase 3 was not started.
The previous coordinator-gap STOP report is preserved as `/tmp/DR-ISL-phase2d/PHASE_2D_STOP2_REPORT.md` and in commit bb59f6e. This report supersedes its status.
## Stop condition and cleanup
Printed filesystem values at failure:

```
Filesystem      Size  Used Avail Use% Mounted on
tmpfs           4.0G  4.0G     0 100% /tmp
/dev/vdd        256G  2.6G  252G   2% /home/runner/workspace
```
The report-file write failed with the literal tool error `ENOSPC: no space left on device, write`.
Observed background exits: diesel checks tMmXUVGg = 120; H/no-diesel/base sequence N8QT3Ai9 = -1; full suite aYwveBkE = 120. These are incomplete verification processes, not successful scenario or suite results.
Only the following generated, incomplete export was removed to restore scratch capacity. Its size/hash were recorded BEFORE removal:

```json
{
  "path": "/tmp/DR-ISL-phase2d/before/islanded-fc-bess-diesel-slurm-gpu-peaks.1.ticks.jsonl",
  "bytes": 2173403136,
  "sha256_partial_file": "6822e5c5d6e461a68262b5a64c36ff6611e15180584c310f46ac382cf450be76",
  "complete_lines": 840,
  "status": "incomplete export, removed to restore scratch capacity; not a simulation result"
}
```
The 840 LF-terminated records in that partial export are NOT a finalized simulation tick count or a validated physical hash. No completed Slurm GPU-peaks baseline result is claimed.
After removing it, the printed /tmp values were 4.0G total, 2.0G used, 2.1G available, 50% used. Application data and the other scratch evidence were retained.
## 2d.0 design note
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py:1448–1547: optional controlled advance separates physical startup capability from dispatched output; dispatch bounds and target application are on DieselModule.
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:777–860,1696–1885,2065–2076: diesel enters the existing merit allocator, its current delivery is credited to primary/BESS demand, and achieved dispatch is used for fuel accounting.
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py:114–123,180–263,375–400: the coordinator owns lifecycle decisions, on-bus rollup and the fuel curve.
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:830–846: PROPOSED_HERE infinity is the diesel ranking-only fallback, not a monetary price. The generic allocator ranks BESS, turbine, FC, diesel. In the live call, existing measured FC delivery is still netted before the allocation (fuel_cell_available_mw=0.0); that existing policy was not changed. The complete source hunk is below.
The user approved two explicit exceptions: (1) the 30% bound is SYNCHRONISED-only; UNLOADING may ramp below it; (2) the coordinator may use primary feasible supply, respecting ramp/policy/AC-energy bounds, rather than a residual that includes primary MW displaced by the diesel minimum.
## 2d.1–2d.3 implementation state: working tree only, not accepted by all gates
- D10: attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py:1526–1554; attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:1696–1885. Synchronized minimum = 0.30 × rated; UNLOADING remains its existing physical tail. The comment identifies NFPA 110 §8.4.2/Annex A as a monthly-test-load proxy, NOT a continuous-operation requirement.
- Dispatch-aware gap: attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:1783–1802. It uses existing BESS AC ceilings and ramp/policy-bounded primary capacity; no second diesel dispatch loop.
- IMPL-ISL-14: attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py:114–123,384–400: on-bus UNLOADING power and fuel counted. Fuel remains proportional to delivered load fraction; no no-load term was added.
- IMPL-ISL-15: attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py:230–260: a refused stop resets the hold; completion requires each unloading unit's configured cooldown/ramp duration to have elapsed.
No scenario JSON, commitment, reserve-floor formula, frequency/protection code, configured diesel timing value or authority tier was edited. Exact production/test diff follows in the appendix.
## 2d.4 tests — completed targeted evidence
Assigned IDs: TC-ISL-19,20,21,22. Case-insensitive search for those IDs outside the new test file returned no matches.
/tmp/DR-ISL-phase2d/final-new-tests.log:1–2:

```
....                                                                     [100%]
4 passed in 0.75s
```
Asserted values in attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_diesel_dispatch.py: minimum 6.0 MW for a 20 MW synchronized unit; UNLOADING 5.9 MW remains counted with fuel; refused-stop hold 0.0; unloading retains its 300 s ramp; final state OFFLINE/output 0.0. TC-ISL-20 additionally covers an unloading resume and policy-held GT capacity.
The broader targeted check (before the final explicit-target edge assertion was added) was 54 passed / 2 failed. The final new-test check above includes that assertion. Full literal targeted output:

```
.............F...............F..........................                 [100%]
=================================== FAILURES ===================================
_____ test_live_diesel_is_less_aggressive_than_disabled_before_curtailment _____
tests/test_diesel_phase3.py:189: in test_live_diesel_is_less_aggressive_than_disabled_before_curtailment
    assert disabled_tiers
E   assert ()
___________ test_hybrid_covered_demand_does_not_release_bess_reserve ___________
tests/test_diesel_setpoint_gap.py:134: in test_hybrid_covered_demand_does_not_release_bess_reserve
    assert result_480.fuel_cell_output_mw + result_480.diesel_output_mw > (
E   AssertionError: assert (59.600000000000136 + 39.99227768757201) > 99.59227768757215
E    +  where 59.600000000000136 = TickResult(run_id='diesel-setpoint-gap-regression', tick_index=96, sim_time_seconds=480.0, p_compute_demand_mw=82.9935...tisfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id=None, slurm_metrics=None).fuel_cell_output_mw
E    +  and   39.99227768757201 = TickResult(run_id='diesel-setpoint-gap-regression', tick_index=96, sim_time_seconds=480.0, p_compute_demand_mw=82.9935...tisfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id=None, slurm_metrics=None).diesel_output_mw
E    +  and   99.59227768757215 = TickResult(run_id='diesel-setpoint-gap-regression', tick_index=96, sim_time_seconds=480.0, p_compute_demand_mw=82.9935...tisfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id=None, slurm_metrics=None).net_demand_mw
=========================== short test summary info ============================
FAILED tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment
FAILED tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve
2 failed, 54 passed in 2.14s
```
The two failing NODE IDs are in tools/dr_isl/PHASE_2C_FAILING_TESTS.txt. This does not assert that every failure signature is unchanged; their literal assertions are reproduced above.
Only two existing tests were edited, both in attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py: fixed-block diesel MW and additive-generation/residual assertions were replaced with D10 minimum/actual-source-accounting assertions and comments. No other existing test was edited.
## 2d.5 scenario evidence — incomplete
### Completed H checks
Sources: /tmp/DR-ISL-phase2d/H-after.log:1–6 and each named metrics/compact-hash JSON file:1. Comparisons below are read-only rechecks of retained files, not new runs.
| Scenario | Mode | Rep | Ticks | Curtailment MWh | Balance failures | Metrics equal Phase 2c | Compact equal Phase 2c |
|---|---|---:|---:|---:|---:|---|---|
| scenario-h1-k8s-ray-24h | baseline | 1 | 17280 | 187.690139189 | 0 | True | True |
| scenario-h1-k8s-ray-24h | informed | 1 | 17280 | 176.779572526 | 0 | True | True |
| scenario-h1-k8s-ray-24h | baseline | 2 | 17280 | 187.690139189 | 0 | True | True |
| scenario-h1-k8s-ray-24h | informed | 2 | 17280 | 176.779572526 | 0 | True | True |
| scenario-h2-slurm-24h | baseline | 1 | 17280 | 349.917690813 | 0 | True | True |
| scenario-h2-slurm-24h | informed | 1 | 17280 | 343.106291593 | 0 | True | True |

Full printed H rows, including physical and compact hashes:

```json
{"scenario": "scenario-h1-k8s-ray-24h", "mode": "baseline", "repetition": 1, "status": "PASS", "curtailment": 187.690139189, "physical_sha256": "57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b", "balance_failures": 0, "compact": {"sha256": "e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755", "tick_count": 17280}}
{"scenario": "scenario-h1-k8s-ray-24h", "mode": "informed", "repetition": 1, "status": "PASS", "curtailment": 176.779572526, "physical_sha256": "60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9", "balance_failures": 0, "compact": {"sha256": "19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2", "tick_count": 17280}}
{"scenario": "scenario-h1-k8s-ray-24h", "mode": "baseline", "repetition": 2, "status": "PASS", "curtailment": 187.690139189, "physical_sha256": "57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b", "balance_failures": 0, "compact": {"sha256": "e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755", "tick_count": 17280}}
{"scenario": "scenario-h1-k8s-ray-24h", "mode": "informed", "repetition": 2, "status": "PASS", "curtailment": 176.779572526, "physical_sha256": "60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9", "balance_failures": 0, "compact": {"sha256": "19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2", "tick_count": 17280}}
{"scenario": "scenario-h2-slurm-24h", "mode": "baseline", "repetition": 1, "status": "FAIL", "curtailment": 349.917690813, "physical_sha256": "f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1", "balance_failures": 0, "compact": {"sha256": "8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66", "tick_count": 17280}}
{"scenario": "scenario-h2-slurm-24h", "mode": "informed", "repetition": 1, "status": "PASS", "curtailment": 343.106291593, "physical_sha256": "3b40147d28ee89f1ec312b7f57f1c9f77e82c99bd7e6ee4447ff5384f951dbdf", "balance_failures": 0, "compact": {"sha256": "6ae0ce3d7a1b300cd4402fbd640abc67addb953b453075454c39bdefad8b0711", "tick_count": 17280}}
```
H1 both arms/repetitions completed and matched. H2 has only repetition 1 completed for both arms; repetition 2 was not finalized. H2 baseline status FAIL is preserved rather than relabeled PASS; the comparison to Phase 2c is exact in its completed record.
### Pre-change diesel baselines
Built from the immutable bb59f6e scratch worktree, with missing ignored source inputs copied separately (inventory: /tmp/DR-ISL-phase2d/before-ignored-source-copies.json). No tracked pre-change implementation file was overwritten. Runner file unchanged.
| Scenario | Rep | Ticks | Physical SHA-256 | Balance failures |
|---|---:|---:|---|---:|
| scenario-100mw-fuel-cell-bess-diesel | 1 | 252 | 565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b | 0 |
| scenario-100mw-fuel-cell-bess-diesel | 2 | 252 | 565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b | 0 |
| scenario-fc100-islanded-v2 | 1 | 264 | d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3 | 0 |
| scenario-fc100-islanded-v2 | 2 | 264 | d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3 | 0 |
| scenario-fc100-islanded-zero-hot-v2 | 1 | 264 | d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2 | 0 |
| scenario-fc100-islanded-zero-hot-v2 | 2 | 264 | d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2 | 0 |
| scenario-hybrid-ai-100mw-addendum-i | 1 | 120 | 4e9c1a040eeaa4952600225cef71fa7ab8088419a916184bad09ba45bc8bc518 | 0 |
| scenario-hybrid-ai-100mw-addendum-i | 2 | 120 | 4e9c1a040eeaa4952600225cef71fa7ab8088419a916184bad09ba45bc8bc518 | 0 |

### Pending / unavailable
- No-diesel after-change gate: NOT COMPLETED (the H sequence failed before it).
- Base-demo harness A/B, all requested fuel components/start timelines/SoC/refusals/forecast misses/comparison verdict: NOT RUN in this resumed verification sequence.
- Base-demo app-path comparison: NOT RUN.
- Diesel after-change metrics/hashes: NOT RUN; the large pre-change Slurm baseline did not finalize.
- Therefore no final before/after delta, app=harness verdict, or complete 2d.5 acceptance is claimed.
## 2d.6 full suite — NOT COMPLETED
Full-suite process exited 120 during scratch exhaustion. /tmp/DR-ISL-phase2d/full-suite.xml is 0 bytes. No reliable final pass/fail counts, added/removed/remaining set comparison, or final Phase 2d failing-ID list exists. Do not treat incomplete progress marks as counts.
Tail of /tmp/DR-ISL-phase2d/full-suite.log (the traceback itself was truncated by the write failure):

```

Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/pytest/__main__.py", line 9, in <module>
    raise SystemExit(_console_main())
                     ~~~~~~~~~~~~~^^
  File "/home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/_pytest/config/__init__.py", line 253, in _console_main
    code = _main(prog=_get_prog_name(sys.argv))
  File "/home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/_pytest/config/__init__.py", line 229, in _main
    ret: ExitCode | int = config.hook.pytest_cmdline_main(config=config)
                          ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^
  File "/home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
           ~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/workspace/.pythonlibs/lib/python3.1
```
Known Phase 2c failures, for reference ONLY (not a Phase 2d result):

```
tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation
tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config
tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar
tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment
tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve
tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names
tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel
tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited
tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context
tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants
tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude
tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait
tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes
tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load
tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip
```
## 2d.7 commits and changed files
No implementation or completion-report commit was made in this resumed attempt. Changes remain uncommitted; the implementation is not declared ready. Current HEAD is bb59f6eeccf6456c0bf838d4ee6331c0fc0524dd.
| File | Changed/new line ranges |
|---|---|
| .agents/memory/MEMORY.md | 71–71 |
| .agents/memory/diesel-dispatch-scope.md | 11–16 |
| .agents/memory/headless-export-storage.md | 1–10 (new) |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py | 1360–1360, 1448–1448, 1468–1468, 1475–1475, 1502–1506, 1525–1553, 1575–1577 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py | 115–115, 120–120, 187–188, 200–203, 233–233, 235–239, 241–242, 247–250, 375–383, 390–390 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py | 36–37, 69–74, 107–107, 122–122, 146–153, 158–159, 170–172, 174–174, 203–203 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py | 42–42 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py | 32–35, 786–786, 830–845, 852–852, 1696–1733, 1783–1812, 1815–1815, 1818–1818, 1820–1820, 1826–1826, 1828–1836, 1849–1849, 1883–1884, 1988–1988, 1990–1990, 2011–2011, 2051–2051, 2068–2074 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py | 138–142, 165–168, 170–173, 175–176 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_diesel_dispatch.py | 1–120 (new) |
| tools/dr_isl/PHASE_2D_REPORT.md | 1–882 |

## Full literal production and test diff

```diff
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
index 59a2f49..1b2b974 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
@@ -1357,6 +1357,7 @@ class DieselModule(AssetModule):
     _resuming_from_unloading: bool = False
     _resume_start_output_mw: float = 0.0
     _resume_elapsed_s: float = 0.0
+    _dispatch_ceiling_mw: Optional[float] = field(default=None, init=False)
 
     def __post_init__(self) -> None:
         if self.config.rated_mw <= 0.0:
@@ -1444,7 +1445,7 @@ class DieselModule(AssetModule):
         self._current_output_mw = 0.0
         self._resuming_from_unloading = False
 
-    def advance(self, sim_time: float, dt_seconds: float) -> None:
+    def advance(self, sim_time: float, dt_seconds: float, *, dispatch_controlled: bool = False) -> None:
         """Advance startup, synchronization output, or controlled unloading."""
         if dt_seconds < 0.0:
             raise ValueError("diesel dt_seconds must not be negative")
@@ -1464,12 +1465,14 @@ class DieselModule(AssetModule):
                     self._current_output_mw = (
                         self.config.rated_mw * self.config.f_block
                     )
+                    self._dispatch_ceiling_mw = self._current_output_mw
                 else:
                     self.state = DieselState.FAILED_START
                     self._current_output_mw = 0.0
             return
 
         if self.state == DieselState.SYNCHRONISED:
+            _delivered_before_advance = self._current_output_mw
             if self._resuming_from_unloading:
                 self._resume_elapsed_s += dt_seconds
                 duration = self.config.residual_ramp_s
@@ -1496,6 +1499,11 @@ class DieselModule(AssetModule):
                     base_mw
                     + (self.config.rated_mw - base_mw) * fraction
                 )
+            self._dispatch_ceiling_mw = self._current_output_mw
+            if dispatch_controlled:
+                # D10: advance machine capability, not delivered power.  A
+                # subsequent accepted stop must capture actual dispatched MW.
+                self._current_output_mw = _delivered_before_advance
             return
 
         if self.state == DieselState.UNLOADING:
@@ -1514,6 +1522,35 @@ class DieselModule(AssetModule):
     def output_mw(self) -> float:
         return self._current_output_mw
 
+    @property
+    def dispatch_floor_mw(self) -> float:
+        if self.state == DieselState.UNLOADING:
+            # User-approved D10 exception: preserve the tail below 30%.
+            return self.output_mw()
+        if self.state == DieselState.SYNCHRONISED:
+            # PROPOSED_HERE, D10: NFPA 110 §8.4.2 / Annex A test-load
+            # reference, used as a wet-stacking proxy for continuous load;
+            # this is a modelling minimum, not an NFPA run requirement.
+            return 0.30 * self.config.rated_mw
+        return 0.0
+
+    @property
+    def dispatch_ceiling_mw(self) -> float:
+        if self.state != DieselState.SYNCHRONISED:
+            return self.dispatch_floor_mw
+        available = (
+            self.output_mw() if self._dispatch_ceiling_mw is None
+            else self._dispatch_ceiling_mw
+        )
+        return max(self.dispatch_floor_mw, min(self.config.rated_mw, available))
+
+    def apply_dispatch_target(self, target_mw: float) -> None:
+        """D10: sole economic output application; unloading stays physical."""
+        if self.state == DieselState.SYNCHRONISED:
+            self._current_output_mw = max(
+                self.dispatch_floor_mw, min(self.dispatch_ceiling_mw, target_mw),
+            )
+
     def command_stop(self, sim_time: float) -> Optional[str]:
         """Begin controlled unloading, enforcing the diesel minimum run time."""
         self._last_known_sim_time = sim_time
@@ -1535,6 +1572,9 @@ class DieselModule(AssetModule):
         if self.state != DieselState.UNLOADING:
             return
         self.state = DieselState.SYNCHRONISED
+        # D10: resuming exposes the current tail, not a stale pre-unload
+        # capacity. advance() then raises capability on the existing ramp.
+        self._dispatch_ceiling_mw = self._current_output_mw
         self._resuming_from_unloading = True
         self._resume_start_output_mw = self._current_output_mw
         self._resume_elapsed_s = 0.0
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py
index 2a63a3a..5e8e365 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py
@@ -112,12 +112,12 @@ class DieselFleetCoordinator:
 
     @property
     def output_mw(self) -> float:
-        """Aggregate measured output from synchronised diesel units."""
+        """IMPL-ISL-14: aggregate every breaker-closed unit, including unloading."""
         return sum(
             (
                 unit.output_mw()
                 for unit in self.diesel_units
-                if unit.state == DieselState.SYNCHRONISED
+                if unit.is_on_bus
             ),
             0.0,
         )
@@ -184,6 +184,8 @@ class DieselFleetCoordinator:
         dt_seconds: float,
         *,
         success_overrides: Optional[Mapping[str, bool]] = None,
+        advance_units: bool = True,
+        consume_fuel: bool = True,
     ) -> DieselFleetSnapshot:
         """Advance units and coordinate one synthetic-gap fleet tick.
 
@@ -195,9 +197,10 @@ class DieselFleetCoordinator:
             raise ValueError("diesel fleet dt_seconds must not be negative")
         self._last_sim_time = sim_time
 
-        for unit in self.diesel_units:
-            unit.advance(sim_time, dt_seconds)
-        self._consume_fuel(dt_seconds)
+        if advance_units:
+            self.advance_units(sim_time, dt_seconds)
+        if consume_fuel:
+            self._consume_fuel(dt_seconds)
         self._complete_cooldown_if_ready(sim_time)
 
         if gap_mw > 0.0:
@@ -227,15 +230,24 @@ class DieselFleetCoordinator:
                     success_overrides or {},
                 )
         else:
-            if any(unit.state == DieselState.UNLOADING for unit in self.diesel_units):
-                self._restore_elapsed_s += dt_seconds
-            elif any(unit.state == DieselState.SYNCHRONISED for unit in self.diesel_units):
+            if any(unit.state == DieselState.SYNCHRONISED for unit in self.diesel_units):
                 self._begin_unloading(sim_time)
+            # IMPL-ISL-15: a refused stop is not unloading/restoration time.
+            if (
+                any(unit.state == DieselState.UNLOADING for unit in self.diesel_units)
+                and not any(unit.state == DieselState.SYNCHRONISED for unit in self.diesel_units)
+            ):
                 self._restore_elapsed_s += dt_seconds
+            else:
+                self._restore_elapsed_s = 0.0
 
             if (
                 self._restore_elapsed_s >= self.restore_hold_s
                 and any(unit.state == DieselState.UNLOADING for unit in self.diesel_units)
+                and all(
+                    unit._unload_elapsed_s >= unit.config.cooldown_s
+                    for unit in self.diesel_units if unit.state == DieselState.UNLOADING
+                )
             ):
                 self._finish_unloading(sim_time)
 
@@ -360,13 +372,22 @@ class DieselFleetCoordinator:
         self.insufficient_start_alert_fired = False
         self.insufficient_start_alerts.clear()
 
+    def advance_units(self, sim_time: float, dt_seconds: float, *, dispatch_controlled: bool = False) -> None:
+        """Advance lifecycle once; live D10 dispatch separately records delivery."""
+        for unit in self.diesel_units:
+            unit.advance(sim_time, dt_seconds, dispatch_controlled=dispatch_controlled)
+
+    def record_dispatch_fuel(self, dt_seconds: float) -> None:
+        """D10: use this interval's achieved, not pre-allocation, load fraction."""
+        self._consume_fuel(dt_seconds)
+
     def _consume_fuel(self, dt_seconds: float) -> None:
         dt_hours = dt_seconds / 3600.0
         if dt_hours <= 0.0:
             return
         consumed_gal = 0.0
         for unit in self.diesel_units:
-            if unit.state != DieselState.SYNCHRONISED:
+            if not unit.is_on_bus:  # IMPL-ISL-14: the unloading tail burns fuel.
                 continue
             if unit.config.rated_mw <= 0.0:
                 continue
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py
index 587d1d5..fa69800 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py
@@ -33,6 +33,8 @@ if TYPE_CHECKING:
 def compute_loading_setpoints(
     synchronised: "list[TurbineModule]",
     p_fleet: float,
+    *,
+    output_bounds: dict[str, tuple[float, float]] | None = None,
 ) -> tuple[list[float], float]:
     """Compute per-unit setpoints for units in A.  Pure — no side effects.
 
@@ -64,6 +66,12 @@ def compute_loading_setpoints(
         return [0.0] * len(synchronised), 0.0
 
     msl_i = [t.config.p_min_stable_frac * t.config.rated_mw for t in synchronised]
+    ceiling_i = [t.config.rated_mw for t in synchronised]
+    if output_bounds is not None:
+        # D10: the same sequential allocator can use this interval's physical
+        # ramp/policy envelope; no second turbine/diesel loading algorithm.
+        msl_i = [output_bounds[t.config.asset_id][0] for t in synchronised]
+        ceiling_i = [output_bounds[t.config.asset_id][1] for t in synchronised]
     sum_msl = sum(msl_i)
 
     # ── Sub-MSL: feasible band lower bound ───────────────────────────────────
@@ -96,7 +104,7 @@ def compute_loading_setpoints(
     for i, t in enumerate(synchronised):
         if _residual_s < 1e-9:
             break
-        _headroom_i   = t.config.rated_mw - msl_i[i]
+        _headroom_i   = ceiling_i[i] - msl_i[i]
         _fill_i       = min(_residual_s, _headroom_i)
         setpoints[i] += _fill_i
         _residual_s  -= _fill_i
@@ -111,7 +119,7 @@ def compute_loading_setpoints(
         unclamped: list[int] = []
         for i, t in enumerate(synchronised):
             lo = msl_i[i]
-            hi = t.config.rated_mw
+            hi = ceiling_i[i]
             if setpoints[i] < lo - 1e-9:
                 residual += lo - setpoints[i]   # positive: we under-allocated
                 setpoints[i] = lo
@@ -135,10 +143,20 @@ def compute_loading_setpoints(
 # Apply loading to SYNCHRONISED units (has side effects on output_mw)
 # ---------------------------------------------------------------------------
 
+def ramp_limited_output(turbine: "TurbineModule", target_mw: float, dt_seconds: float) -> float:
+    """Pure prediction of the existing loading step, also used to apply it."""
+    delta = target_mw - turbine.output_mw()
+    max_step = turbine.config.r_asset_mw_per_s * dt_seconds
+    step = max(-max_step, min(max_step, delta))
+    return turbine.output_mw() + step
+
+
 def apply_loading(
     synchronised: "list[TurbineModule]",
     p_fleet: float,
     dt_seconds: float,
+    *,
+    output_bounds: dict[str, tuple[float, float]] | None = None,
 ) -> float:
     """Compute setpoints and advance SYNCHRONISED unit outputs toward them.
 
@@ -149,12 +167,11 @@ def apply_loading(
     No stored state — calling twice with the same inputs is idempotent for the
     setpoint computation, though output_mw will advance twice.
     """
-    setpoints, sub_msl_surplus_mw = compute_loading_setpoints(synchronised, p_fleet)
+    setpoints, sub_msl_surplus_mw = compute_loading_setpoints(
+        synchronised, p_fleet, output_bounds=output_bounds,
+    )
     for t, sp in zip(synchronised, setpoints):
-        delta = sp - t.output_mw()
-        max_step = t.config.r_asset_mw_per_s * dt_seconds
-        step = max(-max_step, min(max_step, delta))
-        t.set_output(t.output_mw() + step)
+        t.set_output(ramp_limited_output(t, sp, dt_seconds))
     return sub_msl_surplus_mw
 
 
@@ -183,10 +200,7 @@ def apply_loading_targets(
                 float(targets_mw.get(turbine.config.asset_id, minimum)),
             ),
         )
-        delta = target - turbine.output_mw()
-        max_step = turbine.config.r_asset_mw_per_s * dt_seconds
-        step = max(-max_step, min(max_step, delta))
-        turbine.set_output(turbine.output_mw() + step)
+        turbine.set_output(ramp_limited_output(turbine, target, dt_seconds))
     return sub_msl_surplus_mw
 
 
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py
index 8a7cf6c..adc2ab9 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py
@@ -39,6 +39,7 @@ class PowerSourceType(str, Enum):
     BESS         = "bess"
     TURBINE      = "turbine"
     FUEL_CELL    = "fuel_cell"
+    DIESEL       = "diesel"
 
 
 class AuthorityTier(str, Enum):
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
index d253eb5..9c7e8bb 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -29,7 +29,10 @@ from .asset_modules import (
     TurbineState,
 )
 from .fuel_cell_module import BlockFuelCellFleet, FuelCellModule
-from .loading import apply_loading, apply_loading_targets, ramp_capability
+from .loading import (
+    apply_loading, apply_loading_targets, compute_loading_setpoints,
+    ramp_capability, ramp_limited_output,
+)
 from .contingency import BessSnapshot, FuelCellSnapshot, PlantState, TurbineSnapshot, evaluate_contingency
 from .kube_demand import KubeDemandAgent, KubeGridState
 from .lead_time_observations import LeadTimeObservationRecorder
@@ -780,6 +783,7 @@ def _cost_ranked_dispatch_allocations(
     bess_available_mw: float,
     turbine_available_mw: float,
     fuel_cell_available_mw: float,
+    diesel_available_mw: float = 0.0,
 ) -> dict[str, float]:
     """Allocate discretionary demand using the shared marginal-cost ranking.
 
@@ -823,12 +827,29 @@ def _cost_ranked_dispatch_allocations(
             cost_basis_note="catalogue: fuel_cell_ppa_rate_mwh",
         ),
     ]
+    if diesel_available_mw > 0.0:
+        sources.append(_PowerSource(
+            source_id="diesel-fleet",
+            source_type=_PowerSourceType.DIESEL,
+            dispatchable=True,
+            counts_toward_reserve=True,
+            # PROPOSED_HERE, D10 fallback: no catalogue diesel price exists.
+            # Rank-only infinity (not a fuel price): diesel is last on rise /
+            # first on back-down because diesel fuel/MWh exceeds gas and FC.
+            # Source: approved DR-2026-10-20-ISLAND-COLLAPSE D10.
+            marginal_cost_mwh=math.inf,
+            response_latency_class=_ResponseLatencyClass.RAMP_LIMITED,
+            authority_tier=_AuthorityTier.AUTONOMOUS,
+            available_mw=diesel_available_mw,
+            cost_basis_note="D10: ranking-only last; no catalogue diesel price",
+        ))
     ranked = _PowerRanker().rank(sources).ranked_sources
     remaining_mw = max(0.0, demand_mw)
     allocations = {
         "bess-fleet": 0.0,
         "turbine-fleet": 0.0,
         "fuel-cell-fleet": 0.0,
+        "diesel-fleet": 0.0,
     }
     for source in ranked:
         if remaining_mw <= 1e-9:
@@ -1672,6 +1693,44 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         )
         for t in _truly_sync_units
     )
+    _diesel_loading_bounds = None
+    if state.diesel_units:
+        # D10: one ramp calculation/one sequential loading allocator. Preserve
+        # the existing controller/baseload policy as a physical floor, rather
+        # than allocating diesel against turbine MW already held by that policy.
+        _diesel_loading_bounds = {}
+        _policy_targets = dict(getattr(state, "_preload_targets_mw", {}) or {})
+        _explicit_policy_targets = bool(_policy_targets)
+        if not _policy_targets and _generation_baseload_active:
+            _base_setpoints, _ = compute_loading_setpoints(
+                _truly_sync_units,
+                max(0.0, _generation_baseload_target_mw - _uncontrolled_on_bus_mw - _msl_held_mw),
+            )
+            _policy_targets = {
+                t.config.asset_id: sp for t, sp in zip(_truly_sync_units, _base_setpoints)
+            }
+        for _t in _truly_sync_units:
+            _minimum = _t.config.p_min_stable_frac * _t.config.rated_mw
+            _lo = ramp_limited_output(_t, _minimum, dt_seconds)
+            _hi = ramp_limited_output(_t, _t.config.rated_mw, dt_seconds)
+            if _explicit_policy_targets or _t.config.asset_id in _policy_targets:
+                # apply_loading_targets holds omitted units at minimum too.
+                _target = max(_minimum, min(_t.config.rated_mw, _policy_targets.get(_t.config.asset_id, _minimum)))
+                _lo = ramp_limited_output(_t, _target, dt_seconds)
+                if _explicit_policy_targets or not _generation_peak_following:
+                    _hi = _lo
+            _diesel_loading_bounds[_t.config.asset_id] = (_lo, max(_lo, _hi))
+        _msl_held_mw = sum(
+            ramp_limited_output(t, t.config.p_min_stable_frac * t.config.rated_mw, dt_seconds)
+            for t in _unloading_units
+        )
+        _turbine_must_run_mw = (
+            _uncontrolled_on_bus_mw + _msl_held_mw
+            + sum(bounds[0] for bounds in _diesel_loading_bounds.values())
+        )
+        _turbine_incremental_available_mw = sum(
+            hi - lo for lo, hi in _diesel_loading_bounds.values()
+        )
     # Economic BESS availability must account for both the instantaneous power
     # ceiling and energy that can actually be delivered during this tick.  If
     # only the power ceiling is ranked, an empty/near-empty BESS reserves cheap
@@ -1721,18 +1780,60 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
             min(_physical_ceiling_mw, _normal_energy_ceiling_mw)
         )
     _bess_available_mw = sum(_bess_normal_dispatch_ceilings_mw)
+    _diesel_dispatch_floor_mw = 0.0
+    _diesel_dispatch_headroom_mw = 0.0
+    if state.diesel_units:
+        # Approved D10 signal amendment: primary-only achievable shortfall,
+        # using this allocation's ramp/policy/AC-energy bounds, not the primary
+        # MW displaced by a live diesel minimum. This is a capacity diagnostic,
+        # not a second dispatch. START condition and every timer stay unchanged.
+        state.diesel_fleet_coordinator.advance_units(
+            sim_time, dt_seconds, dispatch_controlled=True,
+        )
+        _diesel_control_gap_mw = max(
+            0.0, p_dispatch_required_mw - fuel_cell_output_mw
+            - _turbine_must_run_mw - _turbine_incremental_available_mw
+            - _bess_available_mw,
+        )
+        state.diesel_fleet_coordinator.step(
+            gap_mw=_diesel_control_gap_mw, sim_time=sim_time,
+            dt_seconds=dt_seconds, advance_units=False, consume_fuel=False,
+        )
+        _diesel_dispatch_floor_mw = sum(t.dispatch_floor_mw for t in state.diesel_units)
+        _diesel_dispatch_headroom_mw = sum(
+            t.dispatch_ceiling_mw - t.dispatch_floor_mw for t in state.diesel_units
+        )
+    # D10: diesel must not be hidden behind the old primary-only dispatch
+    # intent ceiling. Keep the droop/frequency calculation unchanged; the one
+    # allocator's resource envelopes bound the full physical dispatch request.
+    _allocation_demand_mw = (
+        max(0.0, p_dispatch_required_mw + _droop_correction_mw)
+        if state.diesel_units else _p_dispatch_droop_mw
+    )
     _economic_demand_mw = max(
         0.0,
-        _p_dispatch_droop_mw
+        _allocation_demand_mw
         - fuel_cell_output_mw
         - _turbine_must_run_mw,
+        # diesel's synchronized minimum / immutable unloading tail is must-run.
     )
+    _economic_demand_mw = max(0.0, _economic_demand_mw - _diesel_dispatch_floor_mw)
     _economic_allocations = _cost_ranked_dispatch_allocations(
         _economic_demand_mw,
         bess_available_mw=_bess_available_mw,
         turbine_available_mw=_turbine_incremental_available_mw,
         fuel_cell_available_mw=0.0,
-    )
+        diesel_available_mw=_diesel_dispatch_headroom_mw,
+    )
+    _diesel_dispatch_target_mw = _diesel_dispatch_floor_mw + _economic_allocations["diesel-fleet"]
+    _diesel_extra_mw = _economic_allocations["diesel-fleet"]
+    for _diesel in state.diesel_units:
+        _extra = min(
+            _diesel_extra_mw,
+            _diesel.dispatch_ceiling_mw - _diesel.dispatch_floor_mw,
+        )
+        _diesel.apply_dispatch_target(_diesel.dispatch_floor_mw + _extra)
+        _diesel_extra_mw -= _extra
     _planned_bess_setpoint_mw = _economic_allocations["bess-fleet"]
     _thermal_dispatch_target_mw = (
         _turbine_must_run_mw + _economic_allocations["turbine-fleet"]
@@ -1745,7 +1846,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         # replacing conventional turbine generation during a peak.
         _conventional_following_target_mw = max(
             0.0,
-            _p_dispatch_droop_mw - fuel_cell_output_mw,
+            _p_dispatch_droop_mw - fuel_cell_output_mw - _diesel_dispatch_target_mw,
         )
         if _generation_peak_following:
             _thermal_dispatch_target_mw = max(
@@ -1779,7 +1880,8 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         )
     else:
         _sub_msl_surplus_mw = apply_loading(
-            _truly_sync_units, _p_sync_fleet_mw, dt_seconds
+            _truly_sync_units, _p_sync_fleet_mw, dt_seconds,
+            output_bounds=_diesel_loading_bounds,
         )
 
     # Addendum H Phase 1: account for the completed interval after loading has
@@ -1883,7 +1985,9 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         p_dispatch_required_mw
         - _post_loading_turbine_output_mw
         - fuel_cell_output_mw,
+        # D10: the single plan has already credited current diesel delivery.
     )
+    _physical_bess_shortfall_mw = max(0.0, _physical_bess_shortfall_mw - _diesel_dispatch_target_mw)
     _emergency_release_authorized = False
     if _normal_bess_energy_exhausted:
         _grid_emergency_support_mw = (
@@ -1904,7 +2008,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
             # Diesel coordination runs after BESS arbitration.  Use measured
             # delivery from the preceding interval when deciding whether the
             # retained reserve must be released.
-            - state._prev_diesel_output_mw
+            - (0.0 if state.diesel_units else state._prev_diesel_output_mw)
             - _grid_emergency_support_mw,
         )
         _emergency_release_authorized = _emergency_gap_mw > 0.0
@@ -1944,7 +2048,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         # against an actual shortfall; negative values preserve its existing
         # surplus-absorption path so fixed FC overproduction charges the BESS.
         # tick() removes measured turbine output exactly once.
-        p_dispatch_required_mw - fuel_cell_output_mw,
+        p_dispatch_required_mw - fuel_cell_output_mw - _diesel_dispatch_target_mw,
         dt_seconds,
         bess_dispatch_target_mw=_effective_bess_setpoint_mw,
         bess_dispatch_ceilings_mw=_bess_dispatch_ceilings_mw,
@@ -1961,11 +2065,13 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         - fuel_cell_output_mw,
     )
     diesel_enabled = bool(state.diesel_units)
-    _diesel_snapshot = state.diesel_fleet_coordinator.step(
-        gap_mw=_gap_before_diesel_mw if diesel_enabled else 0.0,
-        sim_time=sim_time,
-        dt_seconds=dt_seconds,
-    )
+    if diesel_enabled:
+        state.diesel_fleet_coordinator.record_dispatch_fuel(dt_seconds)
+        _diesel_snapshot = state.diesel_fleet_coordinator.snapshot()
+    else:
+        _diesel_snapshot = state.diesel_fleet_coordinator.step(
+            gap_mw=0.0, sim_time=sim_time, dt_seconds=dt_seconds,
+        )
     diesel_output_mw = float(_diesel_snapshot.output_mw)
     state._prev_diesel_output_mw = diesel_output_mw if diesel_enabled else 0.0
 
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py
index 4fc360c..b40b63f 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py
@@ -135,7 +135,11 @@ def test_live_diesel_output_reduces_remaining_gap_before_curtailment() -> None:
 
     expected_diesel_mw = enabled.sim_state.diesel_fleet_coordinator.output_mw
     assert disabled.sim_state.diesel_fleet_coordinator.output_mw == 0.0
-    assert expected_diesel_mw == pytest.approx(3.0)
+    # D10 supersedes the fixed-block 3 MW assertion: the live unit follows
+    # the shared allocation down to its synchronized minimum.
+    assert expected_diesel_mw == pytest.approx(
+        enabled.sim_state.diesel_units[0].dispatch_floor_mw,
+    )
     assert captured["gap_mw"] < disabled_tick.p_demand_mw
     assert captured["gap_mw"] == pytest.approx(
         max(
@@ -158,13 +162,18 @@ def test_live_diesel_output_increases_generation_and_balance_residual() -> None:
     enabled_tick = _tick(enabled.sim_state, tick_index=0)
     diesel_output_mw = enabled.sim_state.diesel_fleet_coordinator.output_mw
 
-    assert diesel_output_mw == pytest.approx(3.0)
-    assert enabled_tick.p_generation_mw - disabled_tick.p_generation_mw == pytest.approx(
-        diesel_output_mw
+    # D10: diesel is allocated with primary sources, no longer an additive
+    # fixed block that must increase generation/imbalance by exactly 3 MW.
+    assert diesel_output_mw == pytest.approx(
+        enabled.sim_state.diesel_units[0].dispatch_floor_mw,
     )
-    assert enabled_tick.p_imbalance_mw - disabled_tick.p_imbalance_mw == pytest.approx(
-        diesel_output_mw
+    assert enabled_tick.p_generation_mw == pytest.approx(
+        enabled_tick.turbine_output_mw + enabled_tick.bess_output_mw
+        + enabled_tick.fuel_cell_output_mw + enabled_tick.p_renewable_mw
+        + diesel_output_mw,
     )
+    assert enabled_tick.physical_balance.passed
+    assert disabled_tick.physical_balance.passed
 
 
 def test_live_diesel_is_less_aggressive_than_disabled_before_curtailment() -> None:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_diesel_dispatch.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_diesel_dispatch.py
new file mode 100644
index 0000000..399589c
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_diesel_dispatch.py
@@ -0,0 +1,120 @@
+"""TC-ISL-19..22, D10 + IMPL-ISL-14/15.
+
+PROPOSED_HERE diagnostic fixture magnitudes are synthetic, not new plant
+defaults. The runtime minimum's source/rationale is documented on the module.
+"""
+import copy
+import pytest
+
+from core.asset_modules import DieselModule
+from core.diesel_fleet import DieselFleetCoordinator
+from core.models import DieselConfig, DieselState
+from core.simulation_core import _cost_ranked_dispatch_allocations
+from runtime.scenario_factory import build_run_context_from_spec
+from tests.test_diesel_phase3 import _spec, _tick
+
+
+def _live_context():
+    spec = copy.deepcopy(_spec(diesel_enabled=True))
+    spec["diesel_units"][0].update(
+        rated_mw=20.0, f_block=1.0, min_run_s=900.0, cooldown_s=300.0,
+    )
+    spec["diesel_power_block"].update(
+        unit_rating_mw=20.0, target_capacity_mw=20.0,
+        min_run_s=900.0, cooldown_s=300.0,
+    )
+    spec["bess_units"][0].update(rated_mw=10.0, usable_mwh=20.0)
+    ctx = build_run_context_from_spec("D10-regression", spec)
+    unit = ctx.sim_state.diesel_units[0]
+    unit.state = DieselState.SYNCHRONISED
+    unit._current_output_mw = 20.0
+    unit._run_start_s = 0.0
+    ctx.sim_state.diesel_fleet_coordinator.episode_id = "D10-fixture"
+    return ctx
+
+
+def test_tc_isl_19_closing_gap_backs_diesel_down_before_curtailment():
+    ctx = _live_context()
+    ctx.sim_state.compute_floor_mw = 30.0
+    high = _tick(ctx.sim_state, 1)
+    ctx.sim_state.compute_floor_mw = 1.0
+    low = _tick(ctx.sim_state, 2)
+    assert high.diesel_output_mw > 6.0
+    assert low.diesel_output_mw == pytest.approx(6.0)
+    assert high.p_dispatch_curtailed_mw == pytest.approx(0.0)
+    assert low.p_dispatch_curtailed_mw == pytest.approx(0.0)
+    assert high.physical_balance.passed
+    assert low.physical_balance.passed
+
+
+def test_tc_isl_20_shared_merit_order_rising_and_falling():
+    for demand in (20.0, 40.0, 60.0, 80.0, 60.0, 40.0, 20.0):
+        result = _cost_ranked_dispatch_allocations(
+            demand, bess_available_mw=10.0, turbine_available_mw=20.0,
+            fuel_cell_available_mw=30.0, diesel_available_mw=40.0,
+        )
+        assert result["bess-fleet"] == min(10.0, demand)
+        assert result["turbine-fleet"] == min(20.0, max(0.0, demand - 10.0))
+        assert result["fuel-cell-fleet"] == min(30.0, max(0.0, demand - 30.0))
+        assert result["diesel-fleet"] == max(0.0, demand - 60.0)
+    # Reversing a falling-demand unload must not expose stale rated capacity.
+    unit = DieselModule(DieselConfig(asset_id="resume", rated_mw=20.0, role="primary"))
+    unit.state = DieselState.UNLOADING
+    unit._current_output_mw = 2.0
+    unit._dispatch_ceiling_mw = 20.0
+    unit.resume_from_unloading()
+    unit.apply_dispatch_target(20.0)
+    assert unit.output_mw() == 6.0
+    # Explicit targets hold omitted GTs at minimum; they are not available
+    # primary headroom for the coordinator's dispatch-aware gap.
+    ctx = _live_context()
+    ctx.sim_state.compute_floor_mw = 20.0
+    ctx.sim_state._preload_targets_mw = {"not-on-bus": 0.0}
+    constrained = _tick(ctx.sim_state, 1)
+    assert constrained.turbine_output_mw == 0.0
+    assert constrained.diesel_output_mw > 6.0
+    assert constrained.p_unserved_mw == pytest.approx(0.0)
+    assert constrained.physical_balance.passed
+
+
+def test_tc_isl_21_unloading_power_fuel_and_physical_balance():
+    ctx = _live_context()
+    state = ctx.sim_state
+    state.compute_floor_mw = 1.0
+    unit = state.diesel_units[0]
+    unit.state = DieselState.UNLOADING
+    unit._current_output_mw = 6.0
+    unit._unload_start_output_mw = 6.0
+    before = state.diesel_fleet_coordinator.fuel_remaining_gal
+    tick = _tick(state, 1)
+    assert unit.is_on_bus
+    assert tick.diesel_output_mw == pytest.approx(5.9)
+    assert state.diesel_fleet_coordinator.output_mw == pytest.approx(5.9)
+    assert before - state.diesel_fleet_coordinator.fuel_remaining_gal == pytest.approx(
+        5.9 / 20.0 * 230.0 * 5.0 / 3600.0,
+    )
+    assert tick.physical_balance.passed
+
+
+def test_tc_isl_22_refused_stop_does_not_credit_hold_or_shorten_ramp():
+    unit = DieselModule(DieselConfig(
+        asset_id="timing-fixture", rated_mw=20.0, role="primary", f_block=1.0,
+    ))
+    unit.state = DieselState.SYNCHRONISED
+    unit._current_output_mw = 20.0
+    unit._run_start_s = 0.0
+    coordinator = DieselFleetCoordinator([unit])
+    coordinator.episode_id = "timing-fixture"
+    for t in (5.0, 100.0, 895.0):
+        coordinator.step(gap_mw=0.0, sim_time=t, dt_seconds=5.0)
+        assert coordinator._restore_elapsed_s == 0.0
+        assert unit.state == DieselState.SYNCHRONISED
+    coordinator.step(gap_mw=0.0, sim_time=900.0, dt_seconds=5.0)
+    assert unit.state == DieselState.UNLOADING
+    for elapsed in range(5, 300, 5):
+        coordinator.step(gap_mw=0.0, sim_time=900.0 + elapsed, dt_seconds=5.0)
+        assert unit.state == DieselState.UNLOADING
+        assert unit.output_mw() == pytest.approx(20.0 * (1.0 - elapsed / 300.0))
+    coordinator.step(gap_mw=0.0, sim_time=1200.0, dt_seconds=5.0)
+    assert unit.state == DieselState.OFFLINE
+    assert unit.output_mw() == 0.0
```
## Git status at STOP (including ignored new test)

```
 M .agents/memory/MEMORY.md
 M .agents/memory/diesel-dispatch-scope.md
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py
 M tools/dr_isl/PHASE_2D_REPORT.md
?? .agents/memory/headless-export-storage.md
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_diesel_dispatch.py
```

## Resumption requirement
A disk-backed output location needs approval: /tmp has a separate 4 GiB limit. No model/scenario/control change is proposed to address the storage failure. Remaining verification must finish before any implementation commit or Phase 3.
