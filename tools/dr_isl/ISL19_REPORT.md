# IMPL-ISL-19 — over-frequency and dispatch curtailment
DR-2026-10-20-ISLAND-COLLAPSE; read-only diagnosis; 2026-10-22.
Base/application HEAD: `5225a05a7f2dc76acd18dad172fd2cf002c6afd8`.
`P` below expands to `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim`. Evidence paths below are relative to `tools/dr_isl/isl19/` unless stated otherwise.

## Scope and execution controls
Four cases, baseline and requested ledger-formula counterfactual once each (8 recorded executions, plus the existing harness's six unrecorded demand-probe invocations); H1 conventional means harness `baseline`. The study cases use the existing probe/replay and seed/arm settings; S10 uses the pinned ScenarioSpec → factory → RunManager instant-playback path. No study cache or artifact writer is used. Pinning is the existing `tools/dr_isl/baseline_runner.py:1–12, 34–38, 64–84` contract: Python/NumPy/fabric/configured kube seed 1729, per-diesel 1729+i, wall clock 1792454400.0. Base-demo study seed is 42; H1 uses its declared seed.
Observation compiles ONLY evaluate_tick with two observation calls in worker processes; main application files, running app and inputs are not changed. The scratch counterfactual and instrumentation source are NOT committed. Targeted scalar-channel CSVs are NOT full TickResult exports. All completed summaries were written durably before the next case.
Observation control against the already measured Phase-5 hashes (excluding its two newly added reporting fields):
```json
[
  {
    "name": "scenario-uneven-multisched-01_baseline",
    "prior_physical_sha256": "90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1",
    "observed_physical_sha256": "90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1",
    "identical": true
  },
  {
    "name": "scenario-uneven-multisched-01_informed",
    "prior_physical_sha256": "ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6",
    "observed_physical_sha256": "ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6",
    "identical": true
  },
  {
    "name": "scenario-h1-k8s-ray-24h_baseline",
    "prior_physical_sha256": "57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b",
    "observed_physical_sha256": "57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b",
    "identical": true
  },
  {
    "name": "S10_mit_supercloud_2021-08-11_app",
    "prior_physical_sha256": "8ba0dec0459ca09b9df4ea6fa17bd72fa16038220f425b0a8dd499bfa87557ab",
    "observed_physical_sha256": "8ba0dec0459ca09b9df4ea6fa17bd72fa16038220f425b0a8dd499bfa87557ab",
    "identical": true
  }
]
```

## D1 — exact producer/consumer trace, in tick order
Source lines are reproduced verbatim in `TRACE_SOURCES.txt`; method ranges are in `FUNCTION_LOCATIONS.json`.

| Order | File:line / function | Input → output |
|---|---|---|
|1|`P/runtime/run_manager.py:1808–1845`, `RunContext.step` → `P/core/simulation_core.py:946`, `evaluate_tick`|Run clock/state → one TickResult.|
|2|`P/core/simulation_core.py:1171,1228,1311–1324`; `GPUModule.advance`, `per_job_compute_mw`, `CoolingModule.advance/output_mw`|GPU/job draws are summed; either recorded demand replay or thermal-lag cooling supplies compute/cooling; demand = compute + cooling. There is no separate 'other' term in that sum.|
|3|`P/core/simulation_core.py:1335–1376`|Solar advance/output, then renewable curtailment; this is DISTINCT from dispatch curtailment.|
|4|`P/core/simulation_core.py:1471–1497`|Choose on-bus-turbine weighted H/MVA, otherwise GF-BESS VSM or site fallback; this happens before turbine advance at :1635.|
|5|`P/core/simulation_core.py:1542–1588`|Derive droop clamp from first-stage UF/OF thresholds; if none, droop correction = 0. It is a possible frequency→dispatch feedback when configured.|
|6|`P/core/simulation_core.py:1635,1666–1671, 1740–1955`; `_cost_ranked_dispatch_allocations` at :863–944|Advance turbines/FC, allocate ranked turbine/BESS/FC/diesel output and apply loading; actual unit output, not requested load, feeds the next steps.|
|7|`P/core/simulation_core.py:2136–2195`; `DispatchArbitrator.tick` (`P/core/dispatch.py:853–1011`)|Actual turbine output; BESS cover_shortfall or absorb_surplus; negative BESS output is charging. Diesel snapshot output is read at :2170.|
|7 detail|`P/core/loading.py:33–139,146–204`; `compute_loading_setpoints` → `ramp_limited_output` → `apply_loading` / `apply_loading_targets`|Sequential setpoints, physical rise/fall limits and minimum stable output → actual turbine MW. Calls are at `P/core/simulation_core.py:1796,1945,1953–1959`.|
|7 asset detail|`P/core/asset_modules.py:372–438,464–521,848–885,1201–1226,1456–1560,1680–1817,1874–1897`|Respectively GPU compute draws, cooling lag, turbine start/output, diesel advance/dispatch/output, BESS shortfall coverage/surplus absorption, solar advance/output. Individual method ranges are in FUNCTION_LOCATIONS.json; loading bodies are in TRACE_LOADING_SOURCES.txt.|
|8|`P/core/simulation_core.py:3193–3236`|G = turbine + signed BESS + FC + renewable + diesel; surplus = max(0,G−demand). Dispatch dump sink = surplus × response fraction. The elapsed timer advances by the WHOLE outer dt before this fraction is computed; no dump-response sub-step is integrated.|
|9|`P/core/simulation_core.py:3315–3331`|Islanded: grid=0, frequency_forcing=G−demand. Grid-tied uncapped: forcing=0; capped: forcing=(G−demand)−grid_exchange. NO dispatch-sink subtraction.|
|10|`P/core/simulation_core.py:3372,3438–3489`|dynamic forcing starts as frequency_forcing; df/dt=[60×(dynamic_forcing+new_UFLS_shed)/S_base − D_eff×(f−60)]/(2H); f += df/dt×dt_sub.|
|11|`P/core/simulation_core.py:3492–3502,3514–3540`|FC ride-through trips reduce dynamic forcing within the substep. Governor cascade advances separately; it is not added as current-tick forcing. UFLS can reduce load inside this loop.|
|12|`P/core/simulation_core.py:3652–3665`|Post-FC-trip generation/public forcing reconciliation, if trips occurred.|
|13|`P/core/simulation_core.py:3693–3713`|D7: unserved=min(demand,max(explicit_shed,demand−achieved_supply)); served=demand−unserved. Reconcile sink ≤ achieved_supply−served. This is AFTER frequency integration. p_imbalance=achieved_supply−served also excludes the explicit sink.|
|14|`P/core/simulation_core.py:3745–3765` → `P/core/power_balance.py:133–166,186–216`|Physical defect=local generation+permitted import−served−losses−curtailment. BESS charge is already negative in local generation. Losses=0 at :3748. Do NOT subtract BESS charging a second time.|
|15|`P/core/simulation_core.py:4039,4125`|Tick telemetry publishes the reconciled sink and public pre-sink forcing.|

**Answer to the subtraction question:** BESS charge is included once, negatively, BEFORE forcing. The dispatch-curtailment sink is NOT netted. D7 physical shortfall/served accounting is AFTER the integrator, not subtracted before it. New within-tick UFLS shedding is added separately inside the loop. None of these four runs has configured frequency protection or an FC ride-through trip (`*.summary.json`, `audit.site`, `audit.fc_trips`).

### Deliberate historical ordering, not an accidental missing line
Introducing ordering commit: `b74830d26d8ac8753f16f43fb25f94a43d68c903`, author/commit date 2026-09-17T15:36:28Z, 'Repair Phase 2a islanded surplus ordering' (`PROVENANCE.txt`).
`P/core/simulation_core.py:3200–3212` explicitly says:
> 'do not subtract that sink before the electromechanical response: the rotor must see the surplus on this tick.'
> 'this ledger value is the surplus scheduled for that action, not a fictional change to measured generation.'
`docs/addendum-h-phase2a-change-record.md:38–52` documents the same ordering and says the default 0.5 s response delay is below the 5 s smoke interval. `P/core/models.py:499–503` supplies that default. Measured settings in every audit summary are dt_sub=0.01 s and outer dt=5 s, so the sink is full response on each positive-surplus outer tick, yet its surplus still forces ALL 500 substeps.

## D2 — quantified current-HEAD runs
Counts below use the engine's frequency_valid flag, not a separate filter. Curtailment>0 is literal; equality/sign analysis tolerance 1e-9 MW is PROPOSED_HERE for analysis only and never changes a simulator input.
|Case|Ticks|Invalid|Invalid fraction|Invalid with C>0|Share of invalid|Invalid with C=0|Share of invalid|Hz min / max|
|---|---:|---:|---:|---:|---:|---:|---:|---|
|scenario-uneven-multisched-01_baseline|1440|700|0.4861111111111111|637|0.91000000000000003|63|0.089999999999999997|-5.0008668933676752 / 176.43084811383099|
|scenario-uneven-multisched-01_informed|1440|614|0.42638888888888887|446|0.7263843648208469|168|0.2736156351791531|59.534837314959205 / 169.8277840657461|
|scenario-h1-k8s-ray-24h_baseline|17280|13598|0.78692129629629626|11753|0.86431828210030892|1845|0.13568171789969113|17.233729831989471 / 224.93353102420852|
|S10_mit_supercloud_2021-08-11_app|17280|7264|0.42037037037037039|5615|0.77299008810572689|1649|0.22700991189427314|-729.10751180806687 / 998.93305345054637|
### scenario-uneven-multisched-01_baseline: distributions and zero-curtailment causes
```json
{
  "forcing_minus_curtailment_distribution": {
    "n": 637,
    "min": 0.0,
    "max": 0.0,
    "mean": 0.0,
    "p50": 0.0,
    "p95": 0.0,
    "p99": 0.0,
    "within_1e_9": 637
  },
  "subgroups": {
    "curtailment_positive/positive/over": 637,
    "curtailment_zero/negative/under": 27,
    "curtailment_zero/zero/under": 26,
    "curtailment_zero/zero/over": 10
  },
  "zero_curtailment_extrema": {
    "h_aggregate": {
      "min": 4.0,
      "max": 4.0
    },
    "s_base_mva": {
      "min": 58.82352941176471,
      "max": 117.64705882352942
    },
    "dt_sub": {
      "min": 0.01,
      "max": 0.01
    },
    "substeps": {
      "min": 500.0,
      "max": 500.0
    },
    "df_dt_last": {
      "min": -2.5947295935047276,
      "max": 0.8502776423486905
    },
    "euler_damping_factor": {
      "min": 0.9997888497242601,
      "max": 0.9999746286540054
    },
    "demand_step_mw": {
      "min": -8.80499876290473,
      "max": 60.05387828026538
    }
  },
  "new_sync_after_inertia_selection": [],
  "consistency_checks": {
    "raw_forcing_equals_published": true,
    "predicted_served_equals_final_served": true,
    "pre_sink_equals_final_sink": true
  },
  "baseline_physical_balance_failures": 0
}
```

The sign subgroups are mutually exclusive within each curtailment class; overlap with over/under-frequency is printed explicitly. A negative forcing is a current generation deficit; zero forcing with out-of-band f is carried frequency relaxing toward nominal, not a new surplus on that tick. A demand_step_mw is the actual outer-tick change (including cooling lag), not necessarily a discrete job event.
The Euler damping factor is 1−D_eff×dt_sub/(2H); its recorded range tests explicit-Euler damping stability at the fixed forcing, not the fidelity of the forcing or plant parameters.
#### Ten evenly spaced invalid ticks: curtailment_positive
Full-precision scalar values; turbine column is total output / current on-bus minimum-stable total. Per-unit output/minimum/state is in the CSV `turbines_output_min_state` column.
|tick|time s|Hz|forcing MW|curtail MW|abs(F−C) MW|defect MW|BESS MW|GT MW / min|diesel MW|H|S MVA|last df/dt|dt_sub / n|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|124|620.0|67.6374079505063|13.765982173560861|13.765982173560861|0.0|0.0|-30.0|60.0 / 26.25|6.0|4.0|88.23529411764707|0.5679886821203655|0.01 / 500|
|707|3535.0|71.94947849747471|4.6137735999763585|4.6137735999763585|0.0|0.0|-30.0|35.0 / 35.0|6.0|4.0|117.64705882352942|0.02626143410272208|0.01 / 500|
|777|3885.0|73.23346888116289|4.3126998543169615|4.3126998543169615|0.0|0.0|-30.0|35.0 / 35.0|6.0|4.0|117.64705882352942|-0.01726090953267323|0.01 / 500|
|928|4640.0|68.93165584982812|3.8085977515983176|3.8085977515983176|0.0|0.0|-30.0|35.0 / 35.0|6.0|4.0|117.64705882352942|0.12116460327254046|0.01 / 500|
|1087|5435.0|153.62455665436642|32.18775299639838|32.18775299639838|0.0|0.0|-0.0|35.0 / 35.0|2.3|4.0|117.64705882352942|-0.04069860212731857|0.01 / 500|
|1157|5785.0|155.6859658403868|9.821800763077814|9.821800763077814|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|-0.3920203881642603|0.01 / 500|
|1228|6140.0|168.62750616185076|7.326268816944367|7.326268816944367|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|-0.13317540977283437|0.01 / 500|
|1299|6495.0|87.52717092561652|2.767721361887947|2.767721361887947|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|-0.11461827413715758|0.01 / 500|
|1369|6845.0|92.48930296832857|4.8911912450111785|4.8911912450111785|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|0.030120917542730608|0.01 / 500|
|1440|7200.0|117.88239532654443|9.479946989497282|9.479946989497282|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|0.2942220608978958|0.01 / 500|
#### Ten evenly spaced invalid ticks: curtailment_zero
Full-precision scalar values; turbine column is total output / current on-bus minimum-stable total. Per-unit output/minimum/state is in the CSV `turbines_output_min_state` column.
|tick|time s|Hz|forcing MW|curtail MW|abs(F−C) MW|defect MW|BESS MW|GT MW / min|diesel MW|H|S MVA|last df/dt|dt_sub / n|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|67|335.0|40.909530078118486|-22.30936246553462|0.0|22.30936246553462|0.0|29.0|25.0 / 17.5|0.0|4.0|58.82352941176471|-2.5947295935047276|0.01 / 500|
|74|370.0|8.601721826463688|-5.22104440778422|0.0|5.22104440778422|0.0|29.0|50.0 / 17.5|20.0|4.0|58.82352941176471|-0.1727483368016396|0.01 / 500|
|81|405.0|3.2699270764262756|-5.361435043708312|0.0|5.361435043708312|0.0|29.0|50.0 / 17.5|20.0|4.0|58.82352941176471|-0.13308560002137915|0.01 / 500|
|88|440.0|-3.3185335382108123|-11.999826382360467|0.0|11.999826382360467|0.0|29.0|57.5 / 26.25|20.0|4.0|88.23529411764707|0.22944104205391658|0.01 / 500|
|95|475.0|19.50874210804342|0.0|0.0|0.0|0.0|29.0|75.0 / 26.25|8.075683904495918|4.0|88.23529411764707|0.6272651568276758|0.01 / 500|
|101|505.0|34.63784823737926|0.0|0.0|0.0|0.0|29.0|75.0 / 26.25|8.322329264920171|4.0|88.23529411764707|0.39725441142343165|0.01 / 500|
|108|540.0|45.32176368040824|0.0|0.0|0.0|0.0|29.0|75.0 / 26.25|8.249739637985527|4.0|88.23529411764707|0.2291678196447149|0.01 / 500|
|115|575.0|51.50343809800141|0.0|0.0|0.0|0.0|29.0|75.0 / 26.25|8.267160087267598|4.0|88.23529411764707|0.13275785639771914|0.01 / 500|
|518|2590.0|66.0836995494571|0.0|0.0|0.0|0.0|-29.351724700524002|35.0 / 35.0|6.0|4.0|117.64705882352942|-0.07960736660491054|0.01 / 500|
|824|4120.0|66.26258930534422|0.0|0.0|0.0|0.0|-28.651500584424195|35.0 / 35.0|6.0|4.0|117.64705882352942|-0.08030380369001602|0.01 / 500|
### scenario-uneven-multisched-01_informed: distributions and zero-curtailment causes
```json
{
  "forcing_minus_curtailment_distribution": {
    "n": 446,
    "min": 0.0,
    "max": 0.0,
    "mean": 0.0,
    "p50": 0.0,
    "p95": 0.0,
    "p99": 0.0,
    "within_1e_9": 446
  },
  "subgroups": {
    "curtailment_positive/positive/over": 446,
    "curtailment_zero/zero/over": 168
  },
  "zero_curtailment_extrema": {
    "h_aggregate": {
      "min": 4.0,
      "max": 4.0
    },
    "s_base_mva": {
      "min": 58.82352941176471,
      "max": 117.64705882352942
    },
    "dt_sub": {
      "min": 0.01,
      "max": 0.01
    },
    "substeps": {
      "min": 500.0,
      "max": 500.0
    },
    "df_dt_last": {
      "min": -0.18783752780627933,
      "max": -0.012400982018611832
    },
    "euler_damping_factor": {
      "min": 0.9997656466116882,
      "max": 0.9999817527042887
    },
    "demand_step_mw": {
      "min": -2.694999107298173,
      "max": 83.99548392923171
    }
  },
  "new_sync_after_inertia_selection": [],
  "consistency_checks": {
    "raw_forcing_equals_published": true,
    "predicted_served_equals_final_served": true,
    "pre_sink_equals_final_sink": true
  },
  "baseline_physical_balance_failures": 0
}
```

The sign subgroups are mutually exclusive within each curtailment class; overlap with over/under-frequency is printed explicitly. A negative forcing is a current generation deficit; zero forcing with out-of-band f is carried frequency relaxing toward nominal, not a new surplus on that tick. A demand_step_mw is the actual outer-tick change (including cooling lag), not necessarily a discrete job event.
The Euler damping factor is 1−D_eff×dt_sub/(2H); its recorded range tests explicit-Euler damping stability at the fixed forcing, not the fidelity of the forcing or plant parameters.
#### Ten evenly spaced invalid ticks: curtailment_positive
Full-precision scalar values; turbine column is total output / current on-bus minimum-stable total. Per-unit output/minimum/state is in the CSV `turbines_output_min_state` column.
|tick|time s|Hz|forcing MW|curtail MW|abs(F−C) MW|defect MW|BESS MW|GT MW / min|diesel MW|H|S MVA|last df/dt|dt_sub / n|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|123|615.0|66.19487030675623|23.53627916410341|23.53627916410341|0.0|0.0|-30.0|69.77018730743602 / 35.0|6.0|4.0|117.64705882352942|1.0124809082015835|0.01 / 500|
|539|2695.0|99.1371931063025|23.456459491928907|23.456459491928907|0.0|0.0|-30.0|59.03064047025286 / 35.0|5.4|4.0|117.64705882352942|0.8575271795327738|0.01 / 500|
|1094|5470.0|149.04424441061084|13.531380902202557|13.531380902202557|0.0|0.0|-0.0|17.5 / 17.5|2.3|4.0|58.82352941176471|0.07781827797801211|0.01 / 500|
|1143|5715.0|155.95289873231135|10.669652159559218|10.669652159559218|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|0.3328477205838627|0.01 / 500|
|1193|5965.0|125.20482976605123|12.723270123660177|12.723270123660177|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|0.017266142801871442|0.01 / 500|
|1242|6210.0|142.65430107439212|5.800795593464084|5.800795593464084|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|-0.32116667308549496|0.01 / 500|
|1292|6460.0|90.90908613604168|0.6768036077956445|0.6768036077956445|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|-0.34987432462434276|0.01 / 500|
|1341|6705.0|84.37483375561037|4.236088001123175|4.236088001123175|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|0.07817826389936805|0.01 / 500|
|1391|6955.0|100.19590033627865|7.12151344896429|7.12151344896429|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|0.09735868452166696|0.01 / 500|
|1440|7200.0|117.88239532651781|9.479946989497282|9.479946989497282|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|0.2942220608983166|0.01 / 500|
#### Ten evenly spaced invalid ticks: curtailment_zero
Full-precision scalar values; turbine column is total output / current on-bus minimum-stable total. Per-unit output/minimum/state is in the CSV `turbines_output_min_state` column.
|tick|time s|Hz|forcing MW|curtail MW|abs(F−C) MW|defect MW|BESS MW|GT MW / min|diesel MW|H|S MVA|last df/dt|dt_sub / n|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|371|1855.0|69.8770916620952|0.0|0.0|0.0|0.0|27.92891935779852|65.0 / 35.0|5.699999999999999|4.0|117.64705882352942|-0.026096875467731328|0.01 / 500|
|390|1950.0|67.72355266525992|0.0|0.0|0.0|0.0|13.78242984637049|77.09080012933133 / 35.0|6.0|4.0|117.64705882352942|-0.01958988197767355|0.01 / 500|
|408|2040.0|66.21761554629069|0.0|0.0|0.0|0.0|4.956893195286469|83.75 / 35.0|6.0|4.0|117.64705882352942|-0.012626135159894152|0.01 / 500|
|553|2765.0|97.76699318780614|0.0|0.0|0.0|0.0|4.133248779519889|60.391557165154225 / 35.0|6.0|4.0|117.64705882352942|-0.10436949636539762|0.01 / 500|
|571|2855.0|90.05305266587479|0.0|0.0|0.0|0.0|0.8261705918310014|61.546255898661755 / 35.0|6.0|4.0|117.64705882352942|-0.06949923529469057|0.01 / 500|
|590|2950.0|84.39129165600308|0.0|0.0|0.0|0.0|8.609368988830823|55.391557165154225 / 35.0|6.0|4.0|117.64705882352942|-0.0554797235625804|0.01 / 500|
|608|3040.0|80.16168200246454|0.0|0.0|0.0|0.0|19.520135064282854|47.891557165154225 / 35.0|6.0|4.0|117.64705882352942|-0.04312441870697239|0.01 / 500|
|627|3135.0|75.7585642413553|0.0|0.0|0.0|0.0|3.225971113264052|62.503566705810215 / 35.0|6.0|4.0|117.64705882352942|-0.0511094340376015|0.01 / 500|
|645|3225.0|71.92788992414727|0.0|0.0|0.0|0.0|2.788435508041502|62.34811755851037 / 35.0|6.0|4.0|117.64705882352942|-0.03640997169449569|0.01 / 500|
|676|3380.0|66.26778316426054|0.0|0.0|0.0|0.0|-14.340464286057824|17.5 / 17.5|6.0|4.0|58.82352941176471|-0.1424750043527323|0.01 / 500|
### scenario-h1-k8s-ray-24h_baseline: distributions and zero-curtailment causes
```json
{
  "forcing_minus_curtailment_distribution": {
    "n": 11753,
    "min": 0.0,
    "max": 0.0,
    "mean": 0.0,
    "p50": 0.0,
    "p95": 0.0,
    "p99": 0.0,
    "within_1e_9": 11753
  },
  "subgroups": {
    "curtailment_positive/positive/over": 11740,
    "curtailment_positive/positive/under": 13,
    "curtailment_zero/zero/over": 1117,
    "curtailment_zero/negative/over": 5,
    "curtailment_zero/negative/under": 52,
    "curtailment_zero/zero/under": 671
  },
  "zero_curtailment_extrema": {
    "h_aggregate": {
      "min": 4.0,
      "max": 4.0
    },
    "s_base_mva": {
      "min": 58.82352941176471,
      "max": 117.64705882352942
    },
    "dt_sub": {
      "min": 0.01,
      "max": 0.01
    },
    "substeps": {
      "min": 500.0,
      "max": 500.0
    },
    "df_dt_last": {
      "min": -2.9474158067892446,
      "max": 0.10415782156434392
    },
    "euler_damping_factor": {
      "min": 0.9993524706466812,
      "max": 0.9999960064421624
    },
    "demand_step_mw": {
      "min": -44.997198,
      "max": 84.17219496617619
    }
  },
  "new_sync_after_inertia_selection": [],
  "consistency_checks": {
    "raw_forcing_equals_published": true,
    "predicted_served_equals_final_served": true,
    "pre_sink_equals_final_sink": true
  },
  "baseline_physical_balance_failures": 0
}
```

The sign subgroups are mutually exclusive within each curtailment class; overlap with over/under-frequency is printed explicitly. A negative forcing is a current generation deficit; zero forcing with out-of-band f is carried frequency relaxing toward nominal, not a new surplus on that tick. A demand_step_mw is the actual outer-tick change (including cooling lag), not necessarily a discrete job event.
The Euler damping factor is 1−D_eff×dt_sub/(2H); its recorded range tests explicit-Euler damping stability at the fixed forcing, not the fidelity of the forcing or plant parameters.
#### Ten evenly spaced invalid ticks: curtailment_positive
Full-precision scalar values; turbine column is total output / current on-bus minimum-stable total. Per-unit output/minimum/state is in the CSV `turbines_output_min_state` column.
|tick|time s|Hz|forcing MW|curtail MW|abs(F−C) MW|defect MW|BESS MW|GT MW / min|diesel MW|H|S MVA|last df/dt|dt_sub / n|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|213|1065.0|70.13551986008387|8.965449895398807|8.965449895398807|0.0|0.0|-0.04484759928800486|17.5 / 17.5|0.0|4.0|58.82352941176471|1.0117779608336113|0.01 / 500|
|1519|7595.0|134.6877369951724|10.79743498569412|10.79743498569412|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|-0.25520175667904654|0.01 / 500|
|2825|14125.0|129.43790812862255|14.141548609609925|14.141548609609925|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|0.024919518632855686|0.01 / 500|
|4130|20650.0|111.01986030380702|6.011366104493021|6.011366104493021|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|0.07690433055750967|0.01 / 500|
|5436|27180.0|147.27450918898785|6.830420133597066|6.830420133597066|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|-0.15454441324158896|0.01 / 500|
|8597|42985.0|152.74242178870944|11.870671254690652|11.870671254690652|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|0.08180598395346617|0.01 / 500|
|12505|62525.0|145.27213825027914|14.387103287741375|14.387103287741375|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|-0.0877117906535374|0.01 / 500|
|14668|73340.0|99.3164265419298|4.818640000025095|4.818640000025095|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|5.744426729137331e-05|0.01 / 500|
|15974|79870.0|124.78250129197464|13.786503279455545|13.786503279455545|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|0.08110870055868258|0.01 / 500|
|17280|86400.0|165.0352297423482|13.484856494909097|13.484856494909097|0.0|0.0|-0.0|17.5 / 17.5|0.0|4.0|58.82352941176471|-0.010012052774677205|0.01 / 500|
#### Ten evenly spaced invalid ticks: curtailment_zero
Full-precision scalar values; turbine column is total output / current on-bus minimum-stable total. Per-unit output/minimum/state is in the CSV `turbines_output_min_state` column.
|tick|time s|Hz|forcing MW|curtail MW|abs(F−C) MW|defect MW|BESS MW|GT MW / min|diesel MW|H|S MVA|last df/dt|dt_sub / n|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|5769|28845.0|136.7977526854928|0.0|0.0|0.0|0.0|1.9324878695627845|17.5 / 17.5|0.0|4.0|58.82352941176471|-0.44880075769858485|0.01 / 500|
|6249|31245.0|35.36565700665469|0.0|0.0|0.0|0.0|29.0|65.45644820544233 / 35.0|0.0|4.0|117.64705882352942|0.015520488729864623|0.01 / 500|
|7582|37910.0|24.617238765543583|0.0|0.0|0.0|0.0|29.0|63.473336396116665 / 26.25|0.0|4.0|88.23529411764707|0.07141106371858665|0.01 / 500|
|8850|44250.0|135.3632675939523|0.0|0.0|0.0|0.0|16.07142538838759|26.25 / 26.25|0.0|4.0|88.23529411764707|-0.16090030210680767|0.01 / 500|
|9104|45520.0|38.18377224220198|0.0|0.0|0.0|0.0|29.0|58.68295239983199 / 35.0|0.0|4.0|117.64705882352942|0.016704599109576754|0.01 / 500|
|10362|51810.0|79.42560283957877|0.0|0.0|0.0|0.0|17.790657585128685|26.25 / 26.25|0.0|4.0|88.23529411764707|-0.05546162823714015|0.01 / 500|
|11576|57880.0|118.31077826693435|8.881784197001252e-16|0.0|8.881784197001252e-16|8.881784197001252e-16|-14.768193602542084|17.5 / 17.5|0.0|4.0|58.82352941176471|-1.5715049076466396|0.01 / 500|
|11938|59690.0|29.06987298248408|0.0|0.0|0.0|0.0|29.0|57.75909257610665 / 26.25|0.0|4.0|88.23529411764707|0.027303775902867734|0.01 / 500|
|13194|65970.0|129.96852814290125|0.0|0.0|0.0|0.0|13.240539109121947|26.25 / 26.25|0.0|4.0|88.23529411764707|-0.08109379290068666|0.01 / 500|
|13450|67250.0|42.68767552820252|0.0|0.0|0.0|0.0|29.0|65.9548348 / 35.0|0.0|4.0|117.64705882352942|0.019369013919013297|0.01 / 500|
### S10_mit_supercloud_2021-08-11_app: distributions and zero-curtailment causes
```json
{
  "forcing_minus_curtailment_distribution": {
    "n": 5615,
    "min": 0.0,
    "max": 0.0,
    "mean": 0.0,
    "p50": 0.0,
    "p95": 0.0,
    "p99": 0.0,
    "within_1e_9": 5615
  },
  "subgroups": {
    "curtailment_positive/positive/over": 5615,
    "curtailment_zero/zero/over": 1075,
    "curtailment_zero/negative/over": 32,
    "curtailment_zero/negative/under": 446,
    "curtailment_zero/zero/under": 96
  },
  "zero_curtailment_extrema": {
    "h_aggregate": {
      "min": 4.0,
      "max": 4.0
    },
    "s_base_mva": {
      "min": 17.647058823529413,
      "max": 88.23529411764707
    },
    "dt_sub": {
      "min": 0.01,
      "max": 0.01
    },
    "substeps": {
      "min": 500.0,
      "max": 500.0
    },
    "df_dt_last": {
      "min": -12.139504541171434,
      "max": 6.2002958007712525
    },
    "euler_damping_factor": {
      "min": 0.99984375,
      "max": 1.0
    },
    "demand_step_mw": {
      "min": -1.0695631785543824,
      "max": 10.300082400000008
    }
  },
  "new_sync_after_inertia_selection": [],
  "consistency_checks": {
    "raw_forcing_equals_published": true,
    "predicted_served_equals_final_served": true,
    "pre_sink_equals_final_sink": true
  },
  "baseline_physical_balance_failures": 0
}
```

The sign subgroups are mutually exclusive within each curtailment class; overlap with over/under-frequency is printed explicitly. A negative forcing is a current generation deficit; zero forcing with out-of-band f is carried frequency relaxing toward nominal, not a new surplus on that tick. A demand_step_mw is the actual outer-tick change (including cooling lag), not necessarily a discrete job event.
The Euler damping factor is 1−D_eff×dt_sub/(2H); its recorded range tests explicit-Euler damping stability at the fixed forcing, not the fidelity of the forcing or plant parameters.
#### Ten evenly spaced invalid ticks: curtailment_positive
Full-precision scalar values; turbine column is total output / current on-bus minimum-stable total. Per-unit output/minimum/state is in the CSV `turbines_output_min_state` column.
|tick|time s|Hz|forcing MW|curtail MW|abs(F−C) MW|defect MW|BESS MW|GT MW / min|diesel MW|H|S MVA|last df/dt|dt_sub / n|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|1|5.0|71.14198664583199|5.2432878333333335|5.2432878333333335|0.0|0.0|-0.0|5.25 / 5.25|0.0|4.0|17.647058823529413|2.2283973291666666|0.01 / 500|
|3311|16555.0|200.25000035302367|8.25|8.25|0.0|0.0|-18.0|26.25 / 26.25|0.0|4.0|88.23529411764707|0.7012499999999999|0.01 / 500|
|5748|28740.0|78.85968049398787|1.1706719999999997|1.1706719999999997|0.0|0.0|-0.0|10.5 / 10.5|0.0|4.0|35.294117647058826|-0.04592188301278122|0.01 / 500|
|6371|31855.0|75.92113920004546|1.1706719999999997|1.1706719999999997|0.0|0.0|-0.0|10.5 / 10.5|0.0|4.0|35.294117647058826|-7.103484467307908e-13|0.01 / 500|
|9760|48800.0|126.62660089900528|11.670672|11.670672|0.0|0.0|-0.0|21.0 / 21.0|0.0|4.0|70.58823529411765|0.19899935460219909|0.01 / 500|
|10384|51920.0|75.92113920004546|1.1706719999999997|1.1706719999999997|0.0|0.0|-0.0|10.5 / 10.5|0.0|4.0|35.294117647058826|-7.103484467307908e-13|0.01 / 500|
|14601|73005.0|137.6458365972731|5.709264|5.709264|0.0|0.0|-0.0|10.5 / 10.5|0.0|4.0|35.294117647058826|2.403543161610955e-06|0.01 / 500|
|15224|76120.0|134.18532751593716|11.671882483779605|11.671882483779605|0.0|0.0|-0.0|26.25 / 26.25|0.0|4.0|88.23529411764707|-0.013327971236646974|0.01 / 500|
|16410|82050.0|121.21957060213333|11.159631021622422|11.159631021622422|0.0|0.0|-0.0|26.25 / 26.25|0.0|4.0|88.23529411764707|-0.0038495546866018637|0.01 / 500|
|17280|86400.0|96.0000020207384|5.291428800000006|5.291428800000006|0.0|0.0|-0.0|21.0 / 21.0|0.0|4.0|70.58823529411765|-0.00028576622500908755|0.01 / 500|
#### Ten evenly spaced invalid ticks: curtailment_zero
Full-precision scalar values; turbine column is total output / current on-bus minimum-stable total. Per-unit output/minimum/state is in the CSV `turbines_output_min_state` column.
|tick|time s|Hz|forcing MW|curtail MW|abs(F−C) MW|defect MW|BESS MW|GT MW / min|diesel MW|H|S MVA|last df/dt|dt_sub / n|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|110|550.0|213.12623462176654|0.0|0.0|0.0|0.0|5.027867999993628|10.5 / 10.5|0.0|4.0|35.294117647058826|-0.04467921606974423|0.01 / 500|
|1400|7000.0|109.8558576238612|0.0|0.0|0.0|0.0|15.2891121545252|21.0 / 21.0|0.0|4.0|70.58823529411765|-0.668728548773322|0.01 / 500|
|1962|9810.0|99.92747210139743|0.0|0.0|0.0|0.0|17.0|40.12939748851865 / 15.75|0.0|4.0|52.94117647058824|-0.6236128915413764|0.01 / 500|
|3507|17535.0|-47.67529619302894|-16.800494399999963|0.0|16.800494399999963|0.0|0.0|45.0 / 15.75|0.0|4.0|52.94117647058824|-0.6977525608215498|0.01 / 500|
|4153|20765.0|160.55845648594757|0.0|0.0|0.0|0.0|-6.441769589585364|15.75 / 15.75|0.0|4.0|52.94117647058824|-1.553659563809071|0.01 / 500|
|6811|34055.0|-86.1277472786988|0.0|0.0|0.0|0.0|17.0|44.80049439999994 / 15.75|0.0|4.0|52.94117647058824|2.2836028641771864|0.01 / 500|
|8631|43155.0|174.75000016106304|0.0|0.0|0.0|0.0|-15.75|15.75 / 15.75|0.0|4.0|52.94117647058824|0.0|0.01 / 500|
|10544|52720.0|-52.650969346288775|-8.974561761701985|0.0|8.974561761701985|0.0|17.0|30.0 / 10.5|0.0|4.0|35.294117647058826|-0.14716707255310557|0.01 / 500|
|11554|57770.0|-59.72293734349929|-4.300494399999998|0.0|4.300494399999998|0.0|0.0|57.5 / 21.0|0.0|4.0|70.58823529411765|1.4139642979137257|0.01 / 500|
|16703|83515.0|66.37679131351963|0.0|0.0|0.0|0.0|1.3201487999017942|15.75 / 15.75|0.0|4.0|52.94117647058824|-0.09965293504197796|0.01 / 500|
## D3 — scratch-only ledger-formula counterfactual
Exact intervention, just before dynamic forcing is initialized at `P/core/simulation_core.py:3372`: substitute **G_signed_BESS + permitted_import − predicted_D7_served − reconciled_sink**. Equivalently: positive-source generation − BESS_charge + import − served − curtailment. Losses are zero. This does not double-subtract charging.
**Important identification limit:** this is the requested SERVED-load formula, not only `raw_forcing−curtailment`. It removes D7-reported physical shortfall from forcing as well. Therefore disappearance of deficit-driven invalid ticks cannot be credited solely to netting the curtailment sink. The predicted pre-loop D7 served value and reconciled sink were compared against actual post-loop values on EVERY tick (`consistency_checks`); all equal, and FC trips=0 in these cases.
A scratch helper returns the substituted forcing only in the experiment process. No clamp, reset, filtering, threshold or dispatch edit. Source hashes and scratch source location are in each summary; scratch sources are outside the tracked tree and not committed.
|Case|Baseline min/max Hz|CF min/max Hz|Baseline invalid fraction|CF invalid fraction|All other tick channels identical|Energy differences|Fuel channels identical|
|---|---|---|---|---|---|---|---|
|scenario-uneven-multisched-01_baseline|-5.0008668933676752 / 176.43084811383099|60 / 60|0.4861111111111111|0|True|{}|True|
|scenario-uneven-multisched-01_informed|59.534837314959205 / 169.8277840657461|60 / 60|0.42638888888888887|0|True|{}|True|
|scenario-h1-k8s-ray-24h_baseline|17.233729831989471 / 224.93353102420852|60 / 60|0.78692129629629626|0|True|{}|True|
|S10_mit_supercloud_2021-08-11_app|-729.10751180806687 / 998.93305345054637|60 / 60|0.42037037037037039|0|True|{}|True|
The exact other-channel hash excludes only frequency_hz, frequency_valid, frequency_forcing_mw and the four pre-existing nondeterministic/reporting exclusions from the baseline runner. It includes per-unit tick telemetry, SoC, dispatch, starts, served/unserved and curtailment. No energy/fuel change is inferred merely from a rounded headline.
### scenario-uneven-multisched-01_baseline: native metric delta and integrated channels
```json
{
  "study_metric_differences": {
    "invalid_frequency_tick_count": [
      700,
      0
    ],
    "invalid_frequency_fraction": [
      0.4861111111111111,
      0.0
    ]
  },
  "energy_baseline": {
    "p_demand_mw_mwh": 64.55553070163181,
    "p_compute_demand_mw_mwh": 56.69758558100562,
    "p_cooling_demand_mw_mwh": 7.857945120625598,
    "p_served_mw_mwh": 64.20383804369828,
    "p_unserved_mw_mwh": 0.35169265793352056,
    "p_dispatch_curtailed_mw_mwh": 8.136511735180346,
    "p_generation_mw_mwh": 72.34034977887838,
    "turbine_output_mw_mwh": 67.90567076396508,
    "bess_output_mw_mwh": -4.631270456046978,
    "fuel_cell_output_mw_mwh": 0.0,
    "diesel_output_mw_mwh": 9.06594947096269
  },
  "energy_counterfactual": {
    "p_demand_mw_mwh": 64.55553070163181,
    "p_compute_demand_mw_mwh": 56.69758558100562,
    "p_cooling_demand_mw_mwh": 7.857945120625598,
    "p_served_mw_mwh": 64.20383804369828,
    "p_unserved_mw_mwh": 0.35169265793352056,
    "p_dispatch_curtailed_mw_mwh": 8.136511735180346,
    "p_generation_mw_mwh": 72.34034977887838,
    "turbine_output_mw_mwh": 67.90567076396508,
    "bess_output_mw_mwh": -4.631270456046978,
    "fuel_cell_output_mw_mwh": 0.0,
    "diesel_output_mw_mwh": 9.06594947096269
  },
  "turbine_fuel_last_baseline": {
    "gt-spin-01": {
      "load_fuel_mmbtu": 221.11316776332302,
      "no_load_fuel_mmbtu": 2.3999999999999884,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "gt-spin-02": {
      "load_fuel_mmbtu": 203.18717240204253,
      "no_load_fuel_mmbtu": 2.3999999999999884,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "gt-hot-01": {
      "load_fuel_mmbtu": 141.39638923269504,
      "no_load_fuel_mmbtu": 1.7683333333333606,
      "hot_standby_fuel_mmbtu": 0.008680555555555552,
      "start_fuel_mmbtu": 8.0
    },
    "gt-hot-02": {
      "load_fuel_mmbtu": 124.43705357635176,
      "no_load_fuel_mmbtu": 1.6216666666666906,
      "hot_standby_fuel_mmbtu": 0.03055555555555551,
      "start_fuel_mmbtu": 8.0
    }
  },
  "turbine_fuel_last_counterfactual": {
    "gt-spin-01": {
      "load_fuel_mmbtu": 221.11316776332302,
      "no_load_fuel_mmbtu": 2.3999999999999884,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "gt-spin-02": {
      "load_fuel_mmbtu": 203.18717240204253,
      "no_load_fuel_mmbtu": 2.3999999999999884,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "gt-hot-01": {
      "load_fuel_mmbtu": 141.39638923269504,
      "no_load_fuel_mmbtu": 1.7683333333333606,
      "hot_standby_fuel_mmbtu": 0.008680555555555552,
      "start_fuel_mmbtu": 8.0
    },
    "gt-hot-02": {
      "load_fuel_mmbtu": 124.43705357635176,
      "no_load_fuel_mmbtu": 1.6216666666666906,
      "hot_standby_fuel_mmbtu": 0.03055555555555551,
      "start_fuel_mmbtu": 8.0
    }
  },
  "diesel_last_baseline": {
    "diesel_fuel_remaining_gal": 10935.741581084352,
    "diesel_fuel_runtime_hours_remaining": 47.54670252645371
  },
  "diesel_last_counterfactual": {
    "diesel_fuel_remaining_gal": 10935.741581084352,
    "diesel_fuel_runtime_hours_remaining": 47.54670252645371
  },
  "native_study_metrics_baseline": {
    "tick_count": 1440,
    "invalid_frequency_tick_count": 700,
    "invalid_frequency_fraction": 0.4861111111111111,
    "protection_configured": false,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 690.133782974,
      "no_load_fuel_mmbtu": 8.19,
      "hot_standby_fuel_mmbtu": 0.039236111,
      "start_fuel_mmbtu": 16.0
    },
    "turbine_fuel_mmbtu": 714.363019086,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 2,
      "measured_event_count": 2,
      "measured_start_fuel_mmbtu": 16.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 8.136511735,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 291.229346912,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 287.502680246,
      "no_load_fuel_mmbtu": 3.726666667,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 93.186666667,
      "gt-spin-02": 92.778235801,
      "gt-hot-01": 54.624513889,
      "gt-hot-02": 50.639930556
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 85.443185219,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 29.816221037,
      "gt-spin-02": 29.711129581,
      "gt-hot-01": 14.277890997,
      "gt-hot-02": 11.637943604
    },
    "unserved_mwh": 0.351692658,
    "peak_unserved_mw": 22.309362466,
    "served_mwh": 64.203838044,
    "unserved_intervals": [
      {
        "start_sim_time_s": 325.0,
        "end_sim_time_s": 465.0,
        "peak_unserved_mw": 22.30936246553462
      },
      {
        "start_sim_time_s": 1850.0,
        "end_sim_time_s": 1855.0,
        "peak_unserved_mw": 4.628919357798523
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 64.203838044,
      "unserved_demand_mwh": 0.351692658
    },
    "bess_soc_min": 0.746789342,
    "bess_soc_max": 0.999999999,
    "bess_soc_final": 0.999999999,
    "commitment": {
      "distinct_event_count": 8,
      "visible_distinct_event_count": 8,
      "suppressed_repeat_count": 0,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 0,
      "reserve_floor_distinct_event_count": 0,
      "reserve_floor_visible_distinct_event_count": 0,
      "reserve_floor_suppressed_repeat_count": 0,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 0,
      "miss_peak_mw": 0.0
    },
    "compute_trace_sha256": "fb3a32d783d0a61ddd2cb8ec7bfbe0204712a2c6f6f9398ef60932160dafa54b",
    "compute_trace_count": 1440,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 690.133782974,
          "no_load_fuel_mmbtu": 8.19,
          "hot_standby_fuel_mmbtu": 0.039236111,
          "start_fuel_mmbtu": 16.0
        },
        "fuel_mmbtu": 714.363019086,
        "unserved_mwh": 0.351692658,
        "curtailed_mwh": 8.136511735,
        "bess_soc_end": 0.999999999
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "nonfrequency_hash_baseline": "c72eb2a1fc1ba90c70e61cc571cbc310040346e195ffb16cbf4f20b4dc875cf5",
  "nonfrequency_hash_counterfactual": "c72eb2a1fc1ba90c70e61cc571cbc310040346e195ffb16cbf4f20b4dc875cf5"
}
```

### scenario-uneven-multisched-01_informed: native metric delta and integrated channels
```json
{
  "study_metric_differences": {
    "invalid_frequency_tick_count": [
      614,
      0
    ],
    "invalid_frequency_fraction": [
      0.4263888888888889,
      0.0
    ]
  },
  "energy_baseline": {
    "p_demand_mw_mwh": 64.55553070163181,
    "p_compute_demand_mw_mwh": 56.69758558100562,
    "p_cooling_demand_mw_mwh": 7.857945120625598,
    "p_served_mw_mwh": 64.53481162799633,
    "p_unserved_mw_mwh": 0.020719073635471947,
    "p_dispatch_curtailed_mw_mwh": 5.278943187678263,
    "p_generation_mw_mwh": 69.813754815675,
    "turbine_output_mw_mwh": 65.3783308230718,
    "bess_output_mw_mwh": -4.035687118507102,
    "fuel_cell_output_mw_mwh": 0.0,
    "diesel_output_mw_mwh": 8.471111111111284
  },
  "energy_counterfactual": {
    "p_demand_mw_mwh": 64.55553070163181,
    "p_compute_demand_mw_mwh": 56.69758558100562,
    "p_cooling_demand_mw_mwh": 7.857945120625598,
    "p_served_mw_mwh": 64.53481162799633,
    "p_unserved_mw_mwh": 0.020719073635471947,
    "p_dispatch_curtailed_mw_mwh": 5.278943187678263,
    "p_generation_mw_mwh": 69.813754815675,
    "turbine_output_mw_mwh": 65.3783308230718,
    "bess_output_mw_mwh": -4.035687118507102,
    "fuel_cell_output_mw_mwh": 0.0,
    "diesel_output_mw_mwh": 8.471111111111284
  },
  "turbine_fuel_last_baseline": {
    "gt-spin-01": {
      "load_fuel_mmbtu": 238.72294294322325,
      "no_load_fuel_mmbtu": 2.3999999999999884,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "gt-spin-02": {
      "load_fuel_mmbtu": 226.69977313774967,
      "no_load_fuel_mmbtu": 2.3999999999999884,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "gt-hot-01": {
      "load_fuel_mmbtu": 97.97408790928004,
      "no_load_fuel_mmbtu": 1.0233333333333434,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 8.0
    },
    "gt-hot-02": {
      "load_fuel_mmbtu": 79.1577631577186,
      "no_load_fuel_mmbtu": 1.02000000000001,
      "hot_standby_fuel_mmbtu": 0.00034722222222222224,
      "start_fuel_mmbtu": 8.0
    }
  },
  "turbine_fuel_last_counterfactual": {
    "gt-spin-01": {
      "load_fuel_mmbtu": 238.72294294322325,
      "no_load_fuel_mmbtu": 2.3999999999999884,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "gt-spin-02": {
      "load_fuel_mmbtu": 226.69977313774967,
      "no_load_fuel_mmbtu": 2.3999999999999884,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "gt-hot-01": {
      "load_fuel_mmbtu": 97.97408790928004,
      "no_load_fuel_mmbtu": 1.0233333333333434,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 8.0
    },
    "gt-hot-02": {
      "load_fuel_mmbtu": 79.1577631577186,
      "no_load_fuel_mmbtu": 1.02000000000001,
      "hot_standby_fuel_mmbtu": 0.00034722222222222224,
      "start_fuel_mmbtu": 8.0
    }
  },
  "diesel_last_baseline": {
    "diesel_fuel_remaining_gal": 10942.582222222689,
    "diesel_fuel_runtime_hours_remaining": 47.57644444444647
  },
  "diesel_last_counterfactual": {
    "diesel_fuel_remaining_gal": 10942.582222222689,
    "diesel_fuel_runtime_hours_remaining": 47.57644444444647
  },
  "native_study_metrics_baseline": {
    "tick_count": 1440,
    "invalid_frequency_tick_count": 614,
    "invalid_frequency_fraction": 0.4263888888888889,
    "protection_configured": false,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 642.554567148,
      "no_load_fuel_mmbtu": 6.843333333,
      "hot_standby_fuel_mmbtu": 0.000347222,
      "start_fuel_mmbtu": 16.0
    },
    "turbine_fuel_mmbtu": 665.398247704,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 2,
      "measured_event_count": 2,
      "measured_start_fuel_mmbtu": 16.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 5.278943188,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 141.143846919,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 139.390513585,
      "no_load_fuel_mmbtu": 1.753333333,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 61.708845913,
      "gt-spin-02": 61.092791773,
      "gt-hot-01": 9.303598121,
      "gt-hot-02": 9.038611111
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 55.021850379,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 26.368861337,
      "gt-spin-02": 26.22775275,
      "gt-hot-01": 1.242273356,
      "gt-hot-02": 1.182962935
    },
    "unserved_mwh": 0.020719074,
    "peak_unserved_mw": 7.52325057,
    "served_mwh": 64.534811628,
    "unserved_intervals": [
      {
        "start_sim_time_s": 335.0,
        "end_sim_time_s": 345.0,
        "peak_unserved_mw": 7.5232505700275
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 64.534811628,
      "unserved_demand_mwh": 0.020719074
    },
    "bess_soc_min": 0.859751061,
    "bess_soc_max": 0.999999999,
    "bess_soc_final": 0.999999999,
    "commitment": {
      "distinct_event_count": 11,
      "visible_distinct_event_count": 11,
      "suppressed_repeat_count": 1374,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 1377,
      "reserve_floor_distinct_event_count": 1377,
      "reserve_floor_visible_distinct_event_count": 1377,
      "reserve_floor_suppressed_repeat_count": 0,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 4,
      "miss_peak_mw": 3.208264895
    },
    "compute_trace_sha256": "fb3a32d783d0a61ddd2cb8ec7bfbe0204712a2c6f6f9398ef60932160dafa54b",
    "compute_trace_count": 1440,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 642.554567148,
          "no_load_fuel_mmbtu": 6.843333333,
          "hot_standby_fuel_mmbtu": 0.000347222,
          "start_fuel_mmbtu": 16.0
        },
        "fuel_mmbtu": 665.398247704,
        "unserved_mwh": 0.020719074,
        "curtailed_mwh": 5.278943188,
        "bess_soc_end": 0.999999999
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "nonfrequency_hash_baseline": "766b066a7c35e1d9824ae2ceddf0391f9d7e0a164f6dea47cdb5a4e7a46af76e",
  "nonfrequency_hash_counterfactual": "766b066a7c35e1d9824ae2ceddf0391f9d7e0a164f6dea47cdb5a4e7a46af76e"
}
```

### scenario-h1-k8s-ray-24h_baseline: native metric delta and integrated channels
```json
{
  "study_metric_differences": {
    "invalid_frequency_tick_count": [
      13598,
      0
    ],
    "invalid_frequency_fraction": [
      0.7869212962962963,
      0.0
    ]
  },
  "energy_baseline": {
    "p_demand_mw_mwh": 368.6761094789402,
    "p_compute_demand_mw_mwh": 335.75858542450953,
    "p_cooling_demand_mw_mwh": 32.91752405443755,
    "p_served_mw_mwh": 367.78173649304125,
    "p_unserved_mw_mwh": 0.8943729858989126,
    "p_dispatch_curtailed_mw_mwh": 187.69013918904406,
    "p_generation_mw_mwh": 555.4718756820172,
    "turbine_output_mw_mwh": 566.4432846278945,
    "bess_output_mw_mwh": -10.971408945932637,
    "fuel_cell_output_mw_mwh": 0.0,
    "diesel_output_mw_mwh": 0.0
  },
  "energy_counterfactual": {
    "p_demand_mw_mwh": 368.6761094789402,
    "p_compute_demand_mw_mwh": 335.75858542450953,
    "p_cooling_demand_mw_mwh": 32.91752405443755,
    "p_served_mw_mwh": 367.78173649304125,
    "p_unserved_mw_mwh": 0.8943729858989126,
    "p_dispatch_curtailed_mw_mwh": 187.69013918904406,
    "p_generation_mw_mwh": 555.4718756820172,
    "turbine_output_mw_mwh": 566.4432846278945,
    "bess_output_mw_mwh": -10.971408945932637,
    "fuel_cell_output_mw_mwh": 0.0,
    "diesel_output_mw_mwh": 0.0
  },
  "turbine_fuel_last_baseline": {
    "gt-spin-01": {
      "load_fuel_mmbtu": 2380.37592884284,
      "no_load_fuel_mmbtu": 28.799999999990046,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "gt-spin-02": {
      "load_fuel_mmbtu": 2314.904536014535,
      "no_load_fuel_mmbtu": 28.799999999990046,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "gt-hot-01": {
      "load_fuel_mmbtu": 746.1469876046626,
      "no_load_fuel_mmbtu": 9.52833333333401,
      "hot_standby_fuel_mmbtu": 2.0111111111113384,
      "start_fuel_mmbtu": 48.0
    },
    "gt-hot-02": {
      "load_fuel_mmbtu": 405.7407638888765,
      "no_load_fuel_mmbtu": 5.301666666666682,
      "hot_standby_fuel_mmbtu": 2.1309027777779472,
      "start_fuel_mmbtu": 68.0
    }
  },
  "turbine_fuel_last_counterfactual": {
    "gt-spin-01": {
      "load_fuel_mmbtu": 2380.37592884284,
      "no_load_fuel_mmbtu": 28.799999999990046,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "gt-spin-02": {
      "load_fuel_mmbtu": 2314.904536014535,
      "no_load_fuel_mmbtu": 28.799999999990046,
      "hot_standby_fuel_mmbtu": 0.0,
      "start_fuel_mmbtu": 0.0
    },
    "gt-hot-01": {
      "load_fuel_mmbtu": 746.1469876046626,
      "no_load_fuel_mmbtu": 9.52833333333401,
      "hot_standby_fuel_mmbtu": 2.0111111111113384,
      "start_fuel_mmbtu": 48.0
    },
    "gt-hot-02": {
      "load_fuel_mmbtu": 405.7407638888765,
      "no_load_fuel_mmbtu": 5.301666666666682,
      "hot_standby_fuel_mmbtu": 2.1309027777779472,
      "start_fuel_mmbtu": 68.0
    }
  },
  "diesel_last_baseline": {
    "diesel_fuel_remaining_gal": 0.0,
    "diesel_fuel_runtime_hours_remaining": null
  },
  "diesel_last_counterfactual": {
    "diesel_fuel_remaining_gal": 0.0,
    "diesel_fuel_runtime_hours_remaining": null
  },
  "native_study_metrics_baseline": {
    "tick_count": 17280,
    "invalid_frequency_tick_count": 13598,
    "invalid_frequency_fraction": 0.7869212962962963,
    "protection_configured": false,
    "interval_seconds": 5.0,
    "fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 5847.168216351,
      "no_load_fuel_mmbtu": 72.43,
      "hot_standby_fuel_mmbtu": 4.142013889,
      "start_fuel_mmbtu": 116.0
    },
    "turbine_fuel_mmbtu": 6039.74023024,
    "fuel_reconciled": true,
    "start_fuel_reconciliation": {
      "release_charged": true,
      "recorded_event_count": 12,
      "measured_event_count": 12,
      "measured_start_fuel_mmbtu": 116.0,
      "tier_sum_mmbtu": null,
      "passed": true
    },
    "dispatch_curtailment_mwh": 187.690139189,
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 3394.620064264,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "load_fuel_mmbtu": 3347.181453153,
      "no_load_fuel_mmbtu": 43.573333333,
      "hot_standby_fuel_mmbtu": 3.865277778,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-spin-01": 1572.100972222,
      "gt-spin-02": 1571.541314265,
      "gt-hot-01": 154.755902778,
      "gt-hot-02": 96.221875
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 1974.088304814,
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-spin-01": 929.988576652,
      "gt-spin-02": 929.873705803,
      "gt-hot-01": 79.517141839,
      "gt-hot-02": 34.708880519
    },
    "unserved_mwh": 0.894372986,
    "peak_unserved_mw": 35.021533247,
    "served_mwh": 367.781736493,
    "unserved_intervals": [
      {
        "start_sim_time_s": 28860.0,
        "end_sim_time_s": 28865.0,
        "peak_unserved_mw": 0.8040054789154141
      },
      {
        "start_sim_time_s": 30650.0,
        "end_sim_time_s": 30680.0,
        "peak_unserved_mw": 26.618853625395175
      },
      {
        "start_sim_time_s": 30995.0,
        "end_sim_time_s": 31000.0,
        "peak_unserved_mw": 0.0014763720534602953
      },
      {
        "start_sim_time_s": 31500.0,
        "end_sim_time_s": 31515.0,
        "peak_unserved_mw": 5.514271219813324
      },
      {
        "start_sim_time_s": 36030.0,
        "end_sim_time_s": 36045.0,
        "peak_unserved_mw": 5.033568781899795
      },
      {
        "start_sim_time_s": 37850.0,
        "end_sim_time_s": 37880.0,
        "peak_unserved_mw": 29.417818249240682
      },
      {
        "start_sim_time_s": 38240.0,
        "end_sim_time_s": 38255.0,
        "peak_unserved_mw": 1.9529208953445476
      },
      {
        "start_sim_time_s": 38700.0,
        "end_sim_time_s": 38715.0,
        "peak_unserved_mw": 5.25701274369851
      },
      {
        "start_sim_time_s": 45050.0,
        "end_sim_time_s": 45080.0,
        "peak_unserved_mw": 32.46833679356759
      },
      {
        "start_sim_time_s": 45440.0,
        "end_sim_time_s": 45455.0,
        "peak_unserved_mw": 0.5423003956669561
      },
      {
        "start_sim_time_s": 45900.0,
        "end_sim_time_s": 45915.0,
        "peak_unserved_mw": 6.887755602473391
      },
      {
        "start_sim_time_s": 52250.0,
        "end_sim_time_s": 52280.0,
        "peak_unserved_mw": 35.021533246572275
      },
      {
        "start_sim_time_s": 52640.0,
        "end_sim_time_s": 52655.0,
        "peak_unserved_mw": 2.804922000000005
      },
      {
        "start_sim_time_s": 57630.0,
        "end_sim_time_s": 57635.0,
        "peak_unserved_mw": 0.7155264052397072
      },
      {
        "start_sim_time_s": 59450.0,
        "end_sim_time_s": 59480.0,
        "peak_unserved_mw": 27.5
      },
      {
        "start_sim_time_s": 59840.0,
        "end_sim_time_s": 59855.0,
        "peak_unserved_mw": 0.741633537511504
      },
      {
        "start_sim_time_s": 60300.0,
        "end_sim_time_s": 60315.0,
        "peak_unserved_mw": 5.328277620981893
      },
      {
        "start_sim_time_s": 66650.0,
        "end_sim_time_s": 66680.0,
        "peak_unserved_mw": 33.2463089774655
      },
      {
        "start_sim_time_s": 67040.0,
        "end_sim_time_s": 67055.0,
        "peak_unserved_mw": 3.1841012001148385
      },
      {
        "start_sim_time_s": 67500.0,
        "end_sim_time_s": 67515.0,
        "peak_unserved_mw": 5.294020684052754
      }
    ],
    "energy_balance": {
      "closure_status": true,
      "max_abs_physical_ledger_defect_mw": 0.0,
      "served_demand_mwh": 367.781736493,
      "unserved_demand_mwh": 0.894372986
    },
    "bess_soc_min": 0.828342155,
    "bess_soc_max": 0.999999999,
    "bess_soc_final": 0.999999998,
    "commitment": {
      "distinct_event_count": 48,
      "visible_distinct_event_count": 48,
      "suppressed_repeat_count": 0,
      "log_complete": true,
      "omitted_record_count": 0,
      "reserve_floor_refusal_count": 0,
      "reserve_floor_distinct_event_count": 0,
      "reserve_floor_visible_distinct_event_count": 0,
      "reserve_floor_suppressed_repeat_count": 0,
      "reserve_floor_log_complete": true,
      "reserve_floor_omitted_record_count": 0,
      "same_unit_restart_within_min_down_window_count": 0
    },
    "forecast": {
      "miss_count": 0,
      "miss_peak_mw": 0.0
    },
    "compute_trace_sha256": "916eb28339ae921141941a8c90069e573e80ef4bf65f2be39cc3e45b8747ccff",
    "compute_trace_count": 17280,
    "daily_breakdown": [
      {
        "day": 1,
        "kind": "weekday",
        "fuel_by_component_mmbtu": {
          "load_fuel_mmbtu": 5847.168216351,
          "no_load_fuel_mmbtu": 72.43,
          "hot_standby_fuel_mmbtu": 4.142013889,
          "start_fuel_mmbtu": 116.0
        },
        "fuel_mmbtu": 6039.74023024,
        "unserved_mwh": 0.894372986,
        "curtailed_mwh": 187.690139189,
        "bess_soc_end": 0.999999998
      }
    ],
    "constraints_valid": true,
    "hard_violations": []
  },
  "nonfrequency_hash_baseline": "c3d6a39d63e786f5abef82b30bc045b122e675bc9fcc07ffc60a93262de0b823",
  "nonfrequency_hash_counterfactual": "c3d6a39d63e786f5abef82b30bc045b122e675bc9fcc07ffc60a93262de0b823"
}
```

### S10_mit_supercloud_2021-08-11_app: native metric delta and integrated channels
```json
{
  "study_metric_differences": {},
  "energy_baseline": {
    "p_demand_mw_mwh": 620.9086288248361,
    "p_compute_demand_mw_mwh": 514.3713154094312,
    "p_cooling_demand_mw_mwh": 106.53731341538261,
    "p_served_mw_mwh": 612.4446369086545,
    "p_unserved_mw_mwh": 8.4639919161834,
    "p_dispatch_curtailed_mw_mwh": 48.51928134810935,
    "p_generation_mw_mwh": 660.9639182568324,
    "turbine_output_mw_mwh": 667.8423099175071,
    "bess_output_mw_mwh": -6.8783916606638815,
    "fuel_cell_output_mw_mwh": 0.0,
    "diesel_output_mw_mwh": 0.0
  },
  "energy_counterfactual": {
    "p_demand_mw_mwh": 620.9086288248361,
    "p_compute_demand_mw_mwh": 514.3713154094312,
    "p_cooling_demand_mw_mwh": 106.53731341538261,
    "p_served_mw_mwh": 612.4446369086545,
    "p_unserved_mw_mwh": 8.4639919161834,
    "p_dispatch_curtailed_mw_mwh": 48.51928134810935,
    "p_generation_mw_mwh": 660.9639182568324,
    "turbine_output_mw_mwh": 667.8423099175071,
    "bess_output_mw_mwh": -6.8783916606638815,
    "fuel_cell_output_mw_mwh": 0.0,
    "diesel_output_mw_mwh": 0.0
  },
  "turbine_fuel_last_baseline": {
    "turbine-0": {
      "load_fuel_mmbtu": null,
      "no_load_fuel_mmbtu": null,
      "hot_standby_fuel_mmbtu": null,
      "start_fuel_mmbtu": null
    },
    "turbine-1": {
      "load_fuel_mmbtu": null,
      "no_load_fuel_mmbtu": null,
      "hot_standby_fuel_mmbtu": null,
      "start_fuel_mmbtu": null
    },
    "turbine-2": {
      "load_fuel_mmbtu": null,
      "no_load_fuel_mmbtu": null,
      "hot_standby_fuel_mmbtu": null,
      "start_fuel_mmbtu": null
    },
    "turbine-3": {
      "load_fuel_mmbtu": null,
      "no_load_fuel_mmbtu": null,
      "hot_standby_fuel_mmbtu": null,
      "start_fuel_mmbtu": null
    },
    "turbine-4": {
      "load_fuel_mmbtu": null,
      "no_load_fuel_mmbtu": null,
      "hot_standby_fuel_mmbtu": null,
      "start_fuel_mmbtu": null
    }
  },
  "turbine_fuel_last_counterfactual": {
    "turbine-0": {
      "load_fuel_mmbtu": null,
      "no_load_fuel_mmbtu": null,
      "hot_standby_fuel_mmbtu": null,
      "start_fuel_mmbtu": null
    },
    "turbine-1": {
      "load_fuel_mmbtu": null,
      "no_load_fuel_mmbtu": null,
      "hot_standby_fuel_mmbtu": null,
      "start_fuel_mmbtu": null
    },
    "turbine-2": {
      "load_fuel_mmbtu": null,
      "no_load_fuel_mmbtu": null,
      "hot_standby_fuel_mmbtu": null,
      "start_fuel_mmbtu": null
    },
    "turbine-3": {
      "load_fuel_mmbtu": null,
      "no_load_fuel_mmbtu": null,
      "hot_standby_fuel_mmbtu": null,
      "start_fuel_mmbtu": null
    },
    "turbine-4": {
      "load_fuel_mmbtu": null,
      "no_load_fuel_mmbtu": null,
      "hot_standby_fuel_mmbtu": null,
      "start_fuel_mmbtu": null
    }
  },
  "diesel_last_baseline": {
    "diesel_fuel_remaining_gal": 0.0,
    "diesel_fuel_runtime_hours_remaining": null
  },
  "diesel_last_counterfactual": {
    "diesel_fuel_remaining_gal": 0.0,
    "diesel_fuel_runtime_hours_remaining": null
  },
  "native_study_metrics_baseline": "App path has no native study metric table; integrated channels above.",
  "nonfrequency_hash_baseline": "8a9415b84b564b706b7ee2e13035902f0dc3da941b74834de398feed7e3ddebe",
  "nonfrequency_hash_counterfactual": "8a9415b84b564b706b7ee2e13035902f0dc3da941b74834de398feed7e3ddebe"
}
```

## D4 — classification and fix direction (NO fix applied)
**(a) Model-consistency defect, deliberately implemented:** all recorded positive-curtailment invalid ticks integrate the same surplus that the physical ledger books as a sink (see exact |F−C| distributions above). The source deliberately calls the sink 'scheduled', but the authoritative ledger subtracts it as consumed power with no corresponding delayed dump-load subtraction in the substeps or on the following tick (:3200–3236, :3482–3489, :3704–3713, :3762). Under the ledger's physical-sink interpretation these two energy routings are inconsistent.
**(b) Documented intent:** `b74830d`/the change record intentionally preserve the pre-dump rotor response. That is a rationale for a finite response transient, NOT evidence that an already fully responding sink can continue accelerating rotors for every subsequent outer tick. No external physical validation was supplied; do not call this an accidental coding omission or silently reverse the historical contract.
**One-sentence fix direction:** use one time-consistent achieved dump-load response in both electromechanical forcing and the physical ledger, retaining the real response transient rather than counting dumped power as sustained rotor surplus.
**(c) Remaining invalid-tick causes and shares:** the following are observed sign/history categories, not additive causal attributions; the inertia and missing-protection settings overlap them.
Positive forcing during an UNDER-frequency tick is recovery, not evidence that curtailment caused that low frequency; the over/under cross-tab in RESULTS.json preserves that distinction.
|Case|C>0, positive F / all invalid|C=0, deficit F / all invalid|C=0, ~zero F (history) / all invalid|C=0, positive F / all invalid|
|---|---|---|---|---|
|scenario-uneven-multisched-01_baseline|637/700 (91.000000000000%)|27/700 (3.857142857143%)|36/700 (5.142857142857%)|0/700 (0.000000000000%)|
|scenario-uneven-multisched-01_informed|446/614 (72.638436482085%)|0/614 (0.000000000000%)|168/614 (27.361563517915%)|0/614 (0.000000000000%)|
|scenario-h1-k8s-ray-24h_baseline|11753/13598 (86.431828210031%)|57/13598 (0.419179291072%)|1788/13598 (13.148992498897%)|0/13598 (0.000000000000%)|
|S10_mit_supercloud_2021-08-11_app|5615/7264 (77.299008810573%)|478/7264 (6.580396475771%)|1171/7264 (16.120594713656%)|0/7264 (0.000000000000%)|
- Deficit transients: raw G−demand can be negative even though D7 later books that gap as unserved. That is a different timing/served-load interpretation issue from curtailment; it is why the requested ledger-formula CF also suppresses under-frequency.
- Frequency memory: with ~zero forcing and positive D_eff, the recurrence relaxes the previous frequency, not instantly back to nominal; `zero_curtailment_extrema` and representative rows show H, S, dt and df/dt.
- Missing protection: all four `audit.site` configurations have null UF/OF/81U thresholds and empty UFLS stages. The dispatch droop correction is skipped (:1542–1588). Protection therefore does not halt the extreme values. It is an overlapping condition, not another disjoint percentage.
- Inertia/base changes: the recorded branch, H and S explain derivative scaling. `new_sync_after_inertia_selection` lists every zero-inertia-list / now-on-bus-MSL mismatch: H was selected at :1471 before advance at :1635. All four lists are empty: this specific mismatch was NOT observed as a cause in these runs (RESULTS.json).
- Sub-stepping: dt_sub=0.01, n=500; recorded Euler damping factors lie strictly between 0 and 1 on the invalid ticks in these runs. This does not support explicit-Euler damping instability as the cause of the sustained excursions; a correctly integrated but inconsistent forcing can still produce invalid frequencies.
- No frequency feedback into ANY other exported tick channel or energy/fuel metric was observed in these four counterfactuals. That is case-specific: configured droop (:1542–1588), FC ride-through (:3492–3502), frequency-triggered renewable curtailment (:1359–1376), UFLS and UF/OF trips (substep protection section) are explicit possible feedbacks elsewhere.

## Files, reproducibility and boundaries
Evidence: RESULTS.json, REPRESENTATIVE_TICKS.json, OBSERVATION_CONTROLS.json, FUNCTION_LOCATIONS.json, TRACE_SOURCES.txt, TRACE_LOADING_SOURCES.txt, PROVENANCE.txt, the eight targeted channels.csv files, eight summary.json files, four comparison.json files, bounded worker stderr and RUN.log. Scratch experiment scripts and scratch core copies are not committed. No application-code/test/scenario/config changes, no workflow restart, no publish/deploy/push. No fix and no Phase 6.
Final application diff/status and evidence checksums are saved in FINAL_INTEGRITY.json. Report-only commit hash is supplied in the completion response rather than self-embedded.
