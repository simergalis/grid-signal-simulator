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

## D6b continuation — amended REST comparison and completed gates

The prior D6b.3(a) stop above is retained as history and is superseded by
Lloyd's amended comparison rule. No application code was changed during this
continuation.

### D6b.2 S10 replacement record

The replacement is committed in `03476900f0bf1813f6e459c54e75c21946e019bc`
(`Update scenario configuration for S10 mit supercloud`), which changes only
the S10 JSON. Its SHA-256 changed from
`8126ee38ef2206f55d28ea9f4da029df836fbf7c4daf7d65e266d821f323f7ad` to
`5577d437249e48f7b139fa8c7ded820dcc81e5f7ac062e524045dad6f2a187ea`.
The replacement adds the generated non-GPU CPU load profile, initial SoC
`0.9284516364503763`, five SGT-400-proxy turbine fuel blocks, operating-cost
inputs, and provenance/invocation metadata. It keeps the scenario id and name.
The ScenarioSpec, seeded UI catalogue, and REST run-path checks are recorded
above. S10 remains outside the MCP study-class allowlist (IMPL-ISL-25); no MCP
or study-harness routing code was changed.

### D6b.3(a) pinned and REST/RunManager evidence

The second pinned run completed 17,280 ticks. Repetitions 1 and 2 both have
physical SHA-256
`4e33ec591dbf46a41a8d3518f891a7b7f7b1096ad3ca7bbf2a7afc27ab3f2029`
and non-fuel SHA-256
`808873c0bd14974ae4a605c49df4a43e7ba349831689d00399c5a2063da68f9e`.
Their recorded aggregate metrics and operating-cost itemisation are identical.

The in-process REST/RunManager path completed all 17,280 ticks. It was compared
in memory with the pinned tick stream, not by physical hash: `run_id` is part
of `physical_tick_json` (`core/physical_identity.py:14–22, 47–63`) and REST
assigns a UUID run id (`api/routes/runs.py:283`). The requested REST values
were compared: demand, served, unserved, generation, dispatch curtailment,
turbine and BESS output, BESS SoC, frequency and validity, compute, cooling,
non-GPU demand, start count, and each turbine's state and output. All 17,280
ticks are within the serialization tolerance; there is no exceeding tick.

`runtime/run_manager.py:416–445, 452–455, 532, 813` serializes the selected
scalar values with `round(value, 4)`; per-turbine output is rounded to four
decimal places at `:3036–3052`. Thus the numeric tolerance is `0.00005` (half
of `0.0001`); turbine states, `frequency_valid`, and start counts must match
exactly and do. Maximum absolute differences:

| Field | Maximum absolute difference |
|---|---:|
| `bess_output_mw` | 0.000049971991 |
| `bess_soc_fraction` | 0.000049992156 |
| `frequency_hz` | 0.000049989714 |
| `p_compute_demand_mw` | 0.000049833333 |
| `p_cooling_demand_mw` | 0.000049977034 |
| `p_demand_mw` | 0.000049988147 |
| `p_dispatch_curtailed_mw` | 0.000049988147 |
| `p_generation_mw` | 0.000049971991 |
| `p_non_gpu_demand_mw` | 0.000049190714 |
| `p_served_mw` | 0.000049988147 |
| `p_unserved_mw` | 0.000049803185 |
| `turbine_output_mw` | 0.000049957677 |
| `turbine_units.output_mw` | 0 |
| `turbine_units.state` | exact match |
| `frequency_valid` | exact match |
| `turbine_start_count` | exact match |

Fields intentionally excluded from this physical comparison: `run_id`,
`absorbable_mw`, `bess_bridging_*`, `capacity_gate_headroom_mw`,
`design_peak_load_mw`, `rated_cooling_mw`, `site_*`, `edl_dispatch_cost_usd`,
turbine fuel/configuration detail, `breaker_closed`, and `setpoint_mw`.

**IMPL-ISL-26:** the physical hash includes `run_id`; different run ids can
therefore produce different hashes for otherwise identical ticks. This is
recorded for a separate decision; the hash definition was not changed here.

**IMPL-ISL-27:** the REST turbine overlay at
`runtime/run_manager.py:3036–3052` starts with `**static_spec`, then overrides
`state` and `output_mw`; it does not replace `breaker_closed`. The static value
is set at `runtime/scenario_factory.py:2178–2182` to
`not hot_standby`, so offline/starting non-hot-standby units can report
`breaker_closed=true` on REST while the physical tick value at
`core/simulation_core.py:4126` is `bool(turbine.is_on_bus)`. This reporting
difference is deferred to D6c.

### D6b.3(b) S10 metrics and operating cost

| Measure | Value |
|---|---:|
| Demand | 621.857848186 MWh |
| Served | 616.322078773 MWh |
| Unserved / peak unserved | 5.535769413 MWh / 16.8005 MW |
| Dispatch curtailment | 45.771009635 MWh |
| Turbine output | 669.966556179 MWh |
| BESS AC throughput | 158.735233327 MWh |
| Starts | 37 |
| Invalid-frequency ticks / fraction | 519 / 0.0300347222 |
| Total turbine fuel | 7,785.288838529 MMBtu |

Fuel by component: load `7,310.208838529 MMBtu`; no-load `111.080000000`;
hot-standby `0`; start `364.000000000`. Fuel by unit: turbine-0
`2,159.765863003 MMBtu`, turbine-1 `2,033.177159408`, turbine-2
`1,596.658309051`, turbine-3 `1,043.871290797`, turbine-4 `951.816216270`.

