# D6a Hold Diagnosis

**Disposition:** STOP. Read-only diagnosis; no application code, candidate JSON, or tracked S10 scenario was changed for this diagnosis. No SoC was derived and no `(a)+(c)` run was made. The tracked report already records the two pinned 86,400-second RunManager runs per case; this diagnosis used those aggregate summaries and a new 300-tick in-memory RunManager prefix comparison. No full per-tick export was written.

## D6a-H.1(a) — normalized spec identity

Both JSON files were parsed with `ScenarioSpec.model_validate_json` and serialized with `model_dump(mode="json")`, matching the seeder's validation at `P/api/routes/scenarios.py:1454`. The seeder can replace the display name at `:1455–1456`.

With the CPU profile excluded from the comparison, all operational spec fields are identical: GPU workload events/profile, assets, BESS, turbines, cooling parameters, and site configuration. Differences:

| Path | Current S10 | CPU candidate | Classification |
|---|---|---|---|
| `name` | `S10_mit_supercloud_2021-08-11` | `S10 — SuperCloud real GPU day (H100-equivalent shape)` | Display metadata |
| `description` | Existing GPU-day description | Same description plus CPU-load and generator-invocation metadata | Provenance metadata |
| `non_gpu_load_profile_mw` | `null` after validation | Candidate's CPU profile; excluded as requested | The intended new input |

There were no other normalized differences. The generator did not alter the GPU staircase or any physical asset/configuration field.

## D6a-H.1(b) — day totals and first differing tick

Full-day energy values below use the pinned RunManager aggregate summaries `tools/dr_isl/d6/D6A_5_CURRENT_REP1.json` and `D6A_5_CPU_REP1.json`. The GPU-profile integral is `503.06101933333326 MWh` in `tools/dr_isl/d6/D6A_3_CPU_GENERATOR_REPORT.json`; the CPU profile integral is `0.792433206207994 MWh`. Cooling energy is derived using the single demand identity at `P/core/simulation_core.py:1365–1368`: `cooling = total demand − GPU compute − non-GPU IT`.

| Full-day energy (MWh) | Current S10 | CPU candidate (a) |
|---|---:|---:|
| GPU compute | 503.06101933333326 | 503.06101933333326 |
| Cooling, derived | 117.84760949149364 | 41.67396621488290 |
| `p_non_gpu_demand_mw` | 0 (field is `null` when absent) | 0.792433206207994 |
| Total demand | 620.9086288248269 | 545.5274187544242 |
| Served | 612.4446369086435 | 541.3373787346858 |
| Unserved | 8.463991916183423 | 4.190040019738433 |

With the same seed 1729, Python/NumPy seed 1729, wall-clock pin `1792454400.0`, and 5-second ticks, a 300-tick RunManager comparison found **zero GPU-compute differences**. The first GPU-or-cooling difference was **tick 20, sim_time 100 s**:

| Tick-20 field | Current S10 | CPU candidate |
|---|---:|---:|
| GPU compute MW | 0.241638 | 0.241638 |
| Cooling MW | 0.0009621024548434534 | 0.0009656187899719775 |
| `p_non_gpu_demand_mw` | `null` | 0.00007948344432112468 |
| Total demand MW | 0.24260010245484345 | 0.2426831022342931 |
| Served MW | 0.24260010245484345 | 0.2426831022342931 |
| Unserved MW | 0 | 0 |

The initial CPU cooling increment at tick 20 is in the expected additive direction. The full-day decrease in cooling is not: total demand falls by **75.3812100704027 MWh** even though the CPU series adds **0.792433206207994 MWh**.

## D6a-H.1(c) — cooling behavior

`P/core/simulation_core.py:1355–1359` calls `record_job_compute(sim_time, _per_job_draws)` for GPU jobs, then—when the CPU profile exists—calls `record_compute_sample(sim_time, _non_gpu_it_mw)`.

The scalar method is described at `P/core/asset_modules.py:761–775` as a synthetic-envelope path. It tracks the CPU scalar's own previous value (`:777–808`), so it does **not** replace the GPU per-job samples. However, both paths share `CoolingModule._envelopes` (`:698–704`). On a scalar decrease, `:787–805` iterates backward through that shared map and sets `env.end_t = sim_time` without restricting the operation to `_syn_*` envelopes. Thus when GPU draw and CPU load coexist, both are sampled, but a CPU step-down can end a GPU job's envelope.

`CoolingModule.advance` sums the lagged contribution of each envelope at `:848–882`; the prematurely set `end_t` changes the thermal-lag history and cooling output. It does **not** reset or change the configured PUE/cooling parameters. The observed behavior is therefore shared cooling-state mutation, not replacement of the GPU sample. The CPU profile's zero transition is at 527 s, coincident with a generated GPU workload start.

## D6a-H.1(d) — classification

**(i) D6a-X implementation defect.** The generator preserves the GPU event/profile inputs; the added scalar cooling call can mutate GPU job-envelope state. The implicated path is `P/core/simulation_core.py:1355–1359` plus `P/core/asset_modules.py:787–805`, with the resulting cooling consumption at `:863–885`. This is not a generator staircase change.

The diagnosis explains the non-additive outcome; no fix was attempted. The D6a gate remains on hold pending a design decision.
