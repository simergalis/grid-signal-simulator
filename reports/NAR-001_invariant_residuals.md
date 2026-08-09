# NAR-001 Invariant Residuals

## 1. Units assumed

No field in the source system declares its units. Every assumption this harness makes is listed here so a wrong one is caught in review.

| Field | Assumed unit |
|---|---|
| `admitted_nodes` | count |
| `bess_output_mw` | MW |
| `bess_rated_mw` | MW |
| `bess_soc_fraction` | fraction 0-1 |
| `bess_usable_mwh` | MWh |
| `committed_rated_mw` | MW |
| `d4_balance_defect_mw` | MW |
| `grid_exchange_mw` | MW |
| `kw_per_node` | kW |
| `net_demand_mw` | MW |
| `p_compute_demand_mw` | MW |
| `p_compute_served_mw` | MW |
| `p_compute_unserved_mw` | MW |
| `p_cooling_demand_mw` | MW |
| `p_cooling_served_mw` | MW |
| `p_cooling_unserved_mw` | MW |
| `p_demand_mw` | MW |
| `p_generation_mw` | MW |
| `p_renewable_mw` | MW |
| `p_served_mw` | MW |
| `p_unserved_mw` | MW |
| `rated_cooling_mw` | MW |
| `reserve_floor_mw` | MW |
| `sim_time_seconds` | s |
| `turbine_output_mw` | MW |
| `turbine_units[].output_mw` | MW |
| `turbine_units[].rated_mw` | MW |

Further assumptions: on-bus means `state == 'synchronised'`; `hot_standby` is treated as False when the key is absent from a unit (the report states whether it appeared); I5 integrates trapezoidally.

---

## 2. Runs analysed

| Run | Ticks | Control msgs | Recorder events | Malformed | missed_leading_ticks |
|---|---|---|---|---|---|
| `run-37d6809c8917` | 799 | 1 | 0 | 0 | True |
| `run-8ab655986f11` | 11 | 1 | 0 | 0 | True |
| `run-973f3c70f24e` | 59 | 1 | 0 | 0 | True |
| `run-9e39c38eb00f` | 0 | 0 | 3 | 0 | False |
| `run-c3ba3cab67b6` | 11 | 1 | 0 | 0 | True |
| `run-eb86877c77fc` | 0 | 0 | 3 | 0 | False |

---

## 3. Field availability (preflight)

**`run-37d6809c8917`** — 26 of 29 canonical fields resolved on every tick.

| Field | ok fraction | states |
|---|---|---|
| `admitted_nodes` | 0.00 | {'null': 799} |
| `kube_metrics` | 0.00 | {'null': 799} |
| `kw_per_node` | 0.00 | {'null': 799} |

**`run-8ab655986f11`** — 26 of 29 canonical fields resolved on every tick.

| Field | ok fraction | states |
|---|---|---|
| `admitted_nodes` | 0.00 | {'null': 11} |
| `kube_metrics` | 0.00 | {'null': 11} |
| `kw_per_node` | 0.00 | {'null': 11} |

**`run-973f3c70f24e`** — 26 of 29 canonical fields resolved on every tick.

| Field | ok fraction | states |
|---|---|---|
| `admitted_nodes` | 0.00 | {'null': 59} |
| `kube_metrics` | 0.00 | {'null': 59} |
| `kw_per_node` | 0.00 | {'null': 59} |

**`run-9e39c38eb00f`** — 0 of 29 canonical fields resolved on every tick.

