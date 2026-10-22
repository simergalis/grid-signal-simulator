# DR-2026-10-20-ISLAND-COLLAPSE — Phase 3 resumption STOP report

STATUS: STOPPED at B1. NOT finished, NOT validated, no Phase 4.
Base: `134538067d4eb4c2ce14232e483e9a91fd31276b`. Observed HEAD: `5716d223d8623ab2e01b28ebe859dd2e4decc21f`.
`5716d22` automatically checkpointed the earlier crashing candidate; it was NOT a validated implementation commit.
No implementation/report commit was made during this resumption. No publish, deploy or push.

## Stop finding — B1 H2 informed
Observer source: `/tmp/DR-ISL-phase3/check.py:88–104,130–134`; full observer source is appended below.
Physical hash contract: sorted compact JSON plus LF, in tick order; exclusions are exactly advisory_telemetry, fabric_modal, wall_stamp_utc, insufficient_reserve_proposal_id.
Prefix contains ticks 1–10070, strictly before the first BASE rejection at tick 10071.
Fresh BASE prefix: `f4463c9b45ca12ea303b4000525278c63e858766cbc8c0cd9f3255723b2dbda4`.
Candidate repetition 1 prefix: `b83c21c585130e172aa3fd179748a54d917868c70e6a1d0beafc7e9908724ffc`.
Candidate repetition 2 prefix: `b83c21c585130e172aa3fd179748a54d917868c70e6a1d0beafc7e9908724ffc`.
B1 equality = false. The fresh base compact hash also reproduces the saved base hash.
No first-differing-tick or field diagnosis was run after this failed gate. The mismatch is established within the prefix; its precise first tick/field and cause are NOT determined here.
H2 informed's allowed post-rejection metric changes do not waive B1 pre-divergence identity.
H1 tasks were stopped; there is no completed H1 record from this resumption and no certified H1 PASS claim.

## 3.F crash repair and TC-ISL-06
Saved candidate source: `b416122acfa07c59d4a3521a90361d5be775d612:attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:658–660`.
```python
blocked = isinstance(decision.blocked_by, str) and decision.blocked_by.startswith(
    "no eligible turbine:"
)
```
No CommitmentDecision or commitment outcome code was changed in this resumption.
Saved regression: `b416122acfa07c59d4a3521a90361d5be775d612:attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py:107–114`.
The test exercises None, empty string, another reason and a non-string value; each clears the episode flag and emits no log.
Literal pytest result: `5 passed in 4.78s`. TC-ISL-06a,b,c,d and the existing boundary test passed.
JUnit: `tools/dr_isl/PHASE_3_TC06.xml`. Both full base-demo arms ran twice (1440 ticks each); H2 informed ran twice (17280 ticks each), without exception.
These successful runs establish crash repair, not acceptance of the complete D2 candidate.

## B1/B3/B4 — no-rejection scenarios
|Scenario|Ticks|Rejections|Whole physical hash matches saved BASE|Hash|
|---|---:|---:|---|---|
|demo-islanded-ramp|2160|0|True|fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a|
|scenario-100mw-fuel-cell-bess-diesel|252|0|True|565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b|
|scenario-equinix-sj-1|720|0|True|328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84|
|scenario-fc100-islanded-v2|264|0|True|d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3|
|scenario-fc100-islanded-zero-hot-v2|264|0|True|d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2|
|scenario-hybrid-ai-100mw-addendum-i|120|0|True|9377f009785094697116d356ef554985107ce1ee4c92f01c672f4b30b5f7577a|
|scenario-turbine-01|720|0|True|006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a|

