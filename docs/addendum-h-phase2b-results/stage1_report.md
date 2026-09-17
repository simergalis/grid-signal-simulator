# Addendum H Phase 2b-1 Stage-1 Report

Scope: H-1 and H-2 24-hour reference runs only, baseline and informed modes. No 7-day scenario was started. The baseline definition, acceptance rule, commitment policy, pre-load rule, fuel model, and curtailment ordering were not changed in this report work.

All four final run JSONs and both aggregate summary JSONs are below 100 KB; per-tick evidence remains in the compressed `*_ticks.jsonl.gz` files.

## Headline results

| Scenario | Verdict | Baseline fuel (MMBtu) | Informed fuel (MMBtu) | Difference (MMBtu) | Change | Avoided-curtailment share |
|---|---:|---:|---:|---:|---:|---:|
| scenario-h1-k8s-ray-24h | **PASS** | 6039.740230 | 5771.387452 | -268.352778 | -4.4431% | 1.7640 |
| scenario-h2-slurm-24h | **PASS** | 4953.257014 | 4818.440556 | -134.816458 | -2.7218% | 0.8911 |

The avoided-curtailment share is an attribution ratio, not a claim that every avoided MMBtu is independent of the other component changes. A ratio above 1 means other component deltas offset part of the avoided-curtailment reduction.

## scenario-h1-k8s-ray-24h

### Baseline

- Acceptance verdict: **PASS**
- Acceptance conditions:
- trace equality: **PASS**
- balance closure: **PASS**
- hard violations: **PASS**
- start reconciliation: **PASS**
- controller constraints: **PASS**
- informed-vs-baseline unserved energy: **PASS**
- informed-vs-baseline peak unserved: **PASS**

| Turbine fuel component | MMBtu |
|---|---:|
| load | 5847.168216351 |
| no-load | 72.430000000 |
| hot standby | 4.142013889 |
| starts | 116.000000000 |
| total | 6039.740230240 |
| pre-load tag | 0.000000000 |

- Curtailment: **187.690139189 MWh**; interval exposure **12118 ticks** (16.8306 h); attributable curtailment fuel **3394.620064264 MMBtu**.
- Controller stops refused by core reserve-floor condition: **0 compact refusal records**; raw numerical reserve-floor diagnostic evaluations: **0**.
- Controller stop followed by same-unit core `reserve floor violated` restart strictly inside the 900-second minimum-down window: **0**.

**Starts by unit/source:**
- `gt-hot-01` — `automatic_contingency` / `release`: 1
- `gt-hot-01` — `core_commitment` / `start`: 5
- `gt-hot-02` — `automatic_contingency` / `release`: 1
- `gt-hot-02` — `core_commitment` / `start`: 5

**Stops by unit/source:**
- `gt-hot-01` — `core_commitment` / `stop`: 6
- `gt-hot-01` — `turbine_physics` / `stop_complete`: 6
- `gt-hot-02` — `core_commitment` / `stop`: 6
- `gt-hot-02` — `turbine_physics` / `stop_complete`: 6

- Synchronized-count distribution (ticks): `{"2": 11563, "3": 2536, "4": 3181}`.
- Unit-minutes below 50% load: `{"gt-spin-01": 1440.0, "gt-spin-02": 1440.0}`.
- BESS SoC: minimum **0.828342155**, final **0.999999998**.
- Unserved energy: **0.894372986 MWh**, peak **35.021533247 MW**, intervals **20**; per-cluster MWh: `[[1, 0.131572339], [2, 0.153401354], [3, 0.154772651], [4, 0.155756224], [5, 0.139869935], [6, 0.159000484]]`.
- Forecast misses: **0**, peak **0.000000000 MW**.
- Core proposals: approved **0**, vetoed **0**.
- Wall-clock time: **25.687256 s**.

### Informed

- Acceptance verdict: **PASS**
- Acceptance conditions:
- trace equality: **PASS**
- balance closure: **PASS**
- hard violations: **PASS**
- start reconciliation: **PASS**
- controller constraints: **PASS**
- informed-vs-baseline unserved energy: **PASS**
- informed-vs-baseline peak unserved: **PASS**

| Turbine fuel component | MMBtu |
|---|---:|
| load | 5582.268771906 |
| no-load | 68.976666667 |
| hot standby | 4.142013889 |
| starts | 116.000000000 |
| total | 5771.387452462 |
| pre-load tag | 0.000000000 |