| Field | ok fraction | states |
|---|---|---|
| `admitted_nodes` | 0.00 | {} |
| `bess_output_mw` | 0.00 | {} |
| `bess_rated_mw` | 0.00 | {} |
| `bess_soc_fraction` | 0.00 | {} |
| `bess_usable_mwh` | 0.00 | {} |
| `commitment_action` | 0.00 | {} |
| `committed_rated_mw` | 0.00 | {} |
| `d4_balance_defect_mw` | 0.00 | {} |
| `grid_exchange_mw` | 0.00 | {} |
| `kube_metrics` | 0.00 | {} |
| `kw_per_node` | 0.00 | {} |
| `net_demand_mw` | 0.00 | {} |
| `p_compute_demand_mw` | 0.00 | {} |
| `p_compute_served_mw` | 0.00 | {} |
| `p_compute_unserved_mw` | 0.00 | {} |
| `p_cooling_demand_mw` | 0.00 | {} |
| `p_cooling_served_mw` | 0.00 | {} |
| `p_cooling_unserved_mw` | 0.00 | {} |
| `p_demand_mw` | 0.00 | {} |
| `p_generation_mw` | 0.00 | {} |
| `p_renewable_mw` | 0.00 | {} |
| `p_served_mw` | 0.00 | {} |
| `p_unserved_mw` | 0.00 | {} |
| `rated_cooling_mw` | 0.00 | {} |
| `reserve_floor_mw` | 0.00 | {} |
| `reserve_satisfied` | 0.00 | {} |
| `sim_time_seconds` | 0.00 | {} |
| `turbine_output_mw` | 0.00 | {} |
| `turbine_units` | 0.00 | {} |

**`run-c3ba3cab67b6`** — 26 of 29 canonical fields resolved on every tick.

| Field | ok fraction | states |
|---|---|---|
| `admitted_nodes` | 0.00 | {'null': 11} |
| `kube_metrics` | 0.00 | {'null': 11} |
| `kw_per_node` | 0.00 | {'null': 11} |

**`run-eb86877c77fc`** — 0 of 29 canonical fields resolved on every tick.

| Field | ok fraction | states |
|---|---|---|
| `admitted_nodes` | 0.00 | {} |
| `bess_output_mw` | 0.00 | {} |
| `bess_rated_mw` | 0.00 | {} |
| `bess_soc_fraction` | 0.00 | {} |
| `bess_usable_mwh` | 0.00 | {} |
| `commitment_action` | 0.00 | {} |
| `committed_rated_mw` | 0.00 | {} |
| `d4_balance_defect_mw` | 0.00 | {} |
| `grid_exchange_mw` | 0.00 | {} |
| `kube_metrics` | 0.00 | {} |
| `kw_per_node` | 0.00 | {} |
| `net_demand_mw` | 0.00 | {} |
| `p_compute_demand_mw` | 0.00 | {} |
| `p_compute_served_mw` | 0.00 | {} |
| `p_compute_unserved_mw` | 0.00 | {} |
| `p_cooling_demand_mw` | 0.00 | {} |
| `p_cooling_served_mw` | 0.00 | {} |
| `p_cooling_unserved_mw` | 0.00 | {} |
| `p_demand_mw` | 0.00 | {} |
| `p_generation_mw` | 0.00 | {} |
| `p_renewable_mw` | 0.00 | {} |
| `p_served_mw` | 0.00 | {} |
| `p_unserved_mw` | 0.00 | {} |
| `rated_cooling_mw` | 0.00 | {} |
| `reserve_floor_mw` | 0.00 | {} |
| `reserve_satisfied` | 0.00 | {} |
| `sim_time_seconds` | 0.00 | {} |
| `turbine_output_mw` | 0.00 | {} |
| `turbine_units` | 0.00 | {} |

---

## 4. Residual distributions

### `run-37d6809c8917`

