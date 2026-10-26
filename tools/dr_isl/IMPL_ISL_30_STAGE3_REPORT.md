# IMPL-ISL-30/31 — Stage 3 report

## Scope and implementation

Implemented the Stage 3 shared Slurm queue-wait preparation and base/H identity
changes. No scenario files were edited. No full-suite run or acceptance A/B
simulation was run in this stage.

- **Single timeline preparation:** `P/runtime/scenario_factory.py:683–760`
  deep-copies the expanded spec and adds one synthetic `submit_time_s` per
  Slurm job. It uses the earliest start/scale event, then copies that submit
  time to the job's other events. A group with any source-provided submit time
  is left unchanged, preserving S10's observed values (`:716–720`).
- **Scheduler boundary:** only `scheduler_type == "SLURM"` is synthesized
  (`:708–713`). Kubernetes and Ray events are untouched and continue to use
  the existing fallback announcement lead. The Stage 1 cap remains
  `turbine_forecast_announcement_cap_seconds`, default 1,800 seconds in
  `P/api/schemas.py:1762`; without submit data the controller uses the
  configured lead capped by that value (`P/runtime/turbine_commitment.py:302–305`).
- **Deterministic draw:** each job's 64-bit draw is the first eight bytes of a
  SHA-256 keyed digest using the D4 seed-derivation version, resolved root seed,
  `"synthetic_queue_wait"`, rule and CDF versions, stable scenario identity,
  scheduler and job ID (`P/runtime/scenario_factory.py:733–746`). The draw
  selects from the integer cumulative MW-weighted histogram; the same wait is
  applied to every event for that job (`:748–757`).
- **Aggregate source table:** `P/runtime/synthetic_queue_wait_cdf.py:1–53`
  contains only 35 aggregate wait buckets, with aggregate chassis weights and
  job counts; it contains no job IDs or row-level records. The table is
  `PROPOSED_HERE`, based on D6i's one-day S10 sample: 153 in-day jobs and
  70,756 aggregate chassis weight. The source CSV SHA-256 is
  `27259e5b8e6daecd80b7853126af40ba759bc25edc9053fc174ef7a4f186aa01`.
  Weight is proportional to start MW because the sample uses 10.2 kW per
  chassis and PUE 1.03; the recorded chassis/GPU factor is 11.5612282649.
- **Shared run surfaces:** REST/UI scenarios enter
  `build_run_context_from_spec` at `P/api/routes/runs.py:697–718`; the
  preparation call is inside that shared builder at
  `P/runtime/scenario_factory.py:793–802`. Study probes use the same builder
  at `P/study_harness/executor.py:413–430, 480–495`. MCP prepares before
  identity/cache lookup at `P/mcp_server/server.py:473–496`, then passes that
  same prepared spec to `run_mode` at `:581–590`, which reaches the shared
  builder through the executor.
- `WorkloadSignal` carries the optional field at `P/core/models.py:194`;
  `scenario_factory.py:1809–1812` maps it to the signal. Study replay retains
  it in `P/scripts/run_phase2b_stage1.py:180–188`.

## Seed-42 job counts and effective warning

The following are prepared timeline counts, not simulation results. For
Slurm, effective warning is `min(sampled wait, 1,800 s)`. For K8s/Ray, the
existing configured 600-second lead remains in effect.

| Scenario | Start jobs by scheduler | Slurm effective warning, seconds (min / p10 / p25 / median / p75 / p90 / max) | All-job effective warning, seconds (same quantiles) |
|---|---|---|---|
| Base demo | Slurm 1; K8s 2; Ray 2 | 332 / 332 / 332 / 332 / 332 / 332 / 332 | 332 / 332 / 600 / 600 / 600 / 600 / 600 |
| H1-24h | Slurm 0; K8s 12; Ray 12 | no Slurm jobs | 600 / 600 / 600 / 600 / 600 / 600 / 600 |
| H2-24h | Slurm 6 | 0 / 0 / 332 / 1,348 / 1,800 / 1,800 / 1,800 | 0 / 0 / 332 / 1,348 / 1,800 / 1,800 / 1,800 |

The six H2 Slurm warning samples are `[0, 332, 1,348, 1,800, 1,800, 1,800]`
seconds. The base demo's four non-Slurm jobs retain 600 seconds. H1 has no
Slurm jobs, so all 24 starts retain 600 seconds.

## Identity version and digests

`P/study_harness/executor.py:61–64` bumps `STUDY_IDENTITY_VERSION` from 3 to 4
(`PROPOSED_HERE`) because the prepared timeline and queue rule now affect
results. Before cache lookup, base/H identity parameters include the canonical
workload-event SHA-256, submit-time rule version, empirical CDF version,
announcement cap, and resolved root seed (`:107–165`). The digest is over
canonical workload events, including synthetic submit times.