## B2 S10 — completed before B1 stop
Ticks: 17280; rejected starts: BASE 1154 (core 1132, pre-staging 22) -> candidate 0.
Prefix before tick 1059: `279f34c055bcc2a6f6a8b09790a33c5112ea60a598a23eb9531b45dbe3f15c3d`, identical to saved BASE `279f34c055bcc2a6f6a8b09790a33c5112ea60a598a23eb9531b45dbe3f15c3d`.
Candidate ineligibility log episodes: 8.
Candidate full trace summary and complete BASE/candidate turbine START attempts:
```json
{
  "candidate_summary": {
    "steps": 17280,
    "collapsed": [],
    "min_soc": 0.0,
    "frequency": [
      -729.1075118080669,
      998.9330534505464
    ],
    "unserved": 10.600341682490331,
    "balance_failures": [],
    "internal_physical_sha256": "0590ededec7f9988b76b441e89cb7c5d0ee5b7ae5e8baff96f0ce634934d8ac1",
    "prefix_sha256": "279f34c055bcc2a6f6a8b09790a33c5112ea60a598a23eb9531b45dbe3f15c3d"
  },
  "base_starts": [
    {
      "tick": 1,
      "sim_time": 0.0,
      "unit": "turbine-1",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": null,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-2",
        "turbine-3",
        "turbine-4"
      ]
    },
    {
      "tick": 107,
      "sim_time": 527.0,
      "unit": "turbine-2",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": null,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-3",
        "turbine-4"
      ]
    },
    {
      "tick": 226,
      "sim_time": 1125.0,
      "unit": "turbine-3",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": null,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-4"
      ]
    },
    {
      "tick": 420,
      "sim_time": 2092.0,
      "unit": "turbine-4",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": null,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    },
    {
      "tick": 1216,
      "sim_time": 6075.0,
      "unit": "turbine-3",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 5175.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-4"
      ]
    },
    {
      "tick": 1375,
      "sim_time": 6867.0,
      "unit": "turbine-4",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": 5050.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    },
    {
      "tick": 2012,
      "sim_time": 10055.0,
      "unit": "turbine-3",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 9155.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-4"
      ]
    },
    {
      "tick": 2072,
      "sim_time": 10355.0,
      "unit": "turbine-4",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 9030.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    },
    {
      "tick": 2906,
      "sim_time": 14525.0,
      "unit": "turbine-4",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 13625.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    },
    {
      "tick": 3549,
      "sim_time": 17740.0,
      "unit": "turbine-3",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 16840.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-4"
      ]
    },
    {
      "tick": 3609,
      "sim_time": 18040.0,
      "unit": "turbine-4",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 16715.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    },
    {
      "tick": 5271,
      "sim_time": 26347.0,
      "unit": "turbine-3",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": 20650.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-4"
      ]
    },
    {
      "tick": 6667,
      "sim_time": 33330.0,
      "unit": "turbine-4",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 20525.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-2",
        "turbine-3"
      ]
    },
    {
      "tick": 6832,
      "sim_time": 34155.0,
      "unit": "turbine-1",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 33255.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-2",
        "turbine-3"
      ]
    },
    {
      "tick": 6892,
      "sim_time": 34455.0,
      "unit": "turbine-3",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 28570.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-2"
      ]
    },
    {
      "tick": 6964,
      "sim_time": 34815.0,
      "unit": "turbine-2",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 26645.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    },
    {
      "tick": 7479,
      "sim_time": 37390.0,
      "unit": "turbine-4",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 36490.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    },
    {
      "tick": 8150,
      "sim_time": 40745.0,
      "unit": "turbine-4",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 39845.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    },
    {
      "tick": 8639,
      "sim_time": 43186.0,
      "unit": "turbine-3",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": 39970.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    },
    {
      "tick": 10491,
      "sim_time": 52449.0,
      "unit": "turbine-2",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": 51195.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-3",
        "turbine-4"
      ]
    },
    {
      "tick": 10550,
      "sim_time": 52745.0,
      "unit": "turbine-3",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 46890.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-4"
      ]
    },
    {
      "tick": 10622,
      "sim_time": 53105.0,
      "unit": "turbine-4",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 43135.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    },
    {
      "tick": 11514,
      "sim_time": 57565.0,
      "unit": "turbine-3",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 56665.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-4"
      ]
    },
    {
      "tick": 11574,
      "sim_time": 57865.0,
      "unit": "turbine-4",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "simulation_core.py:2350",
      "stop_time_s": 56540.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    },
    {
      "tick": 14726,
      "sim_time": 73623.0,
      "unit": "turbine-2",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": 71655.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-3",
        "turbine-4"
      ]
    },
    {
      "tick": 14789,
      "sim_time": 73940.0,
      "unit": "turbine-3",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": 71530.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-4"
      ]
    },
    {
      "tick": 14859,
      "sim_time": 74290.0,
      "unit": "turbine-4",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": 71405.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    },
    {
      "tick": 15530,
      "sim_time": 77642.0,
      "unit": "turbine-2",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": 76700.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-3",
        "turbine-4"
      ]
    },
    {
      "tick": 15621,
      "sim_time": 78099.0,
      "unit": "turbine-3",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": 76575.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-4"
      ]
    },
    {
      "tick": 15810,
      "sim_time": 79044.0,
      "unit": "turbine-4",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": 76450.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    },
    {
      "tick": 16562,
      "sim_time": 82804.0,
      "unit": "turbine-3",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": 81330.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": [
        "turbine-4"
      ]
    },
    {
      "tick": 16720,
      "sim_time": 83593.0,
      "unit": "turbine-4",
      "eligible": true,
      "reason": "eligible",
      "before": "offline",
      "after": "starting",
      "caller": "dispatch.py:617",
      "stop_time_s": 81205.0,
      "t_min_down_s": 900.0,
      "eligible_alternates": []
    }
  ],
  "candidate_starts": [
    {
      "tick": 1,
      "sim_time": 0.0,
      "unit": "turbine-1",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 107,
      "sim_time": 527.0,
      "unit": "turbine-2",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 226,
      "sim_time": 1125.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 420,
      "sim_time": 2092.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 1191,
      "sim_time": 5950.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 1375,
      "sim_time": 6867.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 1915,
      "sim_time": 9569.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 1987,
      "sim_time": 9930.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 2906,
      "sim_time": 14525.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 3524,
      "sim_time": 17615.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 3584,
      "sim_time": 17915.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 5271,
      "sim_time": 26347.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 6662,
      "sim_time": 33303.0,
      "unit": "turbine-2",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 6733,
      "sim_time": 33660.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 6805,
      "sim_time": 34020.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 6877,
      "sim_time": 34380.0,
      "unit": "turbine-1",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 7479,
      "sim_time": 37390.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 7539,
      "sim_time": 37690.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 8150,
      "sim_time": 40745.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 8639,
      "sim_time": 43186.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 9389,
      "sim_time": 46938.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 10491,
      "sim_time": 52449.0,
      "unit": "turbine-2",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 10550,
      "sim_time": 52745.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 10622,
      "sim_time": 53105.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 11489,
      "sim_time": 57440.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 11549,
      "sim_time": 57740.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 12154,
      "sim_time": 60765.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 12517,
      "sim_time": 62576.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 14726,
      "sim_time": 73623.0,
      "unit": "turbine-2",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 14789,
      "sim_time": 73940.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 14859,
      "sim_time": 74290.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 15474,
      "sim_time": 77365.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 15558,
      "sim_time": 77785.0,
      "unit": "turbine-2",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 15621,
      "sim_time": 78099.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 16161,
      "sim_time": 80798.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 16254,
      "sim_time": 81262.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 16779,
      "sim_time": 83890.0,
      "unit": "turbine-4",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    },
    {
      "tick": 16868,
      "sim_time": 84335.0,
      "unit": "turbine-3",
      "reason": "eligible",
      "before": "offline",
      "after": "starting"
    }
  ],
  "ineligibility_episodes": [
    "Commitment engine: no eligible turbine: turbine-3=min_down; turbine-4=min_down at sim_time=5345.0",
    "Commitment engine: no eligible turbine: turbine-3=min_down at sim_time=9865.0",
    "Commitment engine: no eligible turbine: turbine-4=min_down at sim_time=13730.0",
    "Commitment engine: no eligible turbine: turbine-4=min_down at sim_time=16820.0",
    "Commitment engine: no eligible turbine: turbine-4=min_down at sim_time=36595.0",
    "Commitment engine: no eligible turbine: turbine-4=min_down at sim_time=39960.0",
    "Commitment engine: no eligible turbine: turbine-4=min_down; turbine-3=min_down at sim_time=56825.0",
    "Commitment engine: no eligible turbine: turbine-4=min_down at sim_time=59980.0"
  ]
}
```
Empty collapsed list means no TickResult with island_collapsed=true was observed; it is not an assertion of acceptable frequency or power adequacy.

