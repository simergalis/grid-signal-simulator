# D6e E1 — S10 announced-event power probe

Seed 42, `S10_mit_supercloud_2021-08-11`, informed `StudyRunExecutor.run_pair` path. The run was instrumented in memory through 16,805 seconds (3,361 ticks per arm); the artifact writer was disabled, and no per-tick export was retained. Event-level observations are in `tools/dr_isl/d6e/E1_INPUTS.json`.

| Controller evaluation | Announced events | Relevant event | Callback inputs and returned MW | Forecast sample used |
|---:|---:|---|---|---|
| 13,680 s | 8 | `evt-s10-job-00008-start`, 13,678–16,160 s | 4,902 nodes × 10.2 kW (`hopper_8gpu_air`) × PUE 1.03 / 1,000 = **51.500412 MW** | At 13,680 and 13,685 s, active job state power and its forecast contribution are **0 MW**; aggregate forecast sample is 3.803572 MW. |
| 16,775 s | 9 | `evt-s10-job-00009-start`, 16,771–19,973 s | 4,902 nodes × 10.2 kW (`hopper_8gpu_air`) × PUE 1.03 / 1,000 = **51.500412 MW** | At 16,775 and 16,780 s, active job state power and its forecast contribution are **0 MW**; aggregate forecast sample is 4.114098 MW. |

Both starts are already announced (`job_id_in_announced_start_times=true`). The forecast profile uses a 1,200-second window at 5-second steps; the 600-second announcement cutoff includes each event. Each start is 2–4 seconds before the profile window begins, but the job remains active at the first profile samples.

**Cause of the zero:** `runtime/turbine_commitment.py:403–407` calls `_job_state_at(timestamp=sim_time_s, ...)` with `power_for_event=lambda event: 0.0`. `_job_state_at` writes that callback result into the active-job state at `:339–343` and caches the timestamp at `:357–359`. The event remains in the announced-start map (`:437`), and the forecast sums the cached active-job power at `:534–539`; therefore the sample uses 0 MW even though the real callback returns 51.500412 MW. The real callback's profile lookup and formula are `runtime/run_manager.py:1864–1880`.

The callback values labelled `post_forecast_diagnostic` in the JSON are a read-only callback evaluation after each forecast was built; they are not included in, and did not alter, the forecast profile.
