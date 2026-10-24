# D6b report — resumed after the D6b.2 MCP scope ruling

Scenario replacement commit: `03476900f0bf1813f6e459c54e75c21946e019bc`.
Report-only checkpoint at start of resumed work: `f323091`.

## D6b.1 decision

**LEGITIMATE THRESHOLD EFFECT**, accepted per Lloyd's ruling dated 2026-10-24. In
`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py:360–369`,
the reserve-floor decommit check compares `remaining_total >= floor_without`.
With one unit remaining, this permits decommit only when turbine-side demand is
exactly zero. At tick 6580, the CPU load makes demand approximately
`9.5e-5 MW`, so the comparison blocks decommit. Commitment logic is unchanged;
changing it is deferred.

The saved D6b.1 comparison records its first physical difference at tick 1:
`p_non_gpu_demand_mw` is `null` in the prior S10 and
`7.948344432112468e-05 MW` in the CPU candidate; total demand is
`0.006712166666666666` versus `0.006791650110987791 MW`. The CPU-only candidate
increases daily demand from `620.9086288248361` to
`621.8578481855576 MWh` (+`0.9492193607215 MWh`), while unserved falls from
`8.4639919161834` to `5.535851047049171 MWh` (-`2.928140869134229 MWh`),
peak unserved falls from `29.80` to `16.80 MW`, and turbine starts fall from 38
to 37. The first commitment-reason telemetry wording difference is tick 5259;
the first actual decommit veto is tick 6580 (`32900 s`).

The largest unserved-difference interval is `33400–34050 s`: baseline
`4.096205470588591 MWh`, CPU candidate `1.1901352489540251 MWh`; at its peak
only `turbine-0` is online in baseline, while `turbine-0` and `turbine-1` are
online in the candidate. This interval accounts for `2.906070221634564 MWh` of
the net `2.928140869134271 MWh` reduction. The trace contains 18 differing
unserved intervals; the small remaining net difference is distributed across
the other 17. The saved comparison hashes are baseline
`3e24904fd7e8f71afa1f5b30ec2f2958a6b43e7670ab9fefae04f3440aa57bff`,
CPU-only `e819540659528686bd40c706290dc09883d87b865e25df17da970f4550fefa1b`.

The D6-F parity evidence reports 17,280 ticks on both sides and identical
non-fuel digests for the (a)+(c) case, the expected digest, and the fuel
candidate: `808873c0bd14974ae4a605c49df4a43e7ba349831689d00399c5a2063da68f9e`.
The saved JSON's `matches_expected` flag is `false` despite those three literal
digest strings being equal; the digest equality is the parity finding, and the
inconsistent flag is retained here rather than silently corrected.

## D6b.2 MCP boundary and REST confirmation (IMPL-ISL-25)

Lloyd withdrew the earlier MCP allowlist instruction for D6b. S10 is not
reachable through MCP because the harness supports only five study classes
(`study_harness/executor.py:72–80`), and the expansion path
(`executor.py:282–305`) would load the base-demo JSON for any other ID.
Listing resolves a study class (`mcp_server/server.py:330–343`), while
`start_run` expands the spec and builds a study identity
(`server.py:457–473`). The allowlist is at `server.py:60–69`. A new S10 study
class needs its own expansion and run identity in a separate design-first
phase. No MCP or study-harness code was changed.

The replaced S10 passed `ScenarioSpec.model_validate_json`; the UI scenario
store seeded it as `S10_mit_supercloud_2021-08-11` with 239 workload events,
320 non-GPU profile points, five fuelled turbines, and initial SoC
`0.9284516364503763`. The REST `/runs` route accepted it with HTTP 201 for a
one-tick smoke run (`run_id=run-24e6f95ab2d7`, physical hash
`b05313fe1532a5f575b4896075a96bc789b01948dd1b292caa2616f3538d0135`).
The seeded UI catalogue entry is at `api/routes/scenarios.py:1435–1466`;
REST retrieves the stored ScenarioSpec and builds the interactive context at
`api/routes/runs.py:286–305` and `:697–734`.

