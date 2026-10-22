# Phase 3 — TC125 diagnosis: STOP at 3.L

Date: 2026-10-22. Main HEAD: `3601f1550987213cafa38267d53d112e4e32cf58`.
Application BASE: `134538067d4eb4c2ce14232e483e9a91fd31276b`.
Candidate: retained stash `c52218ee0e35597eac442cabaa04e839ebc50273`.
No application, scenario, config, parameter or test file in the main tree was changed.
No implementation/test/report commit was made in this resumption; 3.N is conditional on all gates passing.

`P = attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim`.
BASE citations below refer to the main tree. Candidate citations refer to the stash tree, not the active application.

## 3.K(a) — exact candidate refusal

The unchanged TC125 fixture is defined at `P/tests/test_addendum_h_phase2a_commitment.py:39–75` and used at lines 588–605.
It sets `turbine-1` to `state="offline"`, `hot_standby=true`, `min_down_enabled=false`.
Calling the same adjudication as TC125 printed:

```json
{
  "manual_approval": false,
  "refusal_reason": "forecast controller veto: start ineligible (hot_standby)"
}
```

Candidate `P/runtime/turbine_commitment.py:1203–1210` invokes the shared predicate.
Candidate `P/core/asset_modules.py:1057–1067` returns `(False, "hot_standby")` at lines 1059–1060.
This is a direct invocation of the TC125 fixture and adjudication, not a newly passing pytest result.

## 3.K(b) — BASE approval and physical delivery

BASE `P/runtime/turbine_commitment.py:1198–1212` checks OFFLINE and minimum-down time, not `config.hot_standby`.
The identical fixture printed `manual_approval=true`, `refusal_reason=null`.
Immediately after that approval the unit remained `offline`, `hot_standby=true`, `is_on_bus=false`, `output_mw=0.0`.

The native core delivery path:

1. `P/core/simulation_core.py:2330–2346`: adjudicates the core proposal.
2. `P/core/simulation_core.py:2347–2350`: if approved, calls `_cht.command_start(sim_time)` without clearing `hot_standby`.
3. `P/core/asset_modules.py:1069–1070`: `if self.config.hot_standby: return`.
4. `P/core/simulation_core.py:2358–2359`: pending start is recorded only after transition to STARTING.
5. `P/core/simulation_core.py:2383–2387`: unchanged state produces the silently-dropped warning.

### Three-tick BASE delivery probe

Method: use the unchanged TC125 `_spec(...).model_dump()` fixture. Approve its proposal. Replace only the first otherwise-native `evaluate_commitment` return value in memory with that same proposal, to exercise the actual delivery branch. Later decisions are native. This is an injected delivery probe, not evidence that the natural core selects a reserved unit.
No scenario/config/parameter file or application source file is edited.

At `sim_time=0.0`, the native adjudicator again returned `approved=true`, `refusal_reason=null`.
The command capture printed:

| Command time s | Caller | Before state / hot_standby | After state / hot_standby | Output MW |
|---:|---|---|---|---:|
| 0.0 | `evaluate_tick`, `P/core/simulation_core.py:2350` | offline / true | offline / true | 0.0 |
| 10.0 | `_release_hot_standby_for_contingency`, `P/core/simulation_core.py:728` | offline / false | starting / false | 0.0 |

The exact first-command warning, at `P/core/simulation_core.py:2383`:

```text
Commitment engine: start 'turbine-1' silently dropped by command_start() at sim_time=0.0 (state=OFFLINE) — pending register NOT set; engine will retry next tick
```

Printed interval-end rows:

| Tick | sim_time s | turbine-1 state | hot_standby | is_on_bus | Output MW |
|---:|---:|---|---|---|---:|
| 1 | 5.0 | offline | true | false | 0.0 |
| 2 | 10.0 | offline | true | false | 0.0 |
| 3 | 15.0 | starting | false | false | 0.0 |

