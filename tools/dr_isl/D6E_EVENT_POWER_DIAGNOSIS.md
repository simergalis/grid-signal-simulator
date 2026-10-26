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

## E4 — start horizon

`runtime/turbine_commitment.py:23–24` defines the defaults as a 300-second hot-start look-ahead and 60-second ramp-to-load allowance; the controller fields use these defaults at `:187–188`. The informed start decision computes `start_horizon = hot_start_lookahead_seconds + ramp_to_load_seconds` at `:833` and checks `forecast.peak_over(start_horizon)` at `:834` before choosing a candidate at `:835–849`. The resulting horizon is **360 seconds for every candidate**. This expression does not read the candidate's thermal state, its configured hot/warm/cold start duration, or its ramp rate.

The scenario's configured tier values show what a thermal-aware horizon would imply if the same 60-second allowance were retained:

| Fleet/configuration | Configured start durations | Start plus 60-second allowance |
|---|---|---|
| S10 `turbine-0` | hot 300 s, warm 360 s, cold 600 s; initial thermal state hot (`config/scenarios/S10_mit_supercloud_2021-08-11.json:2181–2184`) | hot 360 s; warm 420 s; cold 660 s |
| S10 `turbine-1` | hot 300 s, warm 360 s; initial state warm (`:2242–2244`) | warm 420 s |
| S10 `turbine-2` through `turbine-4` | cold 600 s; warm/hot unset; initial state cold (`:2302–2305`, `:2363–2366`, `:2424–2427`) | cold 660 s |
| Base demo and H1/H2 | Base units configure hot 300 s, warm 360 s, cold 600 s, and are initially hot (`config/scenarios/scenario-uneven-multisched-01.json:174–177`) | initially hot 360 s; warm 420 s; cold 660 s |

H1 and H2 compact entries point to the base scenario (`scenario-h1-k8s-ray-24h.json:4–6`; `scenario-h2-slurm-24h.json:4–6`). Their expansion deep-copies that base turbine roster (`runtime/phase2b_reference.py:87–115`), so their configured tiers are the same. The code also has a separate future-burst stop-refusal delay at `runtime/turbine_commitment.py:681–695`; it uses the maximum configured hot/warm/cold duration plus ramp and unload/min-down terms, not the unit's current thermal state. That is not the fixed 360-second start-action horizon.

## E5 — design options for zeroed active-job power

### Why the zero callback is present

`git blame` attributes `runtime/turbine_commitment.py:403–407` to commit `532c7cc04fb54bdf52129a4fa618747114d39408`, titled “Index long-horizon forecast event evaluation” (2026-09-18). That commit adds the `_job_state_at(timestamp=sim_time_s, ...)` call with `lambda event: 0.0` before `_announced_start_times` scans events. There is no comment or commit-body explanation for why the callback is zero. Structurally, it primes/advances the cached timeline while building the announced-start index, but it also writes zero-power active jobs into that cached state, which later profile samples reuse (`:339–343`, `:357–359`, `:529–540`).

The documented double-count controls are elsewhere: `_job_state_at` says its job map prevents overlapping STARTING/SCALE records for one job from being counted twice (`:289–294`), and `_background_samples` explicitly removes known scripted load from measured history (`:449–491`). Therefore “avoid double-counting measured demand” is a plausible inference for the zero callback, not a documented rationale; the recorded commit title only states the timeline-indexing purpose. The same background subtraction is already intended to keep event load out of the historical residual before the forecast adds event power.

### Options

| Option | Design change and double-count risk | Confirmed informed scenarios affected | Tests needed |
|---|---|---|---|
| **A — pass the real callback when building current state** | Replace the zero callback at `:403–407` with the same `power_for_event` used by `forecast()` (`:494–503`, `:529–540`). Thread it into `_announced_start_times` and its callers (`:521–524`, `:697–700`), or avoid that helper's cache-seeding side effect where a callback is unavailable. The principal risk is adding event MW on top of a measured-history residual that still contains that job; the existing `_background_samples` subtraction (`:478–491`) is specifically meant to remove known job power and lagged cooling first. Verify callback and physical job draw agree and that each job is added once. | Forecast profiles change for the observed zeroed-active jobs in S10 (E1), base demo (2 affected evaluations), H1 (122), and H2 (65). Their informed decisions/results may change; baseline arms do not use this informed forecast path. | Unit tests for an event already active at the evaluation, active STARTING/SCALE records, callbacks across multiple profile samples, and job end; assert positive current-state MW appears once, measured residual remains unchanged, and overlapping records are not double-counted. Replay focused informed probes for all four scenarios; verify conventional/baseline arms remain unchanged. |
| **B — separate measured current load from remaining-job projection** | Do not use an already-active job as a new announced-start contribution. Use the latest measured demand for the present component and project only that job's remaining activity into future samples (`:395–438`, `:449–491`, `:521–540`). This requires explicit current-vs-future accounting; `measured_history` is a rolling past window, not a per-job current measurement. Risk: counting the job both in measured demand and its remaining projection, or omitting it when the latest measurement is stale or the event has no matching sample. | The same four informed arms where active event jobs were observed; any other informed run with an active announced event. Baseline arms should be unaffected. | Tests for current measurement freshness, already-active events, remaining duration, scale/end transitions, stale/missing samples, and exact-once demand accounting; scenario-level forecast comparisons for S10/base/H1/H2. |
| **C — reconcile active-job power against measured demand** | Keep the active-job map, but add event MW only to the extent not already represented in the measured-demand decomposition (`:449–491`, `:521–540`). This makes the no-double-count rule explicit but requires attributing aggregate measured load to event jobs and separating non-GPU/base load and lagged cooling. Risk: attribution errors can suppress real workload power or count it twice when measured and event power differ. | The same four informed arms and any other informed runs using the shared forecast. Baseline arms should be unaffected. | Tests with exact, partial, stale, and absent measured/event matches; non-GPU load and cooling isolation; once-only accounting through scale/end; scenario-level comparisons for S10/base/H1/H2. |

**Recommendation:** Option A, with the existing historical subtraction retained and an explicit exact-once regression test. It is the smallest change and uses the event-power callback already supplied to the forecast builder; the current code already removes modeled job power from historical samples before adding projected event power. Do not assume this prevents every mismatch: prove the accounting with the tests above before accepting changed informed results.

Keep the start-horizon issue separate from the active-job power fix. The horizon is an independent decision threshold: changing it alongside forecast MW would make resulting start/stop changes harder to attribute. A separate gated change should decide whether the threshold uses the chosen unit's actual thermal tier and configured start/ramp timing; no such change or simulation was made for this design note.
