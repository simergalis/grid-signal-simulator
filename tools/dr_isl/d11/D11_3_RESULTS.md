# D11.3 paired acceptance evidence

Two repetitions per case, each with a 5225a05 base and isolated D11 candidate. Non-frequency ticks stream through SHA-256 and pairwise comparison; no full tick exports.

|Scenario / arm|Ticks|Hz before|Hz after|Invalid fraction before → after|Non-frequency hash identical|
|---|---:|---|---|---|---|
|scenario-uneven-multisched-01 / baseline|1440|-5.000866893367675–176.430848113831|-5.000866893367675–60.04391555797632|0.4861111111111111 → 0.03680555555555556|True|
|scenario-uneven-multisched-01 / informed|1440|59.534837314959205–169.8277840657461|55.495062375543036–60.29869344972031|0.4263888888888889 → 0.0|True|
|scenario-h1-k8s-ray-24h / baseline|17280|17.23372983198947–224.93353102420852|17.09771681495931–60.271876826116234|0.7869212962962963 → 0.04693287037037037|True|
|scenario-h1-k8s-ray-24h / informed|17280|48.666827290428756–224.93353102420852|48.59156754833297–60.458333516015756|0.7935185185185185 → 0.004398148148148148|True|
|scenario-h2-slurm-24h / baseline|17280|-225.278937529193–245.96773016794788|-239.88626623828412–60.22370565114776|0.9723379629629629 → 0.03177083333333333|True|
|scenario-h2-slurm-24h / informed|17280|60.0–250.44034654726377|11.925776125116506–60.14917658611521|0.9811921296296297 → 0.023842592592592592|True|
|S10_mit_supercloud_2021-08-11 / app|17280|-729.1075118080669–998.9330534505464|-749.6905479257669–60.54595734564584|0.4203703703703704 → 0.034375|True|
|scenario-equinix-sj-1 / app|720|60.0–60.0|60.0–60.0|0.0 → 0.0|True|
|scenario-turbine-01 / app|720|60.0–305.12517226604007|60.0–60.58640692110985|0.6152777777777778 → 0.0|True|
|scenario-hybrid-ai-100mw-addendum-i / app|120|-218.79606450000827–285.92631259085584|-218.79606450000827–60.97955266880781|0.65 → 0.45|True|
|scenario-100mw-fuel-cell-bess-diesel / app|252|60.0–60.0|60.0–60.0|0.0 → 0.0|True|
|scenario-fc100-islanded-v2 / app|264|60.0–60.0|60.0–60.0|0.0 → 0.0|True|
|scenario-fc100-islanded-zero-hot-v2 / app|264|-82.80435199997717–60.0|-82.80435199997717–60.0|0.8106060606060606 → 0.8106060606060606|True|
|demo-islanded-ramp / app|2160|-127.48961154607643–60.0|-127.48961154607643–60.0|0.047685185185185185 → 0.047685185185185185|True|

## Complete non-frequency SHA-256 values

|Scenario / arm|Before = after|
|---|---|
|scenario-uneven-multisched-01 / baseline|`c72eb2a1fc1ba90c70e61cc571cbc310040346e195ffb16cbf4f20b4dc875cf5`|
|scenario-uneven-multisched-01 / informed|`766b066a7c35e1d9824ae2ceddf0391f9d7e0a164f6dea47cdb5a4e7a46af76e`|
|scenario-h1-k8s-ray-24h / baseline|`c3d6a39d63e786f5abef82b30bc045b122e675bc9fcc07ffc60a93262de0b823`|
|scenario-h1-k8s-ray-24h / informed|`958efa040f72ec67186b89a70f8ee984069fa19a961332559db36e83f3be845c`|
|scenario-h2-slurm-24h / baseline|`905a7f9d83cb2492d77bead4bd687f3959f300535f98838b33c384951cb75ca3`|
|scenario-h2-slurm-24h / informed|`49363ec20bc1634542c5b13d1e56a2fba5c035697689a362c50ab7d797f2d97c`|
|S10_mit_supercloud_2021-08-11 / app|`8a9415b84b564b706b7ee2e13035902f0dc3da941b74834de398feed7e3ddebe`|
|scenario-equinix-sj-1 / app|`65f41459bbb89a002473166453aa3792efc7460d210813e4700b7ea27734bd65`|
|scenario-turbine-01 / app|`4287d6a45c254914ffc67d5925ed9949c24a4dcd626a45f180929b7dd5afa7e4`|
|scenario-hybrid-ai-100mw-addendum-i / app|`74f55fca1651deabc7364360b1d0f52941b8564df6e6001be377bc3a3458cfc1`|
|scenario-100mw-fuel-cell-bess-diesel / app|`c6ccccd59d04a3356f651c3f963e7eb4bdfb3367af7ddf9faab63c1c7db87f65`|
|scenario-fc100-islanded-v2 / app|`c3738260c4f18bf43dd2d7284f501386d2756572e74be23beb81b704a154eccb`|
|scenario-fc100-islanded-zero-hot-v2 / app|`aefdc289bec7a9da3c99398716f8549a0eef0bfdf765bd72a1264a95fe44a507`|
|demo-islanded-ramp / app|`88b04757bff6b8a1d88fc2de6a0396f1da203c724f3021cc4f1db1bd97d16ceb`|