## B5 H2 informed — completed observations, NOT accepted
Fresh BASE compact: `6ae0ce3d7a1b300cd4402fbd640abc67addb953b453075454c39bdefad8b0711`.
Candidate compact (both repetitions): `0def2a33daa2770e5095d8cb63b2c5e7d01ab65c85aaf4db3bd732a89623a3c7`.
Full metric table (native MetricsCollector keys; candidate repetitions agree on every listed metric):
|Metric|BASE|Candidate|
|---|---|---|
|tick_count|17280|17280|
|interval_seconds|5.0|5.0|
|fuel_by_component_mmbtu|{"hot_standby_fuel_mmbtu": 3.761458333, "load_fuel_mmbtu": 5107.722017303, "no_load_fuel_mmbtu": 64.866666667, "start_fuel_mmbtu": 152.0}|{"hot_standby_fuel_mmbtu": 3.761458333, "load_fuel_mmbtu": 5106.733034717, "no_load_fuel_mmbtu": 64.855, "start_fuel_mmbtu": 152.0}|
|turbine_fuel_mmbtu|5328.350142303|5327.34949305|
|fuel_reconciled|true|true|
|start_fuel_reconciliation|{"measured_event_count": 14, "measured_start_fuel_mmbtu": 152.0, "passed": true, "recorded_event_count": 14, "release_charged": true, "tier_sum_mmbtu": null}|{"measured_event_count": 14, "measured_start_fuel_mmbtu": 152.0, "passed": true, "recorded_event_count": 14, "release_charged": true, "tier_sum_mmbtu": null}|
|dispatch_curtailment_mwh|343.106291593|342.977539092|
|dispatch_curtailment_interval_exposure_fuel_mmbtu|4894.248370795|4892.43517635|
|dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu|{"hot_standby_fuel_mmbtu": 3.642013889, "load_fuel_mmbtu": 4677.688023572, "no_load_fuel_mmbtu": 60.918333333, "start_fuel_mmbtu": 152.0}|{"hot_standby_fuel_mmbtu": 3.642013889, "load_fuel_mmbtu": 4675.898162461, "no_load_fuel_mmbtu": 60.895, "start_fuel_mmbtu": 152.0}|
|dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu|{"gt-hot-01": 738.419791667, "gt-hot-02": 294.486527778, "gt-spin-01": 2152.666217898, "gt-spin-02": 1708.675833457}|{"gt-hot-01": 737.513194445, "gt-hot-02": 293.579930556, "gt-spin-01": 2152.666217898, "gt-spin-02": 1708.675833457}|
|dispatch_curtailment_attributable_fuel_mmbtu|3608.878484911|3607.524008603|
|dispatch_curtailment_attributable_fuel_by_unit_mmbtu|{"gt-hot-01": 537.463176576, "gt-hot-02": 164.951193898, "gt-spin-01": 1645.626267003, "gt-spin-02": 1260.837847434}|{"gt-hot-01": 536.782073718, "gt-hot-02": 164.270090991, "gt-spin-01": 1645.630131731, "gt-spin-02": 1260.841712162}|
|unserved_mwh|0.893328423|0.859772492|
|peak_unserved_mw|42.36838787|42.36838787|
|served_mwh|143.067046027|143.100601957|
|unserved_intervals|[{"end_sim_time_s": 29165.0, "peak_unserved_mw": 19.287968405751712, "start_sim_time_s": 29130.0}, {"end_sim_time_s": 29235.0, "peak_unserved_mw": 1.8802011558611156, "start_sim_time_s": 29215.0}, {"end_sim_time_s": 36350.0, "peak_unserved_mw": 38.394865912415625, "start_sim_time_s": 36310.0}, {"end_sim_time_s": 43555.0, "peak_unserved_mw": 39.4036584956214, "start_sim_time_s": 43510.0}, {"end_sim_time_s": 50730.0, "peak_unserved_mw": 29.140845418775996, "start_sim_time_s": 50710.0}, {"end_sim_time_s": 50760.0, "peak_unserved_mw": 1.25, "start_sim_time_s": 50750.0}, {"end_sim_time_s": 57940.0, "peak_unserved_mw": 42.36838786968556, "start_sim_time_s": 57910.0}, {"end_sim_time_s": 65140.0, "peak_unserved_mw": 37.890845418775996, "start_sim_time_s": 65110.0}]|[{"end_sim_time_s": 29165.0, "peak_unserved_mw": 19.287968405751712, "start_sim_time_s": 29130.0}, {"end_sim_time_s": 29235.0, "peak_unserved_mw": 1.8802011558611156, "start_sim_time_s": 29215.0}, {"end_sim_time_s": 36350.0, "peak_unserved_mw": 38.394865912415625, "start_sim_time_s": 36310.0}, {"end_sim_time_s": 43555.0, "peak_unserved_mw": 39.4036584956214, "start_sim_time_s": 43510.0}, {"end_sim_time_s": 50725.0, "peak_unserved_mw": 26.640845418775996, "start_sim_time_s": 50710.0}, {"end_sim_time_s": 57940.0, "peak_unserved_mw": 42.36838786968556, "start_sim_time_s": 57910.0}, {"end_sim_time_s": 65140.0, "peak_unserved_mw": 37.890845418775996, "start_sim_time_s": 65110.0}]|
|energy_balance|{"closure_status": true, "max_abs_physical_ledger_defect_mw": 0.0, "served_demand_mwh": 143.067046027, "unserved_demand_mwh": 0.893328423}|{"closure_status": true, "max_abs_physical_ledger_defect_mw": 0.0, "served_demand_mwh": 143.100601957, "unserved_demand_mwh": 0.859772492}|
|bess_soc_min|0.950386947|0.950386947|
|bess_soc_max|0.999999998|0.999999998|
|bess_soc_final|0.999999987|0.999999987|
|commitment|{"distinct_event_count": 67, "log_complete": true, "omitted_record_count": 0, "reserve_floor_distinct_event_count": 14890, "reserve_floor_log_complete": true, "reserve_floor_omitted_record_count": 0, "reserve_floor_refusal_count": 14890, "reserve_floor_suppressed_repeat_count": 0, "reserve_floor_visible_distinct_event_count": 14890, "same_unit_restart_within_min_down_window_count": 0, "suppressed_repeat_count": 11205, "visible_distinct_event_count": 67}|{"distinct_event_count": 65, "log_complete": true, "omitted_record_count": 0, "reserve_floor_distinct_event_count": 14904, "reserve_floor_log_complete": true, "reserve_floor_omitted_record_count": 0, "reserve_floor_refusal_count": 14904, "reserve_floor_suppressed_repeat_count": 0, "reserve_floor_visible_distinct_event_count": 14904, "same_unit_restart_within_min_down_window_count": 0, "suppressed_repeat_count": 11198, "visible_distinct_event_count": 65}|
|forecast|{"miss_count": 39, "miss_peak_mw": 13.130749227}|{"miss_count": 39, "miss_peak_mw": 13.130749227}|
|compute_trace_sha256|"ea1916a426e67dde51a9a926dc4b64b0c2eb2470ee2e0076fe7f17b8d55f420b"|"ea1916a426e67dde51a9a926dc4b64b0c2eb2470ee2e0076fe7f17b8d55f420b"|
|compute_trace_count|17280|17280|
|daily_breakdown|[{"bess_soc_end": 0.999999987, "curtailed_mwh": 343.106291593, "day": 1, "fuel_by_component_mmbtu": {"hot_standby_fuel_mmbtu": 3.761458333, "load_fuel_mmbtu": 5107.722017303, "no_load_fuel_mmbtu": 64.866666667, "start_fuel_mmbtu": 152.0}, "fuel_mmbtu": 5328.350142303, "kind": "weekday", "unserved_mwh": 0.893328423}]|[{"bess_soc_end": 0.999999987, "curtailed_mwh": 342.977539092, "day": 1, "fuel_by_component_mmbtu": {"hot_standby_fuel_mmbtu": 3.761458333, "load_fuel_mmbtu": 5106.733034717, "no_load_fuel_mmbtu": 64.855, "start_fuel_mmbtu": 152.0}, "fuel_mmbtu": 5327.34949305, "kind": "weekday", "unserved_mwh": 0.859772492}]|
|constraints_valid|true|true|
|hard_violations|[]|[]|
Candidate full metrics repeat-identical = True
BASE rejected starts: 6 per saved repetition; fresh repetition also 6. Candidate: 0 in both repetitions.
Replacement accepted START: gt-hot-02 at sim_time 50350.0 s, tick 10071; gt-hot-01 starts at 50380.0 s, tick 10077.
Candidate constraints_valid=True, hard_violations=[], status=PASS, guard_failures=[].
H2 baseline was NOT re-run before the stop. Its historical FAIL (recorded 6 vs measured 11 starts, fuel 124.0 MMBtu) is preserved in prior evidence; baseline identity and a new compare_runs gate are NOT established.
No comparison combines different engine commits under a fabricated build-parity PASS.