| Invariant | n eval | n skip | max abs | p95 abs | p50 abs | min | max | n>0 | unit |
|---|---|---|---|---|---|---|---|---|---|
| I1 | 799 | 0 | 14.339 | 3.311 | 0.739 | -3.311 | 14.339 | 568 | MW |
| I1d | 799 | 0 | 14.339 | 3.311 | 0.739 | -3.311 | 14.339 | 568 | MW |
| I2a | 799 | 0 | 3.55271e-15 | 8.88178e-16 | 0 | -3.55271e-15 | 1.77636e-15 | 66 | MW |
| I2b | 0 | 799 | — | — | — | — | — | — | — |
| I3_compute | 799 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I3_cooling | 799 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I3_site | 799 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I4_bess | 799 | 0 | 18 | 18 | 18 | -18 | -2 | 0 | MW |
| I4_cooling | 799 | 0 | 1.5875 | 0.35901 | 0.3549 | -1.5875 | -0.3549 | 0 | MW |
| I4_turbine | 3995 | 0 | 7 | 7 | 7 | -7 | -3.2 | 0 | MW |
| I5 | 798 | 1 | 0.0112889 | 0.000651389 | 0 | -0.0111111 | 0.0112889 | 86 | MWh |
| I6_committed | 799 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I6_floor | 799 | 0 | 28.139 | 6.861 | 6.861 | -28.139 | 6.861 | 783 | MW |

**Shape of the evaluated series** (per subject; pooling assets would produce meaningless reversal counts)

| Invariant | subject | first | last | stdev | max step | reversals | monotonic frac | distinct |
|---|---|---|---|---|---|---|---|---|
| I1 | — | 2.4677 | -1.7159 | 2.08996 | 17 | 37 | 0.58 | 32 |
| I1d | — | 2.4677 | -1.7159 | 2.08996 | 17 | 37 | 0.58 | 32 |
| I2a | — | 0 | -8.88178e-16 | 4.44361e-16 | 3.55271e-15 | 36 | 0.52 | 6 |
| I3_compute | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I3_cooling | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I3_site | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I4_bess | bess | -18 | -17.4049 | 2.07552 | 16 | 36 | 0.71 | 55 |
| I4_cooling | cooling | -1.5875 | -0.3549 | 0.192574 | 0.2927 | 0 | 1.00 | 38 |
| I4_turbine | turbine_units[0] | -7 | -3.2 | 1.18799 | 1 | 32 | 0.56 | 5 |
| I4_turbine | turbine_units[1] | -7 | -7 | 1.39493 | 2.8 | 1 | 0.75 | 4 |
| I4_turbine | turbine_units[2] | -7 | -7 | 0 | 0 | 0 | 0.00 | 1 |
| I4_turbine | turbine_units[3] | -7 | -7 | 0 | 0 | 0 | 0.00 | 1 |
| I4_turbine | turbine_units[4] | -7 | -7 | 0 | 0 | 0 | 0.00 | 1 |
| I5 | — | 0 | 0.000386736 | 0.00188036 | 0.0224 | 170 | 0.52 | 88 |
| I6_committed | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I6_floor | — | 1.6323 | 2.461 | 3.54378 | 35 | 47 | 0.63 | 55 |

**Extreme residual per invariant**

One-sided invariants (I4) report the largest signed value, since only exceedance above a rating is a finding; the largest magnitude there would be the most idle asset.

