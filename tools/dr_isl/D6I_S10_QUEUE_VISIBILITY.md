# D6i — S10 queue visibility

Read-only analysis of `attached_assets/supercloud/slurm-log.csv` for the
2021-08-11 UTC S10 day. No application, test, or scenario files were changed.
This report contains aggregates and the requested high-load job list only; it
does not contain the raw log or a full row-level extract.

## Scope and method

- Used the generator's GPU-job selection: partitions `normal`, `gaia`, and
  `test` (the S10 metadata labels this historical partition selection
  **INFERRED**), GPU TRES IDs 1001/1002, and rows overlapping the UTC day.
  The generator finds 154 jobs overlapping the day; one had started before
  midnight. The queue-wait distribution below covers the 153 whose actual
  `time_start` falls within `[2021-08-11 00:00 UTC, 2021-08-12 00:00 UTC)`.
- Queue wait is raw `time_start - time_submit` in seconds. `time_submit` is
  read from the source CSV; the generator/parser uses `time_eligible` for
  eligibility, which is a different timestamp.
- Mapped jobs to the generator's stable sorted S10 IDs (`s10-job-00001`, etc.).
  Event node counts use the same GPU-to-chassis scale as S10:
  `chassis_per_gpu = (50.0 MW × 1000 / 10.2 kW) / 424 peak GPUs =
  11.5612282649`; node count is `max(1, round(gpus × chassis_per_gpu))`.
  MW-at-start is the S10 callback formula:
  `node_count × 10.2 kW × 1.03 PUE / 1000`.
- Unweighted percentiles use linear interpolation at `(n-1)×q`. MW-weighted
  percentiles use the inverse weighted empirical CDF: the first wait at which
  cumulative per-job MW reaches `q × total per-job MW`. Percentiles are in
  seconds. The MW weights sum to 743.363 MW across these 153 jobs; this is a
  sum of per-job start powers, not a simultaneous demand measurement.

## Queue-wait distribution

| Statistic | By job count | MW-weighted |
|---|---:|---:|
| Minimum | 0 s | 0 s |
| P10 | 0 s | 0 s |
| P25 | 0 s | 412 s |
| Median | 1 s | 2,959 s |
| P75 | 6 s | 8,568 s |
| P90 | 2,846.6 s | 20,842 s |
| Maximum | 26,944 s | 26,944 s |

## Submitted at least the stated time before start

| Minimum queue wait | Jobs | Job share | Sum of start MW | MW share |
|---|---:|---:|---:|---:|
| 5 minutes | 25 / 153 | 16.34% | 619.014 MW | 83.27% |
| 10 minutes | 23 / 153 | 15.03% | 516.013 MW | 69.42% |
| 20 minutes | 23 / 153 | 15.03% | 516.013 MW | 69.42% |
| 30 minutes | 19 / 153 | 12.42% | 461.592 MW | 62.10% |
| 60 minutes | 12 / 153 | 7.84% | 332.347 MW | 44.71% |

## Jobs with at least 10 MW at start

Times are UTC. “MW” is the S10 event-power result, including the 1.03 PUE.

| S10 job ID | Submitted | Started | Queue wait | MW |
|---|---|---|---:|---:|
| `s10-job-00002` | 2021-08-10 23:02:52 | 2021-08-11 00:08:47 | 3,955 s (65m 55s) | 31.098 |
| `s10-job-00003` | 2021-08-10 23:03:36 | 2021-08-11 00:34:52 | 5,476 s (91m 16s) | 31.098 |
| `s10-job-00004` | 2021-08-10 23:04:09 | 2021-08-11 01:05:02 | 7,253 s (120m 53s) | 31.098 |
| `s10-job-00005` | 2021-08-10 23:05:20 | 2021-08-11 01:28:08 | 8,568 s (142m 48s) | 31.098 |
| `s10-job-00006` | 2021-08-10 23:05:55 | 2021-08-11 01:54:27 | 10,112 s (168m 32s) | 31.098 |
| `s10-job-00007` | 2021-08-11 02:39:29 | 2021-08-11 02:39:29 | 0 s | 47.613 |
| `s10-job-00008` | 2021-08-11 03:42:26 | 2021-08-11 03:47:58 | 332 s (5m 32s) | 51.500 |
| `s10-job-00009` | 2021-08-11 03:50:12 | 2021-08-11 04:39:31 | 2,959 s (49m 19s) | 51.500 |
| `s10-job-00012` | 2021-08-11 04:17:28 | 2021-08-11 09:15:03 | 17,855 s (297m 35s) | 51.500 |
| `s10-job-00013` | 2021-08-11 04:21:46 | 2021-08-11 10:09:08 | 20,842 s (347m 22s) | 47.613 |
| `s10-job-00014` | 2021-08-11 04:27:16 | 2021-08-11 11:04:57 | 23,861 s (397m 41s) | 31.098 |
| `s10-job-00015` | 2021-08-11 04:30:42 | 2021-08-11 11:59:46 | 26,944 s (449m 04s) | 15.549 |
| `s10-job-00017` | 2021-08-11 14:11:30 | 2021-08-11 14:34:09 | 1,359 s (22m 39s) | 15.549 |
| `s10-job-00018` | 2021-08-11 14:11:41 | 2021-08-11 14:34:09 | 1,348 s (22m 28s) | 15.549 |
| `s10-job-00019` | 2021-08-11 14:10:58 | 2021-08-11 14:34:09 | 1,391 s (23m 11s) | 15.549 |
| `s10-job-00020` | 2021-08-11 14:11:54 | 2021-08-11 14:51:35 | 2,381 s (39m 41s) | 15.549 |
| `s10-job-00025` | 2021-08-11 15:39:25 | 2021-08-11 15:46:17 | 412 s (6m 52s) | 51.500 |
| `s10-job-00026` | 2021-08-11 15:57:11 | 2021-08-11 16:38:38 | 2,487 s (41m 27s) | 31.098 |
| `s10-job-00027` | 2021-08-11 16:04:25 | 2021-08-11 17:22:56 | 4,711 s (78m 31s) | 15.549 |

## Jobs 00008 and 00009

- `s10-job-00008`: submitted 2021-08-11 03:42:26 UTC (13,346 s from midnight),
  started 03:47:58 (13,678 s), queue wait 332 s, 51.500 MW.
- `s10-job-00009`: submitted 2021-08-11 03:50:12 UTC (13,812 s from midnight),
  started 04:39:31 (16,771 s), queue wait 2,959 s, 51.500 MW.
- At 16,160 s (04:29:20 UTC), job 00009 had already been queued for
  **2,348 s (39m 08s)**.

## Estimated starts and reservations

No. The source has `time_submit`, `time_eligible`, `time_start`, and `time_end`;
`time_start` is the actual start and `time_eligible` is eligibility time. The
CSV header has no estimated-start or reservation field.

## Source references

- `tools/supercloud/make_scenario.py:58–63`: default scale, profile, and
  partitions; `:256–290`: selected GPU rows and ordering; `:447–468`: chassis
  scaling, event MW basis, and synthetic S10 job IDs.
- `tools/supercloud/convert_to_kube_trace.py:8–10, 145–164`: source time/TRES
  interpretation and parsed `time_start` / `time_eligible` fields.
- `tools/dr_isl/d6/S10_2021-08-11_cpu_soc_fuel_candidate.json`: S10 event
  profile, 1.03 PUE, profile and recorded invocation metadata.