## B6 base demo
|Arm|Repetition|Ticks|Curtailment MWh|Turbine MMBtu|Unserved MWh|Peak unserved MW|All saved metrics / compact hash equal|
|---|---:|---:|---:|---:|---:|---:|---|
|baseline|1|1440|8.136511735|714.363019086|0.351692658|22.309362466|True|
|baseline|2|1440|8.136511735|714.363019086|0.351692658|22.309362466|True|
|informed|1|1440|5.278943188|665.398247704|0.020719074|7.52325057|True|
|informed|2|1440|5.278943188|665.398247704|0.020719074|7.52325057|True|

## 3.4 / 3.5 — not reached
Full suite: NOT RUN after B1 failure. Passed/failed/added/removed counts: NOT AVAILABLE.
No PHASE_3_FAILING_TESTS.txt was created; an empty list would falsely imply a completed passing suite.
No validated implementation commit or report-only commit was made. HEAD remains the automatic unvalidated checkpoint.

## Safe stopped state / stash
Stash: `stash@{0}` = `b416122acfa07c59d4a3521a90361d5be775d612`; its tree contains the complete D2 candidate plus nullable logger repair and test.
Because HEAD itself contains the earlier checkpointed crashing candidate, stashing only the new working changes would expose that crash again.
Therefore the eight candidate application/test paths were additionally restored in index and worktree from 1345380, without changing HEAD or rewriting history.
Verification: `git diff 1345380 -- P/core P/runtime P/tests` = empty output.
The new candidate test is absent in restored BASE; it is preserved in the stash and diff below.
Current source is BASE, not the rejected candidate. Staged restorations are intentional; Git status is NOT clean.
The existing GridSignal web workflow was restarted once after restoration; log records Application startup complete and GET / HTTP/1.1 200 OK.
Workflow log: `/tmp/logs/artifactsgridsignal_web_20261022_074844_708_c05a8106.log`.

Current git status:
```text
M .agents/memory/s1-study-harness.md
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
D  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py
 M tools/dr_isl/PHASE_3_EVIDENCE.json
 M tools/dr_isl/PHASE_3_TC06.xml
```

## Storage and evidence limitations
No full per-tick exports were written. SHA-256 and metrics streamed in memory; native compact rows remained in memory until hashed.
Every scratch file is below 200,000,000 bytes. Original persisted baseline_runner.py was not edited.
The missing registered scratch worktree required git worktree add --force; the initial failed worktree attempt did not produce a scenario result.
H2 candidate identity seed field is 42 from the reconstructed helper; the fresh base uses None. This affects identity metadata only: run context IDs and configured RNG pinning are identical, and fresh base exactly reproduces saved BASE full physical and compact hashes.
This seed-label difference is disclosed, not used to waive the physical prefix mismatch. Certified H1 checks were not completed.