- **I1** largest magnitude 14.339 at sim_time 3675s — terms: {"p_generation_mw": 21.2, "grid_exchange_mw": 0.0, "p_demand_mw": 6.861, "_paths": {"p_generation_mw": "p_generation_mw", "grid_exchange_mw": "grid_exchange_mw", "p_demand_mw": "p_demand_mw"}}
- **I1d** largest magnitude 14.339 at sim_time 3675s — terms: {"residual_i1": 14.338999999999999, "d4_balance_defect_mw": 0.0}
- **I2a** largest magnitude -3.55271e-15 at sim_time 3860s — terms: {"turbine_output_mw": 3.8, "bess_output_mw": 13.3746, "p_renewable_mw": 0.75, "p_generation_mw": 17.9246, "_paths": {"turbine_output_mw": "turbine_output_mw", "bess_output_mw": "bess_output_mw", "p_renewable_mw": "p_renewable_mw", "p_generation_mw": "p_generation_mw"}}
- **I4_bess** largest exceedance -2 at sim_time 3675s (bess) — terms: {"bess_output_mw": 16.0, "bess_rated_mw": 18.0}
- **I4_cooling** largest exceedance -0.3549 at sim_time 335s (cooling) — terms: {"p_cooling_demand_mw": 1.2326, "rated_cooling_mw": 1.5875}
- **I4_turbine** largest exceedance -3.2 at sim_time 3675s (turbine_units[0]) — terms: {"output_mw": 3.8, "rated_mw": 7.0}
- **I5** largest magnitude 0.0112889 at sim_time 3720s — terms: {"dt_s": 5.0, "soc_prev": 0.8717, "soc_now": 0.8689, "bess_usable_mwh": 8.0, "p_avg_mw": 8.0, "_paths": {"bess_soc_fraction": "bess_soc_fraction", "bess_output_mw": "bess_output_mw", "bess_usable_mwh": "bess_usable_mwh", "sim_time_seconds": "sim_time_seconds"}}
- **I6_floor** largest magnitude -28.139 at sim_time 3675s — terms: {"reported_reserve_floor_mw": 42.0, "largest_on_bus_rated_mw": 7.0, "p_demand_mw": 6.861, "net_demand_mw": 5.461}

**Skips by reason**

- **I2b**: kube path unavailable ×799
- **I5**: no predecessor tick ×1

**I6 reconstruction**

- Ticks where reconstructed `floor_violated` disagrees with reported `reserve_satisfied`: **241** (first at sim_time 10s)
- Ticks with `reserve_satisfied == False` alongside `action == 'hold'`: **197** (first at sim_time 20s)

- Reserve-floor demand basis: mean |residual| is 6.44685 using `p_demand_mw` and 2.8931 using `net_demand_mw`. The reported floor is better reproduced by **`net_demand_mw`**.

- `d4_balance_defect_mw` sign convention: **indeterminate** — the declared field is identically zero across the run (mean |delta| 1.45801 either way).

- Constant fields: 193; varying: 660.

---

### `run-8ab655986f11`

| Invariant | n eval | n skip | max abs | p95 abs | p50 abs | min | max | n>0 | unit |
|---|---|---|---|---|---|---|---|---|---|
| I1 | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I1d | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I2a | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I2b | 0 | 11 | — | — | — | — | — | — | — |
| I3_compute | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I3_cooling | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I3_site | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I4_bess | 11 | 0 | 4.997 | 4.9954 | 4.9895 | -4.997 | -4.9895 | 0 | MW |
| I4_cooling | 11 | 0 | 0.0027 | 0.0027 | 0.0027 | -0.0027 | -0.0027 | 0 | MW |
| I4_turbine | 11 | 0 | 10 | 10 | 10 | -10 | -10 | 0 | MW |
| I5 | 10 | 1 | 0.000185417 | 0.000108542 | 1.45833e-05 | -1.45833e-05 | 0.000185417 | 1 | MWh |
| I6_committed | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I6_floor | 11 | 0 | 0.0038 | 0.0034 | 0.0005 | -0.0038 | 0.003 | 9 | MW |

**Shape of the evaluated series** (per subject; pooling assets would produce meaningless reversal counts)

| Invariant | subject | first | last | stdev | max step | reversals | monotonic frac | distinct |
|---|---|---|---|---|---|---|---|---|
| I1 | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I1d | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I2a | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I3_compute | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I3_cooling | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I3_site | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I4_bess | bess | -4.997 | -4.9895 | 0.00233939 | 0.0032 | 0 | 1.00 | 5 |
| I4_cooling | cooling | -0.0027 | -0.0027 | 0 | 0 | 0 | 0.00 | 1 |
| I4_turbine | turbine_units[0] | -10 | -10 | 0 | 0 | 0 | 0.00 | 1 |
| I5 | — | -6.38889e-06 | -1.45833e-05 | 5.96154e-05 | 0.0002 | 2 | 0.83 | 6 |
| I6_committed | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I6_floor | — | 0.003 | 0.0005 | 0.00151084 | 0.0068 | 1 | 0.75 | 5 |

