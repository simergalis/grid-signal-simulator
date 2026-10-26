# IMPL-ISL-30/31 — diagnosis of the two new suite failures

Diagnostic base: `b3deb57` (`IMPL-ISL-30/31: record two-seed full-suite results`).
Scope: read-only diagnosis; no application, test, or scenario files changed.

## Summary

| Test | Classification | Finding |
|---|---|---|
| `test_tc147_stop_refuses_when_post_stop_core_n_minus_one_floor_breaches` | (a) Test premise obsolete by design | It calls forecast evaluation and expects a forecast-origin stop log. IMPL-ISL-30 §3 removes forecast-origin stops. The N-1 floor refusal logic remains on the core decommit proposal path. |
| `test_tc164_shared_identity_and_cache_match_for_every_study_scenario` | (b) Test expectation stale | It computes expected identity from the unprepared scenario, while MCP correctly hashes the seed-prepared timeline. MCP and executor identities match when given the same prepared spec and seed manifest. |

## TC-ISL-147 / H60 stop-floor test

### Isolated result

Command:

`python -m pytest tests/test_addendum_h_phase2b_stage1.py::test_tc147_stop_refuses_when_post_stop_core_n_minus_one_floor_breaches -vv --tb=long`

Result: **failed in 5.70 s**.

Exact failing assertion:

`tests/test_addendum_h_phase2b_stage1.py:262: AssertionError: assert []`

The test first calls `controller.evaluate(...)` at line 260, then expects
`controller.log` to be non-empty, its last record to be a refused stop, and
the reason to contain `"post-stop N-1 reserve floor"` (lines 262–268).
Its fixture is an informed context with an injected 10 MW forecast profile
(lines 231–260). The actual `controller.log` is empty.

### Cause and classification

Classification: **(a), obsolete test premise, not a reported N-1 physics defect.**

The IMPL-ISL-30 stage-1 implementation commit is **`f8deefc`**
(`Update turbine commitment logic and schema definitions`; the stage-1 report
identifies it as the implementation commit). Its change in
`runtime/turbine_commitment.py:1010–1100` removes the forecast-origin stop
branch. The current code states that preload is the proactive action and that
commit/decommit proposals are adjudicated after the core measures the tick
(`runtime/turbine_commitment.py:1076–1080`). Forecast-originated starts remain
possible at `:1081–1100`; forecast-originated stops do not.

This is required by **IMPL-ISL-30 design §3**, which says a stop can occur only
when the core proposes decommit, and the informed adjudicator may veto/delay
that proposal. The corresponding no-forecast-stop assertion is
`tests/test_isl30_stage1.py::test_tc_isl_80_forecast_does_not_originate_stop`
at lines 121–127.

The N-1 reserve-floor refusal logic still exists on the core proposal path:

- `ForecastDrivenTurbineController.adjudicate_core_proposal()` handles
  `decision.action == "decommit"` and calls `_future_burst_refusal()` at
  `runtime/turbine_commitment.py:1427–1455`.
- `_future_burst_refusal()` computes the post-stop N-1 floor and reserve deficit
  at `:913–920`; when the deficit exceeds the sensitivity it records the
  refusal evidence and returns the N-1 refusal reason if no announced job is
  the trigger, at `:925–989`.
- `tests/test_isl30_stage1.py::test_tc_isl_81_core_decommit_is_vetoed_for_announced_job_in_rts`
  exercises the core-decommit veto for an announced workload at lines 130–153.

There is **not** a direct test found that exercises the N-1-only refusal reason
through a core decommit proposal. TC-ISL-81 exercises the related core-proposal
path for an announced-job/RTS veto, not the no-announced-job N-1-only branch.
TC-ISL-147's current forecast-evaluation setup does not provide that coverage.

### Proposed test-only correction (not applied)

Change TC-ISL-147's setup to call `adjudicate_core_proposal()` with an explicit
`decommit` proposal and an injected forecast/capacity state that makes the
post-stop N-1 floor exceed remaining turbine capacity, with no announced job
trigger. Assert the proposal is vetoed and the floor/refusal evidence values
are recorded. Keep forecast-origin stop absence covered separately by
TC-ISL-80/TC-ISL-133.

## TC-ISL-164 / MCP identity-cache test

### Isolated result

Command:

`python -m pytest tests/test_mcp_server.py::test_tc164_shared_identity_and_cache_match_for_every_study_scenario -vv --tb=long`

Result: **failed in 5.73 s**.

Exact failing assertion at `tests/test_mcp_server.py:797`:

`record["identity_digest"] == identity.digest`

For the first mismatching case, the assertion values were:

- expected by the test: `d8ee3d0bcc31483c1d3104f9263480b40e45085fd3db57b24b6e8d57144c4c6e`
- recorded by MCP: `db7dcc1165421b766f277b255594e2b654af64fd3f4d8e2ebe8dac8bcb8b6355`

### Cause and classification