## Full stopped candidate diff (BASE 1345380 -> stashed candidate; NOT active source)
```diff
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
index 1b2b974..11ec12b 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
@@ -1054,6 +1054,18 @@ class TurbineModule(AssetModule):
         self._last_setpoint_mw = float(new_output_mw)   # store before rate-clip
         self._current_output_mw = max(0.0, min(new_output_mw, self.config.rated_mw))
 
+    def start_eligibility(self, sim_time: float) -> tuple[bool, str]:
+        """DR D2 / IMPL-ISL-5: the single, unchanged turbine start interlock."""
+        if self.config.hot_standby:
+            return False, "hot_standby"
+        if self.state != TurbineState.OFFLINE:
+            return False, "state"
+        if self.config.min_down_enabled and not math.isnan(self._stop_time_s):
+            elapsed = sim_time - self._stop_time_s
+            if elapsed < self.config.t_min_down_s:
+                return False, "min_down"
+        return True, "eligible"
+
     def command_start(self, sim_time: float) -> None:
         """Transition OFFLINE → STARTING.  Phase 2 commitment-logic entry point.
 
@@ -1066,19 +1078,10 @@ class TurbineModule(AssetModule):
 
         No output is produced while STARTING (_current_output_mw stays 0.0).
         """
-        if self.config.hot_standby:
+        # DR D2 / IMPL-ISL-5: retain the safety check, using the same predicate
+        # as selection and the availability boundary (no second guard copy).
+        if not self.start_eligibility(sim_time)[0]:
             return
-        if self.state != TurbineState.OFFLINE:
-            return
-
-        # R6: enforce minimum down-time when the constraint is enabled.
-        # Phase E closeout Item 1 / D-03: gated on min_down_enabled so tests
-        # that create TurbineConfig() directly (min_down_enabled=False default)
-        # are unaffected.
-        if self.config.min_down_enabled and not math.isnan(self._stop_time_s):
-            elapsed = sim_time - self._stop_time_s
-            if elapsed < self.config.t_min_down_s:
-                return  # cooling window not yet satisfied
 
         # Determine thermal state from time offline since last synchronisation.
         # First start (never stopped): use config.initial_thermal_state so the
@@ -1114,7 +1117,9 @@ class TurbineModule(AssetModule):
                 ThermalState.COLD: self.config.fuel.start_fuel_mmbtu_cold,
             }[self._thermal_state]
 
-    def unit_availability(self) -> "UnitAvailability":
+    # PROPOSED_HERE: epoch default preserves existing no-argument boundary
+    # callers; runtime selection always passes the actual simulation time.
+    def unit_availability(self, sim_time: float = 0.0) -> "UnitAvailability":
         """Build a UnitAvailability boundary object from current state.
 
         Called by simulation_core.py each tick to build the availability list
@@ -1132,6 +1137,7 @@ class TurbineModule(AssetModule):
         else:
             time_to_online = None
 
+        eligible, reason = self.start_eligibility(sim_time)
         return UnitAvailability(
             unit_id=self.config.asset_id,
             state=self.state,
@@ -1142,6 +1148,8 @@ class TurbineModule(AssetModule):
             time_to_online_s=time_to_online,
             out_of_service_reason=self._out_of_service_reason,
             hot_standby=self.config.hot_standby,
+            start_eligible=eligible,
+            start_ineligibility_reason=None if eligible else reason,
         )
 
     def command_stop(self, sim_time: float) -> Optional[str]:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
index c6b6401..85c7a7c 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
@@ -326,9 +326,22 @@ def evaluate_commitment(
                 ),
                 floor_mw=floor_mw, floor_violated=floor_violated,
             )
+        # DR D2 / IMPL-ISL-5: consume the one asset predicate's snapshot,
+        # preserving caller priority, rather than retrying offline[0].
+        eligible = next((unit for unit in offline if unit.start_eligible), None)
+        if eligible is None:
+            return CommitmentDecision(
+                action="hold",
+                target_unit_id=None,
+                reason=f"commit condition met (U={utilisation:.3f}, floor_violated={floor_violated})",
+                blocked_by="no eligible turbine: " + "; ".join(
+                    f"{unit.unit_id}={unit.start_ineligibility_reason}" for unit in offline
+                ),
+                floor_mw=floor_mw, floor_violated=floor_violated,
+            )
         return CommitmentDecision(
             action="commit",
-            target_unit_id=offline[0].unit_id,
+            target_unit_id=eligible.unit_id,
             reason=(
                 f"floor_violated={floor_violated}, U={utilisation:.3f}"
                 f" ≥ {cfg.commit_utilisation}" if not floor_violated else
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
index 4bd7cac..9507e45 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
@@ -590,7 +590,8 @@ class DispatchArbitrator:
         if not _active_turbines and not _active_fuel_cells:
             required_ramp_s = float("inf")
         else:
-            _offline = [t for t in _active_turbines if t.state == TurbineState.OFFLINE]
+            # DR D2 / IMPL-ISL-5: staging shares command_start's interlock.
+            _offline = [t for t in _active_turbines if t.start_eligibility(sim_time)[0]]
             _on_bus  = [t for t in _active_turbines if t.state != TurbineState.OFFLINE]
 
             # ── Stage offline turbines: N_needed + 1 N-1 spare ──────────────────
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
index cf0140b..3044d09 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
@@ -745,6 +745,11 @@ class UnitAvailability:
     time_to_online_s: Optional[float]    # 0.0 = SYNCHRONISED; None = OUT_OF_SERVICE
     out_of_service_reason: Optional[str] # None unless OUT_OF_SERVICE
     hot_standby: bool = False            # True → excluded from ramp credit and dispatch
+    # DR D2 / IMPL-ISL-5: verdict evaluated by TurbineModule.start_eligibility.
+    # PROPOSED_HERE: True preserves explicitly supplied PMS/test snapshots;
+    # live turbine snapshots always supply their time-resolved verdict.
+    start_eligible: bool = True
+    start_ineligibility_reason: Optional[str] = None
 
     @property
     def is_starting(self) -> bool:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
index 60596e0..c30fc99 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -291,6 +291,7 @@ class SimulationState:
     _commit_cfg:    CommitmentConfig    = field(init=False)
     _pending_start: PendingStartRegister = field(init=False)
     _commit_cond:   SustainedCondition  = field(init=False)
+    _start_ineligible_episode_logged: bool = field(default=False, init=False)
     _decommit_cond: SustainedCondition  = field(init=False)
     # Contingency-triggered standby release is deliberately separate from
     # evaluate_commitment().  The condition is armed again only after one
@@ -598,7 +599,7 @@ _STANDBY_THERMAL_PRIORITY = {
 }
 
 
-def _offline_turbines_by_thermal_priority(
+def _offline_turbine_roster(
     turbines: list[TurbineModule],
 ) -> list[TurbineModule]:
     """Return offline turbines in hot → warm → cold, then roster order."""
@@ -617,6 +618,51 @@ def _offline_turbines_by_thermal_priority(
     )
 
 
+def _offline_turbines_by_thermal_priority(
+    turbines: list[TurbineModule], sim_time: float, *, include_blocked: bool = False,
+) -> list[TurbineModule]:
+    """DR D2 / IMPL-ISL-5: one start predicate, unchanged thermal/roster order.
+
+    The commitment boundary includes blocked non-reserved units so it can
+    report why an episode has no candidate. Reserve labels use the raw roster.
+    """
+    candidates = []
+    for turbine in _offline_turbine_roster(turbines):
+        eligible, reason = turbine.start_eligibility(sim_time)
+        if eligible or (include_blocked and reason != "hot_standby"):
+            candidates.append(turbine)
+    return candidates
+
+
+def _releasable_hot_standby_turbines(
+    turbines: list[TurbineModule], sim_time: float,
+) -> list[TurbineModule]:
+    """Evaluate unchanged interlocks under the existing explicit release authority."""
+    candidates = []
+    for turbine in _offline_turbine_roster(turbines):
+        if turbine.config.hot_standby:
+            turbine.config.hot_standby = False
+            try:
+                eligible, _ = turbine.start_eligibility(sim_time)
+            finally:
+                turbine.config.hot_standby = True
+            if eligible:
+                candidates.append(turbine)
+    return candidates
+
+
+def _log_start_ineligibility_episode(
+    state: SimulationState, decision: CommitmentDecision, sim_time: float,
+) -> None:
+    """DR D2: one commitment-log reason per contiguous blocked episode."""
+    blocked = isinstance(decision.blocked_by, str) and decision.blocked_by.startswith(
+        "no eligible turbine:"
+    )
+    if blocked and not state._start_ineligible_episode_logged:
+        _log.info("Commitment engine: %s at sim_time=%.1f", decision.blocked_by, sim_time)
+    state._start_ineligible_episode_logged = blocked
+
+
 def _promote_reserve_standby_labels(
     turbines: list[TurbineModule],
 ) -> tuple[str, ...]:
@@ -627,7 +673,7 @@ def _promote_reserve_standby_labels(
     """
     remaining = [
         turbine
-        for turbine in _offline_turbines_by_thermal_priority(turbines)
+        for turbine in _offline_turbine_roster(turbines)
         if turbine.config.hot_standby
     ]
     desired = [ThermalState.HOT, ThermalState.WARM]
@@ -714,11 +760,7 @@ def _release_hot_standby_for_contingency(
     ):
         return None
 
-    hot_standby_units = [
-        turbine
-        for turbine in _offline_turbines_by_thermal_priority(state.turbines)
-        if turbine.config.hot_standby
-    ]
+    hot_standby_units = _releasable_hot_standby_turbines(state.turbines, sim_time)
     if not hot_standby_units:
         return None
 
@@ -2178,12 +2220,13 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     # reserve; using them here would make the commitment decision disagree with
     # the operator-facing reserve summary during the controlled rundown.
     _avail_on_bus = [
-        t.unit_availability() for t in state.turbines if t.contributes_to_reserve
+        t.unit_availability(sim_time) for t in state.turbines if t.contributes_to_reserve
     ]
     _avail_offline = [
-        t.unit_availability()
-        for t in _offline_turbines_by_thermal_priority(state.turbines)
-        if not t.config.hot_standby
+        t.unit_availability(sim_time)
+        for t in _offline_turbines_by_thermal_priority(
+            state.turbines, sim_time, include_blocked=True,
+        )
     ]
 
     # ── Cascade commit trigger (site.cascade_commit_fraction) ─────────────
@@ -2239,11 +2282,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
                 # command_start().  Fix: clear the flag, THEN call command_start()
                 # (the guard is gone so it transitions OFFLINE → STARTING normally,
                 # using initial_thermal_state="hot" → hot_start_s duration).
-                _hs_units = [
-                    t
-                    for t in _offline_turbines_by_thermal_priority(state.turbines)
-                    if t.config.hot_standby
-                ]
+                _hs_units = _releasable_hot_standby_turbines(state.turbines, sim_time)
                 if _hs_units and state._pending_start.is_empty:
                     _next_hs = _hs_units[0]
                     _before_state = _next_hs.state
@@ -2316,6 +2355,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         decommit_enabled     = _bess_rundown_enabled and not _generation_baseload_active,
         decommit_reason_context = _bess_rundown_reason,
     )
+    _log_start_ineligibility_episode(state, _commit_decision, sim_time)
     if (
         _commit_decision.action == "commit"
         and _commit_decision.target_unit_id is not None
@@ -2535,7 +2575,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     # UNLOADING units are pinned at MSL with no upward headroom — counting their
     # nameplate overstates reserve precisely when the fleet is shrinking.
     # Distinct from on_bus_output_mw which INCLUDES UNLOADING (they do produce).
-    _avail_reserve        = [t.unit_availability() for t in state.turbines if t.contributes_to_reserve]
+    _avail_reserve        = [t.unit_availability(sim_time) for t in state.turbines if t.contributes_to_reserve]
     _committed_rated_mw_cs = sum(u.rated_mw for u in _avail_reserve)
     _fleet_utilisation_cs = (
         _commitment_demand_mw / _committed_rated_mw_cs
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
index 6eec6e0..4f3fadb 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
@@ -1519,9 +1519,11 @@ class RunContext:
                         unit_id, self.sim_time, self.run_id,
                     )
                 elif action == "start":
-                    was_offline = turbine.state == _TurbineState.OFFLINE
+                    # DR D2 / IMPL-ISL-5: explicit operator commands retain
+                    # their target; eligibility is not independently reimplemented.
+                    eligible, _ = turbine.start_eligibility(self.sim_time)
                     turbine.command_start(self.sim_time)
-                    accepted = was_offline and turbine.state == _TurbineState.STARTING
+                    accepted = eligible and turbine.state == _TurbineState.STARTING
                     if not accepted:
                         refusal_reason = (
                             "start refused: unit is not offline or minimum down time "
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
index ca8445f..19e8ba6 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
@@ -619,20 +619,25 @@ class ForecastDrivenTurbineController:
         )
         return allowance, soc
 
-    def _candidate_start(self, turbines: list[Any]) -> Optional[Any]:
-        standby = [
-            turbine for turbine in turbines
-            if turbine.state == TurbineState.OFFLINE
-            and getattr(turbine.config, "hot_standby", False)
-        ]
-        if standby:
-            return standby[0]
-        offline = [
-            turbine for turbine in turbines
-            if turbine.state == TurbineState.OFFLINE
-            and not getattr(turbine.config, "hot_standby", False)
-        ]
-        return offline[0] if offline else None
+    def _candidate_start(self, turbines: list[Any], sim_time_s: float) -> Optional[Any]:
+        # DR D2 / IMPL-ISL-5: preserve standby-first/roster priority, but use
+        # the same interlock as the core and command path. A reserved candidate
+        # is evaluated under this controller's existing explicit release authority.
+        ordered = (
+            [t for t in turbines if getattr(t.config, "hot_standby", False)]
+            + [t for t in turbines if not getattr(t.config, "hot_standby", False)]
+        )
+        for turbine in ordered:
+            reserved = bool(turbine.config.hot_standby)
+            if reserved:
+                turbine.config.hot_standby = False
+            try:
+                eligible, _ = turbine.start_eligibility(sim_time_s)
+            finally:
+                turbine.config.hot_standby = reserved
+            if eligible:
+                return turbine
+        return None
 
     def _candidate_stop(self, turbines: list[Any]) -> Optional[Any]:
         synchronized = [
@@ -828,7 +833,7 @@ class ForecastDrivenTurbineController:
         start_horizon = self.hot_start_lookahead_seconds + self.ramp_to_load_seconds
         start_peak = forecast.peak_over(start_horizon)
         if start_peak > synchronized_capacity + bess_allowance:
-            candidate = self._candidate_start(turbines)
+            candidate = self._candidate_start(turbines, float(ctx.sim_time))
             if candidate is not None:
                 self._queue(
                     ctx,
@@ -1196,7 +1201,7 @@ class ForecastDrivenTurbineController:
         accepted = True
         refusal_reason: Optional[str] = None
         if decision.action == "commit":
-            if turbine.state != TurbineState.OFFLINE:
+            if not turbine.start_eligibility(sim_time_s)[0]:
                 accepted = False
                 refusal_reason = (
                     "forecast controller veto: unit is not offline and cannot start"
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py
new file mode 100644
index 0000000..d1036fb
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py
@@ -0,0 +1,127 @@
+"""DR D2 / IMPL-ISL-5, TC-ISL-06: one unchanged turbine start interlock."""
+import ast
+from dataclasses import replace
+import inspect
+import logging
+import textwrap
+from types import SimpleNamespace
+
+from core.asset_modules import TurbineModule
+from core.commitment import (
+    CommitmentConfig, PendingStartRegister, SustainedCondition, evaluate_commitment,
+)
+from core.dispatch import DispatchArbitrator
+from core.models import TurbineConfig, TurbineState
+from core.simulation_core import (
+    _log_start_ineligibility_episode, _offline_turbines_by_thermal_priority,
+    _releasable_hot_standby_turbines,
+)
+from runtime.run_manager import RunContext
+from runtime.turbine_commitment import ForecastDrivenTurbineController
+
+
+def _calls(fn):
+    return {
+        node.func.attr for node in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(fn))))
+        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
+    }
+
+
+def _unit(name, stopped=False):
+    # PROPOSED_HERE: synthetic fixture timestamps straddle the existing 900 s
+    # minimum-down interlock; these are not new operational settings.
+    unit = TurbineModule(TurbineConfig(
+        asset_id=name, min_down_enabled=True, t_min_down_s=900.0,
+    ))
+    if stopped:
+        unit._stop_time_s = 0.0
+    return unit
+
+
+def _decision(units, time):
+    roster = _offline_turbines_by_thermal_priority(units, time, include_blocked=True)
+    return evaluate_commitment(
+        on_bus=[], offline=[u.unit_availability(time) for u in roster],
+        p_demand_mw=20.0, pending=PendingStartRegister(),
+        commit_cond=SustainedCondition(), decommit_cond=SustainedCondition(),
+        cfg=replace(CommitmentConfig.from_catalogue(), inter_start_settle_s=0.0),
+        dt_s=5.0, sim_time=time,
+    )
+
+
+def test_tc_isl_06a_single_guard_call_graph():
+    for fn in (TurbineModule.command_start, TurbineModule.unit_availability,
+               _offline_turbines_by_thermal_priority, _releasable_hot_standby_turbines):
+        assert "start_eligibility" in _calls(fn)
+    # Inspect the entire arbitrator: staging must call the same predicate.
+    assert "start_eligibility" in _calls(DispatchArbitrator)
+    assert "start_eligibility" in _calls(ForecastDrivenTurbineController._candidate_start)
+    assert "start_eligibility" in _calls(ForecastDrivenTurbineController.adjudicate_core_proposal)
+    assert "start_eligibility" in _calls(RunContext.drain_operator_commands)
+    source = inspect.getsource(TurbineModule.command_start)
+    assert "self.config.hot_standby" not in source
+    assert "elapsed < self.config.t_min_down_s" not in source
+    assert "self.state != TurbineState.OFFLINE" not in source
+    assert "unit.start_eligible" in inspect.getsource(evaluate_commitment)
+    assert "target_unit_id=offline[0]" not in inspect.getsource(evaluate_commitment)
+
+
+def test_tc_isl_06b_skip_min_down_start_alternate():
+    cooling, alternate = _unit("cooling", True), _unit("alternate")
+    assert cooling.start_eligibility(100.0) == (False, "min_down")
+    assert alternate.start_eligibility(100.0) == (True, "eligible")
+    decision = _decision([cooling, alternate], 100.0)
+    assert decision.action == "commit"
+    assert decision.target_unit_id == "alternate"
+    alternate.command_start(100.0)
+    assert alternate.state == TurbineState.STARTING
+    assert cooling.state == TurbineState.OFFLINE
+    # The certified study's forecast selector must skip the same interlock.
+    alternate.state = TurbineState.OFFLINE
+    assert ForecastDrivenTurbineController._candidate_start(
+        None, [cooling, alternate], 100.0,
+    ) is alternate
+
+
+def test_tc_isl_06c_no_eligible_one_log_per_episode(caplog):
+    units = [_unit("one", True), _unit("two", True)]
+    state = SimpleNamespace(_start_ineligible_episode_logged=False)
+    with caplog.at_level(logging.INFO, logger="core.simulation_core"):
+        for time in (100.0, 105.0, 110.0):
+            decision = _decision(units, time)
+            assert decision.action == "hold"
+            assert decision.target_unit_id is None
+            assert "one=min_down" in decision.blocked_by
+            assert "two=min_down" in decision.blocked_by
+            _log_start_ineligibility_episode(state, decision, time)
+        logs = [r for r in caplog.records if "no eligible turbine:" in r.message]
+        assert len(logs) == 1
+        assert all(u.state == TurbineState.OFFLINE and u._start_count == 0 for u in units)
+        # Clearing the blocked condition rearms the logger, not the guard.
+        _log_start_ineligibility_episode(state, _decision(units, 900.0), 900.0)
+        _log_start_ineligibility_episode(state, _decision(units, 100.0), 100.0)
+        assert sum("no eligible turbine:" in r.message for r in caplog.records) == 2
+        assert not any("silently dropped" in r.message for r in caplog.records)
+
+
+def test_tc_isl_06d_ordinary_hold_is_not_an_ineligibility_episode(caplog):
+    state = SimpleNamespace(_start_ineligible_episode_logged=True)
+    with caplog.at_level(logging.INFO, logger="core.simulation_core"):
+        for reason in (None, "", "minimum run time", 123):
+            decision = SimpleNamespace(blocked_by=reason)
+            _log_start_ineligibility_episode(state, decision, 100.0)
+            assert state._start_ineligible_episode_logged is False
+    assert not caplog.records
+
+
+def test_tc_isl_06_guard_boundaries_unchanged():
+    unit = _unit("boundary", True)
+    assert unit.start_eligibility(899.0) == (False, "min_down")
+    assert unit.start_eligibility(900.0) == (True, "eligible")
+    unit.config.min_down_enabled = False
+    assert unit.start_eligibility(0.0) == (True, "eligible")
+    unit.config.hot_standby = True
+    unit.state = TurbineState.STARTING
+    assert unit.start_eligibility(0.0) == (False, "hot_standby")
+    unit.config.hot_standby = False
+    assert unit.start_eligibility(0.0) == (False, "state")

```