**Extreme residual per invariant**

One-sided invariants (I4) report the largest signed value, since only exceedance above a rating is a finding; the largest magnitude there would be the most idle asset.

- **I4_bess** largest exceedance -4.9895 at sim_time 30s (bess) — terms: {"bess_output_mw": 0.0105, "bess_rated_mw": 5.0}
- **I4_cooling** largest exceedance -0.0027 at sim_time 10s (cooling) — terms: {"p_cooling_demand_mw": 0.0, "rated_cooling_mw": 0.0027}
- **I4_turbine** largest exceedance -10 at sim_time 10s (turbine_units[0]) — terms: {"output_mw": 0.0, "rated_mw": 10.0}
- **I5** largest magnitude 0.000185417 at sim_time 50s — terms: {"dt_s": 5.0, "soc_prev": 0.95, "soc_now": 0.9499, "bess_usable_mwh": 2.0, "p_avg_mw": 0.0105, "_paths": {"bess_soc_fraction": "bess_soc_fraction", "bess_output_mw": "bess_output_mw", "bess_usable_mwh": "bess_usable_mwh", "sim_time_seconds": "sim_time_seconds"}}
- **I6_floor** largest magnitude -0.0038 at sim_time 15s — terms: {"reported_reserve_floor_mw": 0.01, "largest_on_bus_rated_mw": 0.0, "p_demand_mw": 0.0062, "net_demand_mw": 0.0062}

**Skips by reason**

- **I2b**: kube path unavailable ×11
- **I5**: no predecessor tick ×1

**I6 reconstruction**

- Ticks where reconstructed `floor_violated` disagrees with reported `reserve_satisfied`: **0**
- Ticks with `reserve_satisfied == False` alongside `action == 'hold'`: **11** (first at sim_time 10s)

- Reserve-floor demand basis: mean |residual| is 0.00100909 using `p_demand_mw` and 0.00100909 using `net_demand_mw`. The reported floor is better reproduced by **`net_demand_mw`**.

- `d4_balance_defect_mw` sign convention: **indeterminate** — the declared field is identically zero across the run (mean |delta| 0 either way).

- Constant fields: 170; varying: 599.

---

### `run-973f3c70f24e`

| Invariant | n eval | n skip | max abs | p95 abs | p50 abs | min | max | n>0 | unit |
|---|---|---|---|---|---|---|---|---|---|
| I1 | 59 | 0 | 18.0545 | 18.0093 | 17.5784 | -18.0545 | 0 | 0 | MW |
| I1d | 59 | 0 | 18.0545 | 18.0093 | 17.5784 | -18.0545 | 0 | 0 | MW |
| I2a | 59 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I2b | 0 | 59 | — | — | — | — | — | — | — |
| I3_compute | 59 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I3_cooling | 59 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I3_site | 59 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I4_bess | 59 | 0 | 2.1112 | 1 | 1 | -2.1112 | -1 | 0 | MW |
| I4_cooling | 59 | 0 | 5.2247 | 5.2247 | 0.9077 | -5.2247 | -0.6816 | 0 | MW |
| I4_turbine | 59 | 0 | 5 | 5 | 5 | -5 | -5 | 0 | MW |
| I5 | 58 | 1 | 0.000793889 | 0.000177778 | 2.22222e-05 | -0.000177778 | 0.000793889 | 52 | MWh |
| I6_committed | 59 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I6_floor | 59 | 0 | 19.5045 | 19.5043 | 19.2784 | 4.8988 | 19.5045 | 59 | MW |

**Shape of the evaluated series** (per subject; pooling assets would produce meaningless reversal counts)

