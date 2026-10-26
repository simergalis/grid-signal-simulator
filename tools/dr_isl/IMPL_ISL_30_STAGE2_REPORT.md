# IMPL-ISL-30/31 — Stage 2 report

## Result

S10 start events now carry `submit_time_s` from Slurm `time_submit`, in seconds relative to 2021-08-11 00:00:00 UTC. Values before the day origin remain negative. The generator leaves ending events unchanged.

The recorded generation parameters were used: date `2021-08-11`; template `demo-islanded-ramp.json`; peak `50.0 MW`; profile `hopper_8gpu_air`; GPU partitions `normal,gaia,test`; initial SoC `0.9284516364503763`; fuel model `siemens-sgt-400-proxy`; and input SHA-256 `27259e5b8e6daecd80b7853126af40ba759bc25edc9053fc174ef7a4f186aa01`. The existing S10 name and description were preserved. Its embedded historical `generator_commit` remains `fd3bc85c90861844d829edcd5ca7d0110d7bb08c`; the generator code used for this field-only regeneration was `dd411b6f8cd249a305b84ae504694bb6153fd561`.

The generator merge mode requires the regenerated and existing start-event job ID sets to match, then copies only `submit_time_s` onto each matching start event. This preserves all other scenario data and metadata. `profile_slurm_log.py` was not changed; the generator reads `time_submit` directly from the source CSV rows.

## Verification

- S10 has 239 workload events: 154 starts and 85 ends. The parsed JSON comparison found exactly 154 changed paths, all the addition of `workload_events[*].submit_time_s` on start events; no other scenario value or key changed.
- Old scenario SHA-256: `8bf3a8fd3d59469fe762838907b4bf907a6279c4e78474402665f6824571b288`
- New scenario SHA-256: `1fdc5bb95c86b36a7da9ee613c06ed1b07cdf86f5849322d3a46f968398702ee`
- Old `workload_events` SHA-256: `b002ca98f25f1d3f6946343d02564078cd46543190f3aefd26aea56b78523f85`
- New `workload_events` SHA-256: `dda0d21842069984c42bd0f8471c3ac2dd68cc9b6e0177025bc24b604b640953`
- Spot checks:
  - `s10-job-00002`: start `527 s`, submit `-3428 s` (2021-08-10 23:02:52 UTC).
  - `s10-job-00007`: start and submit both `9569 s`.
  - `s10-job-00009`: start `16771 s`, submit `13812 s`.
- Generator tests: `python -m pytest tools/supercloud/test_make_scenario.py -q` — **11 passed**. New test: `TC-ISL-95`, `tools/supercloud/test_make_scenario.py:267–299`.
- No simulator scenario runs were performed.

## Changed code

- `tools/supercloud/make_scenario.py:241–246, 268–297` — retain source submission time relative to the UTC day origin.
- `tools/supercloud/make_scenario.py:464–470` — emit it only on generated start events.
- `tools/supercloud/make_scenario.py:677–711, 774–829` — guarded, matching-ID merge mode; existing scenario content is preserved except for the new field.

## Commits

- `f775f6146c3d5a6b2f05da9fbf7353b0aaf9af1c` — `IMPL-ISL-30 stage 2: carry Slurm submit times through S10 generator`
- `69cf7f0b70847f245890b474a13311584e7a9e26` — `IMPL-ISL-30 stage 2: test S10 submit-time provenance`
- `dd411b6f8cd249a305b84ae504694bb6153fd561` — `IMPL-ISL-30 stage 2: preserve S10 JSON formatting in merge mode`
- `c0d8cacac7fa301ac027e2833531cc024374e94d` — `IMPL-ISL-30 stage 2: add source submit times to S10 events`