Classification: **(b), stale test expectation; no MCP-versus-executor identity
defect was found.**

The test loops in `STUDY_SCENARIOS` order (`mcp_server/server.py:63–76`) and
computes `identity` at `tests/test_mcp_server.py:777–782` by calling
`isolated._identity()` without `seed_manifest` or a prepared `spec`. That call
expands and hashes the source scenario before synthetic submit times have been
prepared.

The MCP `start_run` path resolves the seed and prepares the timeline before
identity/cache lookup (`mcp_server/server.py:473–492`). The shared
`prepare_workload_timeline()` adds deterministic `submit_time_s` values to
Slurm jobs (`runtime/scenario_factory.py:683–760`). `make_study_run_identity()`
then hashes the workload events and the queue-rule inputs
(`study_harness/executor.py:139–159`). The executor pair path also prepares
the same timeline before running either arm (`study_harness/executor.py:769–775`),
and `_run_mode()` builds an identity from that prepared spec when no identity
was passed (`:471–481`). MCP passes its prepared identity/spec into the
executor (`mcp_server/server.py:537–544, 581–590`).

The implementation that introduced the prepared timeline into identity/cache
construction is **`482fed0`** (`IMPL-ISL-30/31 stage 3: synthesize Slurm queue
warnings before identity and cache`). The identity version is 4 at
`study_harness/executor.py:61–64`; the timeline digest is specifically
`parameter_set.workload_events_sha256` at `:139–144`.

The first mismatch follows the test's loop order: **H2-24h, baseline**. The
only differing payload path between the test's raw expected identity and the
prepared identity is `parameter_set.workload_events_sha256`:

- raw expected timeline digest: `4c444ab6cb4d7b5b59bde99b0e1364658f0fb86e4bf04eff29839f71a1017657`
- prepared timeline digest: `9dff30230675a725fac1840ed47a65ff2cb5b7ea593ab65a85002f5b351efe14`

This produces the expected/recorded identity digests above. The informed H2-24h
case differs for the same sole field (raw identity
`a64c72ff1a80b521ea31a9a0f0b12913c92bdf4dc2e17aa43d27f93998c9ee40`;
prepared identity `8eeaac7e014be1b61322a011d96907301221e7b7add64e594edcacd8753172a1`).

### MCP-versus-executor identity probe at HEAD

For each scenario and mode, MCP's identity construction on the prepared spec
was compared with `make_study_run_identity()` used by the executor on that
same prepared spec and resolved seed. **They match for all 6 scenarios and
both modes (12/12 comparisons).** The table shows the common prepared digest:

| Scenario | Baseline | Informed |
|---|---|---|
| `scenario-h1-k8s-ray-24h` | `03c91b010c2e23c0bb6626ed344787dfd24757d9f5dfc4087da944d209f3cd1a` | `efd93e5ab4108864e2b39b2d87c1c4bbd753783a13075a6e07d4ce14c126b665` |
| `scenario-h1-k8s-ray-7d` | `2e9c1e15b9234ee7a6524f336e9cd616caa875a0046ec0ebdef53306a0dc7f28` | `7b5b2c1c8ac3856e827e0e7afa4ee28538e882b7c9e59e79e3c7112a0723bd0a` |
| `scenario-h2-slurm-24h` | `db7dcc1165421b766f277b255594e2b654af64fd3f4d8e2ebe8dac8bcb8b6355` | `8eeaac7e014be1b61322a011d96907301221e7b7add64e594edcacd8753172a1` |
| `scenario-h2-slurm-7d` | `cc17353172a843198dd399d24c278ab0ad3fd14927bd1659de750c1af7b5bd82` | `2f8187a6a03a07d9e605559f7186a37df411b5712a910af2c2e127a3dee31828` |
| `scenario-uneven-multisched-01` | `90f2c1dbf21e9531dc9a98c61e146f784846287e229d4fa8f63475bcee206b9e` | `94d3cf92e07f99d35d4f2ab9cfbeeab73ccd47431b86d783e28706d0023d6ad0` |
| `S10_mit_supercloud_2021-08-11` | `f61160692a34383cfcf3e63dcb9059faaf4631ab3ad124d5eb24b5bd03a3137f` | `d278bb5515c969180cec52fd9d0185a10502f7a1a5e48239a075cc45f1eeead8` |

The raw and prepared digests naturally differ for H2-24h, H2-7d, and the base
demo because the prepared timeline contains synthesized Slurm submit times.
H1 has no synthetic Slurm waits, and S10 retains source-provided submit times,
so the raw and prepared identities match for those scenarios.

### Proposed test-only correction (not applied)

In TC-ISL-164, resolve the seed manifest for the request's expanded spec, call
the shared `prepare_workload_timeline()` before constructing the expected
identity, and pass that manifest and prepared spec to `isolated._identity()`.
Keep the identity-digest and cache-hit assertions; this makes the expected
digest correspond to the exact identity/cache input used by `start_run`.