| Invariant | subject | first | last | stdev | max step | reversals | monotonic frac | distinct |
|---|---|---|---|---|---|---|---|---|
| I1 | — | 0 | -18.0545 | 3.33905 | 5.9884 | 0 | 1.00 | 48 |
| I1d | — | 0 | -18.0545 | 3.33905 | 5.9884 | 0 | 1.00 | 48 |
| I2a | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I3_compute | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I3_cooling | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I3_site | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I4_bess | bess | -2.1112 | -1 | 0.143435 | 1.1112 | 0 | 1.00 | 2 |
| I4_cooling | cooling | -5.2247 | -0.6816 | 2.04587 | 1.0788 | 0 | 1.00 | 41 |
| I4_turbine | turbine_units[0] | -5 | -5 | 0 | 0 | 0 | 0.00 | 1 |
| I5 | — | 0.000793889 | 2.22222e-05 | 0.000119792 | 0.000771667 | 40 | 0.50 | 5 |
| I6_committed | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I6_floor | — | 4.8988 | 19.5045 | 3.00498 | 5.9884 | 0 | 1.00 | 45 |

**Extreme residual per invariant**

One-sided invariants (I4) report the largest signed value, since only exceedance above a rating is a finding; the largest magnitude there would be the most idle asset.

- **I1** largest magnitude -18.0545 at sim_time 300s — terms: {"p_generation_mw": 6.45, "grid_exchange_mw": 0.0, "p_demand_mw": 24.5045, "_paths": {"p_generation_mw": "p_generation_mw", "grid_exchange_mw": "grid_exchange_mw", "p_demand_mw": "p_demand_mw"}}
- **I1d** largest magnitude -18.0545 at sim_time 300s — terms: {"residual_i1": -18.0545, "d4_balance_defect_mw": 0.0}
- **I4_bess** largest exceedance -1 at sim_time 15s (bess) — terms: {"bess_output_mw": 2.0, "bess_rated_mw": 3.0}
- **I4_cooling** largest exceedance -0.6816 at sim_time 300s (cooling) — terms: {"p_cooling_demand_mw": 4.5431, "rated_cooling_mw": 5.2247}
- **I4_turbine** largest exceedance -5 at sim_time 10s (turbine_units[0]) — terms: {"output_mw": 0.0, "rated_mw": 5.0}
- **I5** largest magnitude 0.000793889 at sim_time 15s — terms: {"dt_s": 5.0, "soc_prev": 0.9494, "soc_now": 0.948, "bess_usable_mwh": 2.0, "p_avg_mw": 1.4444, "_paths": {"bess_soc_fraction": "bess_soc_fraction", "bess_output_mw": "bess_output_mw", "bess_usable_mwh": "bess_usable_mwh", "sim_time_seconds": "sim_time_seconds"}}
- **I6_floor** largest magnitude 19.5045 at sim_time 300s — terms: {"reported_reserve_floor_mw": 5.0, "largest_on_bus_rated_mw": 0.0, "p_demand_mw": 24.5045, "net_demand_mw": 20.0545}

**Skips by reason**

- **I2b**: kube path unavailable ×59
- **I5**: no predecessor tick ×1

**I6 reconstruction**

- Ticks where reconstructed `floor_violated` disagrees with reported `reserve_satisfied`: **0**
- Ticks with `reserve_satisfied == False` alongside `action == 'hold'`: **59** (first at sim_time 10s)

- Reserve-floor demand basis: mean |residual| is 17.4612 using `p_demand_mw` and 12.7672 using `net_demand_mw`. The reported floor is better reproduced by **`net_demand_mw`**.

- `d4_balance_defect_mw` sign convention: **indeterminate** — the declared field is identically zero across the run (mean |delta| 15.7163 either way).

- Constant fields: 141; varying: 631.

---

### `run-9e39c38eb00f`