## Output-only observer used for the runs
```python
#!/usr/bin/env python3
"""Output-only Phase 3 observer. No tick exports; all files <200 MB."""
import argparse, asyncio, copy, hashlib, importlib.util, json, logging, os
from pathlib import Path
import random, resource, sys
from types import SimpleNamespace
from unittest.mock import patch

resource.setrlimit(resource.RLIMIT_FSIZE, (200_000_000, 200_000_000))
ROOT = Path("/home/runner/workspace")
P = Path("attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim")
T = Path("/tmp/DR-ISL-phase3")
a = argparse.ArgumentParser()
a.add_argument("scenario")
a.add_argument("--arm", default="app")
a.add_argument("--version", default="candidate")
a.add_argument("--reps", type=int, default=1)
args = a.parse_args()
pkg = ROOT / P if args.version == "candidate" else T / "base" / P
sys.path.insert(0, str(pkg))
sys.dont_write_bytecode = True
os.chdir(pkg)
import numpy as np
from core.asset_modules import TurbineModule
from core.models import TurbineState
from core.simulation_core import SimulationState
from runtime.fabric_engine import FabricEngine
from runtime.run_manager import RunContext, RunManager, WebSocketHub, InMemoryTimeseriesSink
from runtime.scenario_factory import build_run_context_from_spec
from api.schemas import ScenarioSpec
from study_harness import executor

loader = importlib.util.spec_from_file_location("pinning", ROOT / "tools/dr_isl/baseline_runner.py")
pin = importlib.util.module_from_spec(loader)
loader.loader.exec_module(pin)
orig_fabric = FabricEngine.__init__
orig_build = executor.build_run_context_from_spec
orig_start = TurbineModule.command_start
orig_step = RunContext.step
active = None
trace = None

def fabric(self, *pos, **kw):
    kw["seed"] = 1729
    return orig_fabric(self, *pos, **kw)

def build(run_id, spec, **kw):
    global active
    spec = copy.deepcopy(spec)
    pin.pin_spec(spec)
    ctx = orig_build(run_id, spec, **kw)
    for i, diesel in enumerate(ctx.sim_state.diesel_units):
        diesel._rng.seed(1729 + i)
    active = ctx
    return ctx

def start(self, sim_time):
    state = self.state
    if self.config.hot_standby:
        reason = "hot_standby"
    elif state != TurbineState.OFFLINE:
        reason = "state"
    elif self.config.min_down_enabled and not np.isnan(self._stop_time_s) and sim_time - self._stop_time_s < self.config.t_min_down_s:
        reason = "min_down"
    else:
        reason = "eligible"
    result = orig_start(self, sim_time)
    if trace is not None:
        trace["attempts"].append(dict(
            tick=active.sim_state.tick_index + 1, sim_time=sim_time,
            unit=self.config.asset_id, reason=reason,
            before=state.value, after=self.state.value,
        ))
    return result

class LogCounter(logging.Handler):
    def emit(self, record):
        if trace is not None and "no eligible turbine:" in record.getMessage():
            trace["episodes"].append(record.getMessage())

def reset_trace():
    return dict(steps=0, digest=hashlib.sha256(), prefix=hashlib.sha256(),
                attempts=[], episodes=[], collapsed=[], min_soc=1.0,
                frequency=[float("inf"), -float("inf")], unserved=0.0,
                balance_failures=[])

cutoff = 1059 if args.scenario.startswith("S10") else 10071

def step(self, *pos, **kw):
    tick = orig_step(self, *pos, **kw)
    if trace is not None:
        row = pin.plain(tick)
        encoded = pin.encoded({k: v for k, v in row.items() if k not in pin.EXCLUDED})
        trace["digest"].update(encoded)
        trace["steps"] += 1
        if trace["steps"] < cutoff:
            trace["prefix"].update(encoded)
        trace["min_soc"] = min(trace["min_soc"], tick.bess_soc_fraction)
        trace["frequency"][0] = min(trace["frequency"][0], tick.frequency_hz)
        trace["frequency"][1] = max(trace["frequency"][1], tick.frequency_hz)
        trace["unserved"] += tick.p_unserved_mw * 5 / 3600
        if tick.island_collapsed:
            trace["collapsed"].append(dict(tick=tick.tick_index, reason=tick.collapse_reason))
        if not tick.physical_balance.passed:
            trace["balance_failures"].append(tick.tick_index)
    return tick

class Sink(InMemoryTimeseriesSink):
    def __init__(self):
        super().__init__()
        self.digest = hashlib.sha256()
        self.count = 0
    async def append(self, tick):
        row = pin.plain(tick)
        self.digest.update(pin.encoded({k: v for k, v in row.items() if k not in pin.EXCLUDED}))
        self.count += 1

class Writer:
    def write(self, *, identity, record, summary, tick_rows):
        digest = hashlib.sha256()
        for row in tick_rows:
            digest.update(pin.encoded(row))
        record["diagnostic_compact_sha256"] = digest.hexdigest()
        return SimpleNamespace(as_dict=lambda: {})

class Cache:
    def put(self, identity, record):
        return record

def export_trace():
    out = {k: v for k, v in trace.items() if k not in {"digest", "prefix"}}
    out["internal_physical_sha256"] = trace["digest"].hexdigest()
    out["prefix_sha256"] = trace["prefix"].hexdigest()
    return out

async def run():
    global trace
    for rep in range(1, args.reps + 1):
        random.seed(1729)
        np.random.seed(1729)
        trace = None
        if args.arm == "app":
            spec = ScenarioSpec.model_validate_json(
                (pkg / "config/scenarios" / (args.scenario + ".json")).read_bytes()
            ).model_dump(mode="json")
            ctx = build(args.scenario, spec, playback_speed=0.0)
            sink = Sink()
            ctx.sink = sink
            trace = reset_trace()
            manager = RunManager(WebSocketHub())
            await manager.start_run(ctx)
            await manager._tasks[ctx.run_id]
            record = dict(physical_sha256=sink.digest.hexdigest(), tick_count=sink.count)
        else:
            ex = executor.StudyRunExecutor(
                output_dir=T / "unused", engine_commit="phase2c-comparison",
                harness_commit="phase2c-comparison")
            ex.writer, ex.cache = Writer(), Cache()
            spec = ex._expanded_spec(args.scenario, None, None)
            pin.pin_spec(spec)
            replay, demand = ex._probe(spec, run_id=f"{args.scenario}-study-s1-probe")
            trace = reset_trace()
            record = ex._run_mode(
                scenario_id=args.scenario, mode=args.arm, spec=spec,
                replay_events=replay, demand_replay=demand,
                seed=None if args.scenario.startswith("scenario-h") else 42,
                allow_guard_failure=True, reuse_cache=False)
        out = dict(scenario=args.scenario, arm=args.arm, version=args.version,
                   repetition=rep, trace=export_trace(), record=record)
        dest = T / f"{args.version}-{args.scenario}-{args.arm}-{rep}.json"
        dest.write_text(json.dumps(pin.plain(out), indent=2, allow_nan=True))
        print(json.dumps(dict(file=str(dest), ticks=trace["steps"],
              rejected=sum(x["reason"] != "eligible" for x in trace["attempts"]),
              curtailment=record.get("dispatch_curtailment_mwh"),
              hash=record.get("physical_sha256", record.get("diagnostic_compact_sha256")))), flush=True)

logging.basicConfig(level=logging.ERROR)
handler = LogCounter()
logging.getLogger("core.simulation_core").addHandler(handler)
logging.getLogger("core.simulation_core").setLevel(logging.INFO)
with patch("time.time", return_value=1792454400.0), \
     patch.object(FabricEngine, "__init__", fabric), \
     patch.object(TurbineModule, "command_start", start), \
     patch.object(RunContext, "step", step), \
     patch.object(executor, "build_run_context_from_spec", build):
    asyncio.run(run())

```

STOP — Phase 3 failed B1. Do not resume, diagnose further, commit D2, or start Phase 4 without review.

## Final Git status after saving report/evidence

```text
 M .agents/memory/s1-study-harness.md
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
M  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
D  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py
 M tools/dr_isl/PHASE_3_EVIDENCE.json
 M tools/dr_isl/PHASE_3_REPORT.md
 M tools/dr_isl/PHASE_3_TC06.xml
```