| Operating-cost line | Quantity × unit price | Amount |
|---|---:|---:|
| Turbine gas fuel | 8,626.100033090 MMBtu HHV × $5.140790743/MMBtu | $44,344.975194 |
| Diesel fuel | quantity unavailable; $6.276/gal input | null |
| Turbine variable O&M | 669.966556179 MWh × $5.70/MWh | $3,818.809370 |
| Turbine fixed O&M | 205.479452055 kW-year × $9.56/kW-year | $1,964.383562 |
| Non-fuel start cost | 37 starts; no price | null |
| BESS degradation | 158.735233327 MWh AC throughput; no price | null |
| Unserved-energy value | 5.535769413 MWh; no price | null |

Total of non-null lines: `$50,128.168126`; excluded lines are diesel fuel,
non-fuel start, BESS degradation, and unserved-energy value. Cost is
`$81.334370214/MWh` served and `$97.305346065/MWh` IT load. The currency basis
remains mixed: 2023 USD O&M and 2026 USD fuel prices, not inflation-normalized.
The simplified `cost_breakdown` remains separate and is not added to this
total.

### D6b.3(c) protected scenarios and study gates

Seven non-S10 existing-scenario hashes match the saved Phase D6a values, each
with zero balance failures: SJ-1
`616a769cd5b79c243eb7d4d91ff062651e8c2c6e5351f468f0bc4e3a29eab6a7`,
demo-islanded-ramp
`f293c4ad161357df6fef9a5e01dbb78098bfcd331c2e7e8ca286c56c9a8ef13e`,
turbine-01
`b0196383e7b4ef1110f700c762a827ce45460acdfa6792484d0d0074e61d344e`,
hybrid
`2400c1a448bd74fc37248e610c13b026f77e5634672f35142041719ded7ae0c4`,
fuel-cell/diesel
`59f042706562f949250e5eb721bdd817a30e9fd1953f16db52ef003ef3488b98`,
FC100-v2
`d381f9837605c79f8d773c98044856877d42d0cd7b7d51b99cd6db8a98610314`,
and FC100-zero-hot-v2
`952856bb0068913efe767d80ec200f4ca5c0dc8807f5555664e79c4b18965559`.
S10 is the intentional scenario replacement: its seed-42 existing-gate hash
is `f230ae8f141183e1e6bcdb8dda0eb8f4920bf5674167bba972e4a72f37c64353`,
not the prior S10 hash `107c7a5766f99f79d750b50401c8e3341d2b350e18156a312db13ab82679876a`.

The base-demo, H1-24h and H2-24h seed-42 study pairs each returned PASS with
all 10 comparison conditions true. Their baseline/informed physical hashes
match the saved D6-F records exactly:

| Study | Baseline hash | Informed hash | Metric values vs D6-F |
|---|---|---|---|
| Base demo | `f1ebd90e589a217bbaf85264a2153a268a493a8b644c75ebbe74fd89c7f5def6` | `72cc28766574a78c44913d389207bc6cca268ac1bf29b15abd148c63af334754` | identical |
| H1-24h | `c4fa3b355b2eebf949f1f0ad9f43b1b76770cf05bb380d224a3282699985fc20` | `437d480102d11676df747a5ddc742cd29c9785956c1255098dc8d00d9f18a264` | identical |
| H2-24h | `603441374503951709dc77d5ae11234e966d5b479e50edca5dd608c7782f217f` | `17954e9420ad8d0c9493a690c03cd670ae0a5f57df60f801b7c292aeea3a9fba` | identical |

All common metric values compare exactly. The raw JSON-tree comparison also
notes record-only identity/detail fields not present in one evidence wrapper;
these are listed separately in `D6B_3_STUDY_GATES.json` and are not metric
differences. H2 baseline start-fuel reconciliation remains 11 recorded / 11
measured and passes; H2 informed remains 14 / 14 and passes.

### D6b.4 test and suite results

Search found one stale S10 additivity fixture: TC-ISL-51 in
`tests/test_d6a_non_gpu_load_profile.py`. The test now derives its no-CPU
control from the tracked S10 by removing only `non_gpu_load_profile_mw`
(`:314–332`); its assertions are unchanged. The comment cites D6b. The focused
test passed: `1 passed in 120.28 s`.

Both complete real-package suite runs produced the same failing-ID set:

| `PYTHONHASHSEED` | Passed | Failed | Skipped | Xfailed | Xpassed | Added vs Phase 6c | Removed |
|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 2,243 | 15 | 3 | 23 | 0 | none | waived `test_gpu_load_profile` |
| 987654321 | 2,243 | 15 | 3 | 23 | 0 | none | waived `test_gpu_load_profile` |

The GPU test passed in both full-suite runs. The 15 remaining failures are
exactly the common Phase 6c set, including the three Gridley tests; neither run
has an added failure. Failing IDs and JSON summaries are saved under
`tools/dr_isl/d6b/`.

### D6b.5 commits and repository hygiene

- Scenario replacement: `03476900f0bf1813f6e459c54e75c21946e019bc`
  (`Update scenario configuration for S10 mit supercloud`); this pre-existed
  the resumed run.
- Test-only fixture update:
  `fdcf0424a5b7645eaef30272cc4391efd8fcdd5a`
  (`D6b tests: derive the no-CPU S10 additivity control from the replaced scenario`).
- The report and D6b JSON summaries/failing lists are committed separately.

No tracked file matches `slurm-log.csv`, `tres-mapping.txt`, `channels.csv`, or
`gridsignal.db`. No simulator application code or S10 JSON was changed after
the scenario replacement in this continuation.
