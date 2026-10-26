# D6h — S10 informed peak trace

## Run and evidence

Ran `StudyRunExecutor.run_pair` for `S10_mit_supercloud_2021-08-11`, seed 42, at HEAD `71423fde44d6c4156cdc6756c220a0c5def36261`. Both arms completed 17,280 ticks; the pair run took 245.252 s. `tools/dr_isl/d6h/PEAK_WINDOW.json` contains the requested side-by-side 5-second rows for `(15,530, 17,330]`—360 rows—plus the controller transition events. The tick scalars were captured from `TickResult` in memory. No full-run tick export or `*.channels.csv` was committed.

The peak match uses absolute tolerance `1e-9 MW` against the reported peak value:

| Arm | Reported peak unserved | Matching ticks |
|---|---:|---|
| Informed | 31.8004944 MW | 17,330–17,420 s, 19 ticks |
| Baseline | 16.8004944 MW | 17,465–17,920 s (92 ticks), and 57,525–57,745 s (45 ticks) |

The exact in-memory maxima were 31.800494399990384 MW (informed) and 16.800494399999998 MW (baseline); the table uses the rounded values from the request.

The peak intervals do not overlap. The run-pair comparison is `FAIL`; the only failed condition is `informed_peak_unserved_no_worse`. The unserved-energy condition and the other eight conditions pass.

## Unit decision behind the 15 MW peak difference

The informed forecast controller stopped turbine-4 at 16,160 s, turbine-3 at 16,165 s, and turbine-2 at 16,170 s. Each transition was accepted with source `forecast_commitment` and reason `forecast peak and minimum support controlled stop over 1200s`. The recorded forecast MW was 0.0 for turbine-4 and 4.114 for turbines-3 and -2. They completed rundown at 16,220, 16,230, and 16,235 s respectively. The event-level records and reasons are in `PEAK_WINDOW.json`.

Baseline did not stop turbine-2 in that sequence. It stopped turbine-4 at 16,650 s and turbine-3 at 16,775 s, while turbine-2 remained synchronized. Turbine-2 is rated 15.0 MW (`config/scenarios/S10_mit_supercloud_2021-08-11.json:2292–2305`).

At the first informed peak-match tick, 17,330 s:

- Both arms' demand was 61.800494399 MW.
- Baseline served 61.800494399 MW with zero unserved: turbines 0, 1, and 2 were synchronized at 15 MW each; BESS output was 16.800494 MW.
- Informed served 30 MW and had 31.800494399 MW unserved: only turbines 0 and 1 were synchronized at 15 MW; turbines 2, 3, and 4 were starting at zero output; BESS output and SoC were both zero.

The difference between the two arms' reported peak maxima is exactly 15.000000 MW, equal to one turbine-2 rating. At the same informed peak tick, however, baseline also has 16.800494 MW of BESS output that the informed arm lacks; thus the full same-tick unserved difference is not attributable to turbine-2 alone.

The informed arm restarted turbine-4 at 17,120 s, turbine-3 at 17,130 s, and turbine-2 at 17,135 s. Turbine-2's restart was accepted as a hot start. Its event log records synchronization at 17,430 s; the first synchronized tick is 17,435 s, and its first positive output (2.5 MW) is at 17,440 s. From the 17,135 s start command to first output is 305 s. In baseline, turbine-2 had synchronized at 1,125 s and remained on bus through the informed peak.

## Start horizon

The forecast controller uses a fixed 360-second horizon: 300-second hot-start lookahead plus 60-second ramp-to-load (`runtime/turbine_commitment.py:20–24, 844–856`; the core-proposal adjudicator uses the same sum at `:1222–1231`). The horizon calculation does not inspect a candidate unit's thermal tier. S10's turbine-2 JSON has `cold_start_s=600`, `hot_start_s=null`, and initial `thermal_state="cold"` (`config/scenarios/S10_mit_supercloud_2021-08-11.json:2292–2305`); 600 + 60 would be 660 seconds for a cold-start planning case.

That cold-start horizon mismatch did **not** explain this peak: the actual restart event was classified `hot`, and the observed time to first output was 305 seconds, within the fixed 360-second horizon. The observed cause was the earlier accepted decommitment of turbine-2, followed by a restart after the load shortage had begun.

Relevant code:

- `runtime/turbine_commitment.py:900–911` queues the forecast-controlled stop with the recorded 1,200-second reason; `:1083–1110` enqueues it as `forecast_commitment`.
- `runtime/turbine_commitment.py:844–856` sets the fixed start horizon and queues a start when forecast peak exceeds synchronized capacity plus BESS allowance.
- `core/asset_modules.py:1073–1091` resolves thermal tier and start duration; `:1093–1116` starts the countdown; `:1218–1225` advances it to synchronization.
- `core/simulation_core.py:4222–4225` places the core commitment action, target, reason, and blocker on each `TickResult`. Forecast-controller transition events are also retained separately in `PEAK_WINDOW.json`.

No simulator, test, or scenario changes were made. No fix was applied.