- Curtailment: **162.509583594 MWh**; interval exposure **10865 ticks** (15.0903 h); attributable curtailment fuel **2921.246800376 MMBtu**.
- Controller stops refused by core reserve-floor condition: **1 compact refusal records**; raw numerical reserve-floor diagnostic evaluations: **17167**.
- Controller stop followed by same-unit core `reserve floor violated` restart strictly inside the 900-second minimum-down window: **0**.

**Starts by unit/source:**
- `gt-hot-01` — `automatic_contingency` / `release`: 1
- `gt-hot-01` — `core_commitment` / `start`: 5
- `gt-hot-02` — `automatic_contingency` / `release`: 1
- `gt-hot-02` — `core_commitment` / `start`: 5

**Stops by unit/source:**
- `gt-hot-01` — `forecast_commitment` / `stop`: 6
- `gt-hot-01` — `turbine_physics` / `stop_complete`: 6
- `gt-hot-02` — `forecast_commitment` / `stop`: 6
- `gt-hot-02` — `turbine_physics` / `stop_complete`: 6

- Synchronized-count distribution (ticks): `{"2": 12686, "3": 2362, "4": 2232}`.
- Unit-minutes below 50% load: `{"gt-spin-01": 1440.0, "gt-spin-02": 1440.0}`.
- BESS SoC: minimum **0.828342155**, final **0.999999999**.
- Unserved energy: **0.894372986 MWh**, peak **35.021533247 MW**, intervals **20**; per-cluster MWh: `[[1, 0.131572339], [2, 0.153401354], [3, 0.154772651], [4, 0.155756224], [5, 0.139869935], [6, 0.159000484]]`.
- Forecast misses: **3403**, peak **51.281582000 MW**.
- Core proposals: approved **0**, vetoed **0**.
- Wall-clock time: **60.900479 s**.

### Fuel attribution

| Component delta (informed − baseline) | MMBtu |
|---|---:|
| load | -264.899444445 |
| no-load | -3.453333333 |
| hot standby | 0.000000000 |
| starts | 0.000000000 |
| total | -268.352777778 |

- Percent change versus baseline: **-4.4431%**.
- Avoided-curtailment fuel: **473.373263888 MMBtu**; share of total fuel difference: **1.7640**.

## scenario-h2-slurm-24h

### Baseline

- Acceptance verdict: **PASS**
- Acceptance conditions:
- trace equality: **PASS**
- balance closure: **PASS**
- hard violations: **PASS**
- start reconciliation: **PASS**
- controller constraints: **PASS**
- informed-vs-baseline unserved energy: **PASS**
- informed-vs-baseline peak unserved: **PASS**

| Turbine fuel component | MMBtu |
|---|---:|
| load | 4823.379791667 |
| no-load | 61.330000000 |
| hot standby | 4.547222222 |
| starts | 64.000000000 |
| total | 4953.257013889 |
| pre-load tag | 0.000000000 |

- Curtailment: **324.144769567 MWh**; interval exposure **16182 ticks** (22.4750 h); attributable curtailment fuel **4424.576041664 MMBtu**.
- Controller stops refused by core reserve-floor condition: **0 compact refusal records**; raw numerical reserve-floor diagnostic evaluations: **0**.
- Controller stop followed by same-unit core `reserve floor violated` restart strictly inside the 900-second minimum-down window: **0**.

**Starts by unit/source:**
- `gt-hot-01` — `automatic_contingency` / `release`: 1
- `gt-hot-01` — `core_commitment` / `start`: 3
- `gt-hot-02` — `automatic_contingency` / `release`: 1
- `gt-hot-02` — `core_commitment` / `start`: 1

**Stops by unit/source:**
- `gt-hot-01` — `core_commitment` / `stop`: 4
- `gt-hot-01` — `turbine_physics` / `stop_complete`: 4
- `gt-hot-02` — `core_commitment` / `stop`: 2
- `gt-hot-02` — `turbine_physics` / `stop_complete`: 2

- Synchronized-count distribution (ticks): `{"2": 15042, "3": 2238}`.
- Unit-minutes below 50% load: `{"gt-spin-01": 1440.0, "gt-spin-02": 1440.0}`.
- BESS SoC: minimum **0.950386947**, final **0.999999999**.
- Unserved energy: **9.422667343 MWh**, peak **44.868387870 MW**, intervals **7**; per-cluster MWh: `[[1, 2.476570406], [2, 1.268420001], [3, 1.490502844], [4, 1.251972087], [5, 1.704958328], [6, 1.230243678]]`.
- Forecast misses: **0**, peak **0.000000000 MW**.
- Core proposals: approved **0**, vetoed **0**.
- Wall-clock time: **23.558063 s**.