The table compares pre-Stage-3 digests with Stage-3 digests while holding both
commit fields at the same value,
`cd3b72f5e83098b2a657e91dfa1bb041216da3c9`. This isolates the identity payload
change from the ordinary digest change caused by a different engine/harness
commit. Values are identity constructions only; no scenario simulation was
run.

| Scenario | Arm | Identity digest before | Identity digest after | Prepared workload-events SHA-256 |
|---|---|---|---|---|
| Base demo | baseline | `a6896171e978a8e1a7166b027e21190b9960393850acad0cd2602efdbee04dfb` | `486c495ec756312423e4e99899577012ee0c2a30ab0a0d114388e51a5664033b` | `40e6d726a421230c4c6abe2be7122db5a13d8f47da949726dcc90a9c129974b4` |
| Base demo | informed | `418783719c6826ac041f92f0b8d0cb0461cc503e0f878760893bc8bdf464ac4f` | `0a01e4c25fbd26d3c488c40ea9cf451ca93207262b1415399d3dcc145754bc7f` | `40e6d726a421230c4c6abe2be7122db5a13d8f47da949726dcc90a9c129974b4` |
| H1-24h | baseline | `128e243da8dcd46d8a4f8585bf0bd0daa88ff6297aa48a2c6854d4fd64a84746` | `d03390c295f55929468783680c26f94c95dc67bdcf128a22a281958f4105f003` | `bad02ce75ec3fddb091a5a382cab036489d53d3cc15fe709a5d7079ad4712395` |
| H1-24h | informed | `bce06f6478879e38d30318432b883bba043d0594282973e65ba038a25b3ce4ee` | `169979c66d3bd485648f6e7f600022842dc40ee10c38cd739b3478d967ce588a` | `bad02ce75ec3fddb091a5a382cab036489d53d3cc15fe709a5d7079ad4712395` |
| H2-24h | baseline | `7b946766696e7e79e3b18b367cb44d678dd9f15fc3cd3c05d35dc6443fbc37b1` | `d45621aca5addf8a755dd9a5e5d2259418cf6e691b09c8acc45bd7ecfe75a427` | `9dff30230675a725fac1840ed47a65ff2cb5b7ea593ab65a85002f5b351efe14` |
| H2-24h | informed | `7aa5ecca2cc5e7305255bbef1fa8ffdd6a7b4fafcc84ab06e5cd66b967e8c80c` | `b8af95f3ecc1628ed738ac48c32b8f0ccad194993c23da1bec840c30f8f0cafa` | `9dff30230675a725fac1840ed47a65ff2cb5b7ea593ab65a85002f5b351efe14` |

## Tests

Added:

- **TC-ISL-90** — deterministic cross-process keyed waits; one wait per job
  shared across events and both arms.
- **TC-ISL-92** — prepared timeline fields affect identity and cache lookup;
  MCP cache lookup occurs after preparation and a changed timeline misses.
- **TC-ISL-93** — selected baseline physical ticks are unchanged by the
  submit-time-only controller metadata.
- **TC-ISL-94** — only Slurm jobs receive synthetic submits; K8s/Ray remain
  without them; the tracked S10 workload event list and job-00009 submit time
  (`13,812 s`) remain unchanged.

Updated **TC-ISL-72** and **TC-ISL-73** in
`P/tests/test_study_harness.py:785–864` to assert the new base/H timeline
identity contract instead of the superseded no-timeline/pre-change identity
expectations.

Final focused verification:

- Stage 1 regression set plus Stage 3 tests and focused D6e/commitment/fuel
  tests: **64 passed**.
- D6g study-harness/MCP focused selectors (TC-ISL-65–73, applicable tests):
  **8 passed, 47 deselected**.
- `py_compile` passed for all changed Python files.
- One initial TC-ISL-94 test attempt selected the S10 record by `event_id`
  rather than `job_id`; the test lookup was corrected, and the final focused
  run above passed.

## Commits

- Implementation: `482fed0` — `IMPL-ISL-30/31 stage 3: synthesize Slurm queue warnings before identity and cache`
  (shared runtime preparation, aggregate CDF, identity/cache wiring and replay
  field preservation).
- Tests: `c2bb1a0` — `IMPL-ISL-30/31 stage 3: test timeline synthesis and cache identity`
  (TC-ISL-90/92/93/94 and updated TC-ISL-72/73).

No full suite, acceptance A/B simulation, publishing, deployment, or push was
performed. Stage 3 is complete; stop here as requested.