The later start is a different path, not delivery of the earlier approved core command.
`P/core/simulation_core.py:693–695` explicitly documents the contingency release as “intentionally not part of evaluate_commitment()”.
It clears the flag at line 727 and calls `command_start` at line 728; its caller is at lines 2933–2938.
The captured caller at 10.0 s proves that this separate path produced the later start.

## 3.K(c) — natural BASE scenario proposals

Observation point: return from the native `core.evaluate_commitment`, before core adjudication/delivery.
Count `action=="commit"` and inspect the selected turbine's current `config.hot_standby`.
The observer returns the native decision unchanged. Forecast probe runs are excluded; the measured arm/app run is counted.
The BASE observer uses the retained `1345380` worktree; `git diff 1345380 -- P` is empty on the requested main HEAD.
Pinning and execution paths are those of `/tmp/DR-ISL-phase3/finish_worker.py`; ticks are hashed in memory and discarded.
The diagnostic fixture's injected proposal is not included.

| Scenario | Arm/path | Ticks | Native core commit proposals | Targets with hot_standby=true |
|---|---|---:|---:|---:|
| scenario-h1-k8s-ray-24h | baseline | 17280 | 10 | 0 |
| scenario-h1-k8s-ray-24h | informed | 17280 | 5 | 0 |
| scenario-h2-slurm-24h | baseline | 17280 | 4 | 0 |
| scenario-h2-slurm-24h | informed | 17280 | 4 | 0 |
| scenario-uneven-multisched-01 | baseline | 1440 | 0 | 0 |
| scenario-uneven-multisched-01 | informed | 1440 | 0 | 0 |
| S10_mit_supercloud_2021-08-11 | app | 17280 | 1149 | 0 |
| demo-islanded-ramp | app | 2160 | 2 | 0 |

“Hot-standby” here is the actual guard flag, not a unit name or a thermal HOT label after release.
BASE `P/core/simulation_core.py:2183–2187` excludes `config.hot_standby` units from ordinary commitment's offline candidates.

Physical SHA-256 values from these observational BASE runs match the previously retained BASE values:

| Scenario / arm | Physical SHA-256 |
|---|---|
| H1 baseline | 57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b |
| H1 informed | 60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9 |
| H2 baseline | f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1 |
| H2 informed | 3b40147d28ee89f1ec312b7f57f1c9f77e82c99bd7e6ee4447ff5384f951dbdf |
| Base demo baseline | 90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1 |
| Base demo informed | ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6 |
| S10 app | 51dfe89b51138d85930b01684c95c58d60d7dcd1ed0c36801657c9d41840ef52 |
| Template app | fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a |

## 3.L — required STOP

The approved core command at 0.0 s was silently dropped by the hot-standby guard.
This meets the user's explicit STOP branch, even though a separate contingency release subsequently starts the unit.
Changing TC125 adjudication to accept or reject this target differently requires Lloyd's decision.
TC125 was not updated. TC132's substring assertion was not updated because the STOP branch was reached first.
No 3.M acceptance/test/suite runs or 3.N commits were started.
The prior 17-failure suite result remains historical; no new full-suite result is claimed.

## Evidence and repository state

Scratch directory: `/tmp/DR-ISL-phase3/resolve_tc125/`.
Evidence: `fixture-candidate.json`, `fixture-base.json`, `fixture-base-callers.json`, their `.log` files, per-scenario/arm `.json`/`.log` summaries, and observational scripts `fixture.py`, `counts_worker.py`.
No full tick export was written. Scratch helpers impose a 200,000,000-byte per-file limit.
The initial BASE fixture observer used a nonexistent `TickResult.sim_time` field and stopped after one tick; only the scratch observer was corrected to `sim_time_seconds`. Successful three-tick evidence is the callers JSON above.
Main application remains BASE; candidate remains in the retained stash.
Before removing the diagnostic candidate worktree, `git diff c52218e -- P` there was empty; the candidate was unchanged from the retained stash. That worktree was removed after the fixture evidence was collected.
Only this diagnostic report and the historical report's latest-status pointer are main-tree changes; both are uncommitted.
No publish, deploy, push or Phase 4.