### Informed

- Acceptance verdict: **PASS**
- Acceptance conditions:
- trace equality: **PASS**
- balance closure: **PASS**
- hard violations: **PASS**
- start reconciliation: **PASS**
- controller constraints: **PASS**
- informed-vs-baseline unserved energy: **PASS**
- informed-vs-baseline peak unserved: **PASS**

| Turbine fuel component | MMBtu |
|---|---:|
| load | 4565.518125001 |
| no-load | 57.995000000 |
| hot standby | 2.927430556 |
| starts | 192.000000000 |
| total | 4818.440555556 |
| pre-load tag | 0.000000000 |

- Curtailment: **299.465950765 MWh**; interval exposure **16149 ticks** (22.4292 h); attributable curtailment fuel **4304.440555553 MMBtu**.
- Controller stops refused by core reserve-floor condition: **2 compact refusal records**; raw numerical reserve-floor diagnostic evaluations: **15493**.
- Controller stop followed by same-unit core `reserve floor violated` restart strictly inside the 900-second minimum-down window: **0**.

**Starts by unit/source:**
- `gt-hot-01` — `automatic_contingency` / `release`: 1
- `gt-hot-01` — `core_commitment` / `start`: 7
- `gt-hot-02` — `automatic_contingency` / `release`: 1
- `gt-hot-02` — `core_commitment` / `start`: 2
- `gt-spin-02` — `core_commitment` / `start`: 8

**Stops by unit/source:**
- `gt-hot-01` — `core_commitment` / `stop`: 1
- `gt-hot-01` — `forecast_commitment` / `stop`: 6
- `gt-hot-01` — `turbine_physics` / `stop_complete`: 7
- `gt-hot-02` — `core_commitment` / `stop`: 3
- `gt-hot-02` — `turbine_physics` / `stop_complete`: 3
- `gt-spin-02` — `forecast_commitment` / `stop`: 9
- `gt-spin-02` — `turbine_physics` / `stop_complete`: 9

- Synchronized-count distribution (ticks): `{"1": 856, "2": 15331, "3": 1093}`.
- Unit-minutes below 50% load: `{"gt-hot-01": 1440.0, "gt-spin-01": 1440.0}`.
- BESS SoC: minimum **0.950386947**, final **0.999999988**.
- Unserved energy: **9.422667343 MWh**, peak **44.868387870 MW**, intervals **7**; per-cluster MWh: `[[1, 2.476570406], [2, 1.268420001], [3, 1.490502844], [4, 1.251972087], [5, 1.704958328], [6, 1.230243678]]`.
- Forecast misses: **1764**, peak **91.982733000 MW**.
- Core proposals: approved **0**, vetoed **0**.
- Wall-clock time: **58.032907 s**.

### Fuel attribution

| Component delta (informed − baseline) | MMBtu |
|---|---:|
| load | -257.861666666 |
| no-load | -3.335000000 |
| hot standby | -1.619791666 |
| starts | 128.000000000 |
| total | -134.816458333 |

- Percent change versus baseline: **-2.7218%**.
- Avoided-curtailment fuel: **120.135486111 MMBtu**; share of total fuel difference: **0.8911**.

## Diagnostic 1 — curtailment plausibility

Site demand is `p_total_mw` from the compressed tick evidence. Fleet minimum stable load is the sum of `msl_mw` for synchronized, unloading, or otherwise on-bus synchronized units. BESS charge headroom uses the authored 30 MW / 60 MWh H-1/H-2 BESS and the 5-second physical charge-acceptance ceiling.

| Scenario/mode | Demand min / median / p95 / max MW | Fleet MSL min / median / p95 / max MW | Ticks MSL > demand + BESS headroom | Duration | Curtailment |
|---|---|---|---:|---:|---:|
| scenario-h1-k8s-ray-24h / baseline | 0.0541 / 7.4654 / 71.7757 / 98.3358 | 17.5000 / 17.5000 / 35.0000 / 35.0000 | 12104 | 16.8111 h | 187.6901 MWh |
| scenario-h1-k8s-ray-24h / informed | 0.0541 / 7.4654 / 71.7757 / 98.3358 | 17.5000 / 17.5000 / 35.0000 / 35.0000 | 10853 | 15.0736 h | 162.5096 MWh |
| scenario-h2-slurm-24h / baseline | 0.0438 / 3.4617 / 9.2634 / 117.0987 | 17.5000 / 17.5000 / 26.2500 / 26.2500 | 16177 | 22.4681 h | 324.1448 MWh |
| scenario-h2-slurm-24h / informed | 0.0438 / 3.4617 / 9.2634 / 117.0987 | 8.7500 / 17.5000 / 26.2500 / 26.2500 | 16144 | 22.4222 h | 299.4660 MWh |