| Invariant | n eval | n skip | max abs | p95 abs | p50 abs | min | max | n>0 | unit |
|---|---|---|---|---|---|---|---|---|---|

**Shape of the evaluated series** (per subject; pooling assets would produce meaningless reversal counts)

| Invariant | subject | first | last | stdev | max step | reversals | monotonic frac | distinct |
|---|---|---|---|---|---|---|---|---|

**I6 reconstruction**

- Ticks where reconstructed `floor_violated` disagrees with reported `reserve_satisfied`: **0**
- Ticks with `reserve_satisfied == False` alongside `action == 'hold'`: **0**

- Constant fields: 0; varying: 0.

---

### `run-c3ba3cab67b6`

| Invariant | n eval | n skip | max abs | p95 abs | p50 abs | min | max | n>0 | unit |
|---|---|---|---|---|---|---|---|---|---|
| I1 | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I1d | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I2a | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I2b | 0 | 11 | — | — | — | — | — | — | — |
| I3_compute | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I3_cooling | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I3_site | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I4_bess | 11 | 0 | 4.997 | 4.9954 | 4.9895 | -4.997 | -4.9895 | 0 | MW |
| I4_cooling | 11 | 0 | 0.0025 | 0.0025 | 0.0025 | -0.0025 | -0.0025 | 0 | MW |
| I4_turbine | 11 | 0 | 10 | 10 | 10 | -10 | -10 | 0 | MW |
| I5 | 10 | 1 | 0.000185417 | 0.000108542 | 1.45833e-05 | -1.45833e-05 | 0.000185417 | 1 | MWh |
| I6_committed | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | MW |
| I6_floor | 11 | 0 | 0.0038 | 0.0034 | 0.0005 | -0.0038 | 0.003 | 9 | MW |

**Shape of the evaluated series** (per subject; pooling assets would produce meaningless reversal counts)

| Invariant | subject | first | last | stdev | max step | reversals | monotonic frac | distinct |
|---|---|---|---|---|---|---|---|---|
| I1 | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I1d | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I2a | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I3_compute | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I3_cooling | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I3_site | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I4_bess | bess | -4.997 | -4.9895 | 0.00233939 | 0.0032 | 0 | 1.00 | 5 |
| I4_cooling | cooling | -0.0025 | -0.0025 | 0 | 0 | 0 | 0.00 | 1 |
| I4_turbine | turbine_units[0] | -10 | -10 | 0 | 0 | 0 | 0.00 | 1 |
| I5 | — | -6.38889e-06 | -1.45833e-05 | 5.96154e-05 | 0.0002 | 2 | 0.83 | 6 |
| I6_committed | — | 0 | 0 | 0 | 0 | 0 | 0.00 | 1 |
| I6_floor | — | 0.003 | 0.0005 | 0.00151084 | 0.0068 | 1 | 0.75 | 5 |

**Extreme residual per invariant**

One-sided invariants (I4) report the largest signed value, since only exceedance above a rating is a finding; the largest magnitude there would be the most idle asset.

- **I4_bess** largest exceedance -4.9895 at sim_time 30s (bess) — terms: {"bess_output_mw": 0.0105, "bess_rated_mw": 5.0}
- **I4_cooling** largest exceedance -0.0025 at sim_time 10s (cooling) — terms: {"p_cooling_demand_mw": 0.0, "rated_cooling_mw": 0.0025}
- **I4_turbine** largest exceedance -10 at sim_time 10s (turbine_units[0]) — terms: {"output_mw": 0.0, "rated_mw": 10.0}
- **I5** largest magnitude 0.000185417 at sim_time 50s — terms: {"dt_s": 5.0, "soc_prev": 0.95, "soc_now": 0.9499, "bess_usable_mwh": 2.0, "p_avg_mw": 0.0105, "_paths": {"bess_soc_fraction": "bess_soc_fraction", "bess_output_mw": "bess_output_mw", "bess_usable_mwh": "bess_usable_mwh", "sim_time_seconds": "sim_time_seconds"}}
- **I6_floor** largest magnitude -0.0038 at sim_time 15s — terms: {"reported_reserve_floor_mw": 0.01, "largest_on_bus_rated_mw": 0.0, "p_demand_mw": 0.0062, "net_demand_mw": 0.0062}