## D6b.3 STOP — pinned-runner and REST hashes differ

Pinned run 1 (`tools/dr_isl/d6f/run_operating_cost.py`, seed 1729,
`wall_clock=1792454400.0`) completed 17,280 ticks and matched the required
D6-F candidate hash exactly:
`4e33ec591dbf46a41a8d3518f891a7b7f7b1096ad3ca7bbf2a7afc27ab3f2029`.
Its recorded metrics include demand `621.8578481855576 MWh`, served
`616.3220787729296 MWh`, unserved `5.535769412629438 MWh`, curtailment
`45.77100963468485 MWh`, turbine output `669.9665561792048 MWh`, BESS
throughput `158.73523332738998 MWh`, 37 starts, and fuel
`7785.288838528619 MMBtu`. Operating cost was `$50,128.168126`,
`$81.334370214/MWh` served, and `$97.305346065/MWh` IT load.

The REST run also completed 17,280 ticks (HTTP 201,
`run-4e24b8cdca45`), but its hash was
`e1375027b49a3a2c7e40dd6b750dc3bef124e6fb9831d1c584298a9e8d9c26d2`, not
the required hash. Its summary recorded demand `621.8577602777779 MWh`,
served `616.3219894444445 MWh`, unserved `5.535770972222222 MWh`, peak
unserved `16.8005 MW`, curtailment `45.77106902777778 MWh`, turbine output
`669.9665261111112 MWh`, BESS throughput `158.7352438888889 MWh`, 37 starts,
519 invalid-frequency ticks (`0.030034722222222223`), and fuel
`7785.288839 MMBtu`. The reported cost total was `$50,128.167952`,
`$81.33438172/MWh` served, and `$97.305358329/MWh` IT load.

A correctly pinned first-tick comparison stopped after one tick and wrote no
tick export (`tools/dr_isl/d6b/D6B_3_FIRST_DIFF.json`). At tick index 1
(`sim_time_seconds=5.0`), the first differing serialized field was
`absorbable_mw`: pinned `0.0`, REST `11.84509476 MW`. Other differences on
that same tick include `bess_bridging_available_mw` (`0.0` vs `17.0 MW`),
`bess_bridging_floor_mw` (`0.0` vs `2.7 MW`), `capacity_gate_headroom_mw`
(`0.0` vs `49.9933 MW`), `rated_cooling_mw` (`0.0` vs `11.84509476 MW`),
site metadata (empty/zero in the pinned row versus Santa Clara coordinates
and name in REST), and turbine telemetry. Turbine states and output MW match
for the five units on this tick, but REST marks the offline/starting units'
breakers closed and provides `setpoint_mw=0.0`; the pinned rows have open
breakers and no setpoint value. REST also includes fuel/configuration fields
inside `turbine_units` that are absent from the pinned rows.

The run identity itself differs on tick 1: pinned `run_id` is
`S10_mit_supercloud_2021-08-11`, while REST uses `run-ba5fd804b7c7` in the
first-difference diagnostic. The pinned runner passes the scenario ID to
`build_run_context_from_spec` with `execution_mode="headless"`
(`tools/dr_isl/d6f/run_operating_cost.py:129–135`); REST creates a UUID run
ID (`api/routes/runs.py:283`). `core/physical_identity.py:14–22` excludes
only advisory telemetry, fabric modal, wall timestamp, and reserve-proposal
ID; `physical_tick_json` filters only those fields and a null non-GPU load
(`:47–63`). Therefore `run_id` is included in the physical hash, in addition
to the other tick-field differences above.

**Gate result: STOP at D6b.3(a).** Repetition 2 was stopped after the REST
hash mismatch and has no result. D6b.3(b–c), existing-scenario gates,
D6b.4 tests/full suites, and later commits were not run. No simulator or test
code was changed in response to this stop.