- Plain reading: the H-1 187.690139 MWh baseline and 162.509584 MWh informed curtailment are consistent with long periods where synchronized units carry 17.5–35 MW of minimum stable output while site demand is low and the BESS charge headroom is zero or insufficient. H-2 shows the same mechanism, with 324.144770 / 299.465951 MWh and more low-demand exposure. The table supports the curtailment magnitude; it does not by itself establish that every interval is optimally committed.

## Diagnostic 2 — D4 balance defect

`d4_balance_defect_mw` is the absolute residual returned by `_balance_defect_mw(_balance_terms)`. The balance terms are local generation, demand, unserved demand, and grid exchange; in islanded mode this is the pre-curtailment generation-versus-load residual. The definition is in `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3424-3453`.

The stage-1 `closure_status` is true because its acceptance check is the authoritative physical ledger check in `run_phase2b_stage1.py:366-400`; that ledger includes explicit dispatch curtailment as a sink. The D4 diagnostic is intentionally not that closure gate.

| Scenario/mode | D4 max MW | Dispatch-curtailment max MW | Closure |
|---|---:|---:|---:|
| scenario-h1-k8s-ray-24h / baseline | 32.205278552 | 32.205278552 | **PASS** |
| scenario-h1-k8s-ray-24h / informed | 23.758471200 | 23.758471200 | **PASS** |
| scenario-h2-slurm-24h / baseline | 24.358920000 | 24.358920000 | **PASS** |
| scenario-h2-slurm-24h / informed | 24.358920000 | 24.358920000 | **PASS** |

The values confirm that D4 tracks the pre-curtailment surplus in these runs: the D4 and dispatch-curtailment maxima match within the exported precision for each run, but the numeric maximum is not 32.205278552 for every run. That value is H-1 baseline; H-1 informed is 23.758471200 and both H-2 modes are 24.358920000. D4 is therefore a pre-curtailment residual diagnostic, not an accounting gap or a reason to fail physical-ledger closure.

## Diagnostic 3 — forecast quality

The signed error below is actual demand minus forecast peak. The p50 label is the exported median. Misses use the existing sensitivity threshold and forecast rule; no forecast rule was changed.

| Scenario/mode | Mean | p50 | p90 | p99 | Max | Miss count | Miss peak MW |
|---|---:|---:|---:|---:|---:|---:|---:|
| scenario-h1-k8s-ray-24h / baseline | 0.000000000 | 0.000000000 | 0.000000000 | 0.000000000 | 0.000000000 | 0 | 0.000000000 |
| scenario-h1-k8s-ray-24h / informed | -7.289931198 | -1.278036896 | 4.201896701 | 33.116219004 | 51.281581700 | 3403 | 51.281582000 |
| scenario-h2-slurm-24h / baseline | 0.000000000 | 0.000000000 | 0.000000000 | 0.000000000 | 0.000000000 | 0 | 0.000000000 |
| scenario-h2-slurm-24h / informed | -3.390270135 | -0.607731677 | 2.039005955 | 48.198702241 | 91.982733044 | 1764 | 91.982733000 |

Baseline has no controller forecast history, so its forecast-error fields are zero by construction. The 24-hour informed runs show misses because the controller forecast is based on lagged measured history while the restored 24-hour demand trace contains later bursts and transitions that are not present in the forecast window at the evaluation instant. The two-hour smoke has no misses because its shorter trace does not exercise the same later background bursts; its informed forecast history also has a much smaller horizon.

Recommendation: do not change the forecast rule in stage 2b-1. A future change could add a bounded burst/event side-channel or a calibrated upper-quantile forecast, but that would require a new acceptance baseline, forecast-quality tests, and revalidation of starts, fuel, and unserved energy. The operational cost would be more conservative turbine commitment and potentially more starts/no-load fuel; the engineering cost is a separate design and test pass.

## Closure decision

H-65 is committed and the confirming Phase 2a smoke is PASS: baseline 574.613363426 MMBtu / 2.252165190 MWh unserved, informed 528.841861699 MMBtu / 0.075899258 MWh unserved, with 4 informed refusal records and 774 suppressed repeats. Both H-1 and H-2 24-hour stage-1 aggregates are PASS, and all requested diagnostics are recorded above.

Stage 2b-1 can close. The 7-day runs may start as the next separately controlled step; they were not started here.