**Skips by reason**

- **I2b**: kube path unavailable ×11
- **I5**: no predecessor tick ×1

**I6 reconstruction**

- Ticks where reconstructed `floor_violated` disagrees with reported `reserve_satisfied`: **0**
- Ticks with `reserve_satisfied == False` alongside `action == 'hold'`: **11** (first at sim_time 10s)

- Reserve-floor demand basis: mean |residual| is 0.00100909 using `p_demand_mw` and 0.00100909 using `net_demand_mw`. The reported floor is better reproduced by **`net_demand_mw`**.

- `d4_balance_defect_mw` sign convention: **indeterminate** — the declared field is identically zero across the run (mean |delta| 0 either way).

- Constant fields: 170; varying: 599.

---

### `run-eb86877c77fc`

| Invariant | n eval | n skip | max abs | p95 abs | p50 abs | min | max | n>0 | unit |
|---|---|---|---|---|---|---|---|---|---|

**Shape of the evaluated series** (per subject; pooling assets would produce meaningless reversal counts)

| Invariant | subject | first | last | stdev | max step | reversals | monotonic frac | distinct |
|---|---|---|---|---|---|---|---|---|

**I6 reconstruction**

- Ticks where reconstructed `floor_violated` disagrees with reported `reserve_satisfied`: **0**
- Ticks with `reserve_satisfied == False` alongside `action == 'hold'`: **0**

- Constant fields: 0; varying: 0.

---

## 5. Invariant notes

- **I1** — Power balance: p_generation_mw + grid_exchange_mw - p_demand_mw. Carries the whole load-service question, since I3 cannot (see below).
- **I1d** — Independent I1 residual minus the system's own d4_balance_defect_mw. Sign convention of the declared field is undocumented; both signs reported.
- **I2a** — Supply summation: turbine + BESS + renewable - p_generation_mw.
- **I2b** — Job attribution: p_compute_demand_mw vs admitted_nodes x kw_per_node.
- **I3_site** — TAUTOLOGY. p_served_mw is defined as p_demand_mw minus cumulative shed and p_unserved_mw is that shed, so the sum is p_demand_mw by construction. Arithmetic-consistency check only; no physics content. Cannot detect under-delivery.
- **I3_compute** — Per-block tri-field. Uses a proportional split, so unlike the site form it can fail if block fractions do not sum to one.
- **I3_cooling** — As I3_compute.
- **I4_turbine** — Signed margin output_mw - rated_mw per unit. Positive is above nameplate.
- **I4_bess** — |bess_output_mw| - bess_rated_mw, both directions.
- **I4_cooling** — p_cooling_demand_mw - rated_cooling_mw.
- **I5** — Storage energy: dSoC x usable_mwh vs integral of BESS power. Trapezoidal primary; rectangular variant in detail.
- **I6_committed** — Recomputed on-bus rated sum vs reported committed_rated_mw. Detail reconstructs floor_violated (never on the wire) and compares it against reported reserve_satisfied.
- **I6_floor** — Recomputed reserve floor vs reported. Both demand bases are computed because the basis used by the commitment path is not identifiable from the wire.

---

## 6. What this run could not determine

- Any invariant showing 0 evaluated records above was not exercised by this data. It is not passing; it is untested.
- Residual magnitudes are reported without tolerances. Tolerances must be set from these distributions, not chosen in advance.
- `p_served_mw` is demand minus commanded shed, not delivered power. A site physically unable to serve its load reports zero unserved until a shed is commanded, so I3 cannot detect under-delivery and I1 is the only load-service check here.
