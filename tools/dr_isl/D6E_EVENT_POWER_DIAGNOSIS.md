# D6e E1 — S10 announced-event power probe

Seed 42, `S10_mit_supercloud_2021-08-11`, informed `StudyRunExecutor.run_pair` path. The run was instrumented in memory through 16,805 seconds (3,361 ticks per arm); the artifact writer was disabled, and no per-tick export was retained. Event-level observations are in `tools/dr_isl/d6e/E1_INPUTS.json`.

| Controller evaluation | Announced events | Relevant event | Callback inputs and returned MW | Forecast sample used |
|---:|---:|---|---|---|
| 13,680 s | 8 | `evt-s10-job-00008-start`, 13,678–16,160 s | 4,902 nodes × 10.2 kW (`hopper_8gpu_air`) × PUE 1.03 / 1,000 = **51.500412 MW** | At 13,680 and 13,685 s, active job state power and its forecast contribution are **0 MW**; aggregate forecast sample is 3.803572 MW. |
| 16,775 s | 9 | `evt-s10-job-00009-start`, 16,771–19,973 s | 4,902 nodes × 10.2 kW (`hopper_8gpu_air`) × PUE 1.03 / 1,000 = **51.500412 MW** | At 16,775 and 16,780 s, active job state power and its forecast contribution are **0 MW**; aggregate forecast sample is 4.114098 MW. |

Both starts are already announced (`job_id_in_announced_start_times=true`). The forecast profile uses a 1,200-second window at 5-second steps; the 600-second announcement cutoff includes each event. Each start is 2–4 seconds before the profile window begins, but the job remains active at the first profile samples.

**Cause of the zero:** `runtime/turbine_commitment.py:403–407` calls `_job_state_at(timestamp=sim_time_s, ...)` with `power_for_event=lambda event: 0.0`. `_job_state_at` writes that callback result into the active-job state at `:339–343` and caches the timestamp at `:357–359`. The event remains in the announced-start map (`:437`), and the forecast sums the cached active-job power at `:534–539`; therefore the sample uses 0 MW even though the real callback returns 51.500412 MW. The real callback's profile lookup and formula are `runtime/run_manager.py:1864–1880`.

The callback values labelled `post_forecast_diagnostic` in the JSON are a read-only callback evaluation after each forecast was built; they are not included in, and did not alter, the forecast profile.

## E3 — scope

The scope probe ran the informed `StudyRunExecutor` path with seed 42 for the 2-hour base demo, H1-24h and H2-24h. It wrapped the forecast's current-job-state lookup and the controller's queue/refusal hooks in memory; no application, test or scenario files were changed. Event-level findings and the first ten occurrences per scenario (time, job ID, callback MW, and controller action/acceptance) are in `tools/dr_isl/d6e/E3_SCOPE.json`.

| Scenario | Controller evaluations | Affected evaluations | Zeroed job/evaluation occurrences | Evaluations with start/stop/trip decision activity | Missing forecast contribution (MW-evaluation sum) | Max in one evaluation | Announcement lead |
|---|---:|---:|---:|---:|---:|---:|---:|
| Base demo, 2 h | 1,440 | 2 | 6 | 2 | 8.454240 | 4.227120 MW | 600 s |
| H1-24h | 17,280 | 122 | 124 | 117 | 5,187.744144 | 43.192267 MW | 600 s |
| H2-24h | 17,280 | 65 | 65 | 65 | 361.788818 | 11.144765 MW | 600 s |

The “missing forecast contribution” sum adds the zeroed jobs' callback MW multiplied by `(1 + cooling_fraction)` at each affected evaluation. It is an MW-evaluation sum, not energy. Each scenario's recorded start-like workload events were on 5-second tick boundaries (base 5/5, H1 24/24, H2 6/6); none fell between ticks. All three reported a 600-second announcement lead.

Base demo and both H studies are affected, so the zeroed-active-job condition is not S10-specific. Decision activity coincided with affected evaluations in all three (2/2, 117/122, and 65/65). The counter records start/stop/trip queue attempts, refusals, or corresponding tick actions; it does not imply every attempt was accepted. The base-demo occurrences show accepted `trip` actions; `runtime/turbine_commitment.py:841` selects `trip` for a hot-standby start candidate. The first ten H1 and H2 records show `stop` attempts refused by the reserve/minimum-run checks at `:858–890`. Thus these affected jobs had positive callback demand, but the controller's forecast current-state contribution for them was zero. See the JSON for exact event IDs, callback MW, actions, acceptance flags and times.