## Remaining invalid ticks (candidate)

Classification priority matches ISL19: positive ledger curtailment first, then negative forcing, then approximately zero forcing. The diagnostic 1e-9 MW tolerance is PROPOSED_HERE, analysis-only, never a simulation input. Positive curtailment with zero integrated forcing can represent carried frequency.

|Scenario / arm|Total invalid|Curtailment positive|Deficit forcing|Carried / zero forcing|Other|
|---|---:|---:|---:|---:|---:|
|scenario-uneven-multisched-01 / baseline|53|0|27|26|0|
|scenario-uneven-multisched-01 / informed|0|0|0|0|0|
|scenario-h1-k8s-ray-24h / baseline|811|26|52|733|0|
|scenario-h1-k8s-ray-24h / informed|76|0|4|72|0|
|scenario-h2-slurm-24h / baseline|549|54|166|329|0|
|scenario-h2-slurm-24h / informed|412|51|42|319|0|
|S10_mit_supercloud_2021-08-11 / app|594|0|476|118|0|
|scenario-equinix-sj-1 / app|0|0|0|0|0|
|scenario-turbine-01 / app|0|0|0|0|0|
|scenario-hybrid-ai-100mw-addendum-i / app|54|0|10|44|0|
|scenario-100mw-fuel-cell-bess-diesel / app|0|0|0|0|0|
|scenario-fc100-islanded-v2 / app|0|0|0|0|0|
|scenario-fc100-islanded-zero-hot-v2 / app|214|0|207|7|0|
|demo-islanded-ramp / app|103|0|90|13|0|

## compare_runs (unchanged implementation)

### scenario-uneven-multisched-01/base

```json
{
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
```

### scenario-uneven-multisched-01/candidate

```json
{
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
```

### scenario-h1-k8s-ray-24h/base

```json
{
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
    "baseline_unserved_mwh": 0.894372986,
    "informed_unserved_mwh": 0.124133405,
    "baseline_peak_unserved_mw": 35.021533247,
    "informed_peak_unserved_mw": 20.746308977
  }
}
```

### scenario-h1-k8s-ray-24h/candidate

```json
{
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
    "baseline_unserved_mwh": 0.894372986,
    "informed_unserved_mwh": 0.124133405,
    "baseline_peak_unserved_mw": 35.021533247,
    "informed_peak_unserved_mw": 20.746308977
  }
}
```

### scenario-h2-slurm-24h/base

```json
{
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
    "baseline_unserved_mwh": 5.011418076,
    "informed_unserved_mwh": 0.859772492,
    "baseline_peak_unserved_mw": 44.86838787,
    "informed_peak_unserved_mw": 42.36838787
  }
}
```

### scenario-h2-slurm-24h/candidate

```json
{
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
    "baseline_unserved_mwh": 5.011418076,
    "informed_unserved_mwh": 0.859772492,
    "baseline_peak_unserved_mw": 44.86838787,
    "informed_peak_unserved_mw": 42.36838787
  }
}
```

