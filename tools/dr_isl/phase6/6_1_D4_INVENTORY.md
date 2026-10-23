# Phase 6.1 — D4 randomness and clock inventory

Base code: `61e29cabd085404cf3dd600b4c535d5a0c08f899`; Phase 6.0 commit:
`f6ac65849906df7ab33654a0b126a79c9af23d04`. This is an inventory only; no
application code was changed for 6.1.

## RNGs and generated inputs

| Consumer | Current seed/source and reach |
|---|---|
| Kube/Slurm/Ray demand | `core/kube_demand.py:335,341-351` constructs one `random.Random(config.rng_seed)` and two NumPy generators from `SeedSequence(config.rng_seed)`. `KubeConfig.rng_seed` defaults to 42 (`core/kube_demand.py:168`); explicit `None` passes entropy to both libraries. These streams schedule workload and stochastic power (`core/step_scheduler.py:88-124,175-193`; `core/asset_modules.py:498-519`) and can change compute demand and tick fields. The legacy shared-fleet expansion adds offsets 0/1/2 only when the base seed is non-null (`runtime/scenario_factory.py:1277-1297`). |
| Diesel start success | `core/asset_modules.py:1364-1368` uses `random.Random()` with no seed; `:1452` draws it when start success is not already resolved. This can change diesel availability and physical output. The Phase 0b runner pins each module to `1729 + index` after build (`tools/dr_isl/baseline_runner.py:131-132`). |
| Cluster/stressor/parameter pre-run generators | `runtime/cluster_gen.py:335`, `runtime/stressor_gen.py:249`, and `runtime/param_sampler.py:134` use `random.Random(seed)`; their config seeds may be `None` (`api/schemas.py:2649-2762`; API forwards them at `api/routes/runs.py:529-571`). `None` means OS-entropy initialization. These generators create workload events, solar-step stressors, and sampled model parameters that are merged into the run spec (`api/routes/runs.py:583-610`), so outputs can affect physical ticks. `cluster_gen.py:242-275` and `stressor_gen.py:199` additionally assign UUID4 event IDs; the UUIDs identify generated events, not their numerical draws. |
| Optional external generator | The run-start route may invoke solar, cluster, and stressor generators concurrently (`api/routes/runs.py:504-581`); cluster/stressor configs default `use_llm` to true at `:542,558`. An LLM-generated forecast/timeline is not controlled by an RNG seed; its materialized samples/events enter `spec_data` (`:583-610`) and can affect physical ticks. The pinned seeder-path runner explicitly does not call these API generators (`tools/dr_isl/baseline_runner.py:2-6`). |
| Telemetry-corruption schedule | `runtime/telemetry_corruption.py:145-195` uses `random.Random(seed)`; a null seed is entropy-seeded. The run route wires a configured schedule and `RunManager` creates a second `Random(schedule.seed)` (`runtime/run_manager.py:2086-2088`). It changes observed contingency coverage, not clean physics SoC or dispatch (`run_manager.py:2925-2940`); the bridge escalation is explicitly observation/advisory-only. The pinned runner fills null corruption seeds with 1729 (`baseline_runner.py:62-67,133-142`). |
| Process-wide SolarSim | `api/app.py:266-273` constructs one `SolarSim()` with its default `seed=None` and starts a wall-clock 1 Hz ticker (`api/app.py:109-120`). `renewable/solar.py:618-621,793-815` consumes its RNG for POA and temperature noise; its event paths also randomly choose affected banks (`:906-919,932-938,985-1015`). During a run, `RunManager` sets the scenario fraction and reads the singleton's bank state to override scenario solar output (`runtime/run_manager.py:2641-2668`). `live_aggregate_mw()` itself documents that the direct fraction path consumes no RNG (`renewable/solar.py:692-707`), but the concurrent ticker can mutate the state it reads. This is a physical-path RNG and wall-cadence coupling absent from the headless seeder runner. |
| Simulated SCADA loss | `core/simulation_core.py:364` constructs `SimulatedScadaLayer(seed=42)`; `core/scada_layer.py:183-198,253-287` uses that RNG for protocol message-loss fate. Commands are recorded after dispatch (`simulation_core.py:2933-2954`), and delivered SCADA records are not read back into the physics path. It is deterministic today and observability-only. |
| Fabric simulation | `runtime/scenario_factory.py:2129` seeds FabricEngine with Python's salted `hash(run_id) % 2**31`; changing `PYTHONHASHSEED` can change it. The seed is passed to FabricEngine (`:2180`); its `fabric_modal` output is explicitly excluded from the established tick identity hash (`tools/dr_isl/baseline_runner.py:7-9,25-28`) and has no power-dispatch input path. The pinned runner replaces this seed with 1729 (`:106-112`). |
| Advisory de-identification | `core/deident.py:144,473` creates unseeded `Random()` instances for per-session/per-call pseudonymization; advisory agents call it before proposal generation (`advisory/agents/base.py:154-160`). This affects advisory evidence/proposals only, not physical tick state. |
| Random identifiers | API run IDs use UUID4 (`api/routes/runs.py:273`); absent scenario event IDs are filled with UUID4 (`runtime/scenario_factory.py:1590-1592`). They are identifiers, not RNG-driven physics. `run_id` also currently supplies the fabric hash seed above. Generated cluster/stressor UUID event IDs are noted in the generator row because they may appear in run artifacts. |

The pinned runner currently applies Python and NumPy global seed 1729
(`baseline_runner.py:120-122`), pins configured Kube seeds to 1729
(`:53-67`), FabricEngine to 1729 (`:106-112`), per-diesel RNGs to 1729+i
(`:131-132`), configured generator/corruption null seeds to 1729
(`:62-67,133-142`), and `time.time()` to `1792454400.0` (`:29-30,127`).
Those are test-tool patches; they are not a single application build-time
seed bundle.

## Clock consumers and cadence

* `RunContext.step()` creates `SimClock` with simulated time and obtains
  `wall_stamp_utc` from `time.time()` (`runtime/run_manager.py:1818-1845`).
  Core uses `clock.sim_time` for simulation time; the wall stamp is persisted
  alongside it (`core/sim_clock.py:31-56`; `runtime/persistence.py:321,999`).
  The existing physical hash excludes `wall_stamp_utc`, `advisory_telemetry`,
  `fabric_modal`, and `insufficient_reserve_proposal_id`
  (`baseline_runner.py:7-9,25-28`).
* API default-solar generation reads current UTC for local-hour/DST and
  day-of-year/elevation decisions (`api/routes/runs.py:404-500`), then passes
  the resulting time to `generate_solar_forecast` or lets it use its own
  `datetime.now()` fallback (`:504-521`; `runtime/solar_sim.py:607-626`).
  The resulting irradiance and ambient steps are inserted into the spec and
  can affect physical output (`api/routes/runs.py:583-589`). The scenario
  factory's TOU month instead uses a spec value or stable August fallback
  (`runtime/scenario_factory.py:1887-1895`).
* Advisory-agent cadence is currently wall-based: `_drive` supplies
  `time.time()` (`runtime/run_manager.py:3237-3252`); `AgentRegistry` forwards
  `wall_time` (`advisory/agent_registry.py:117-155`); `BaseAdvisoryAgent`
  gates on `wall_time - _last_run_wall` (`advisory/agents/base.py:106,112-148`).
  The gate is ticked by simulation time (`agent_registry.py:167-171`).
  Trace found no automatic advisory-to-physics write: `run_manager.py:3217-3225`
  states agents write only proposals to the gate; accepting a proposal does not
  change dispatch (`runtime/advisory_gate.py:240-253`; `api/routes/advisory.py:142-173`).
  Separately, explicit operator commands are drained before physics
  (`runtime/run_manager.py:1826-1835,2622-2626`); they are user inputs, not
  advisory output. Thus changing advisory cadence for study/headless runs does
  not change physics via the advisory path.
* `wall_clock_sleep_seconds()` paces interactive playback (`run_manager.py:1886-1894`);
  the simulated clock advances by fixed `TICK_INTERVAL_SIM_SECONDS` in `step()`
  (`:1848`). Perf-counter profiling and DB/HTTP `datetime.now()` stamps are
  measurement/metadata, not simulation input (`run_manager.py:2607-2609,3657`;
  `runtime/persistence.py:1119,1165`).
* The 1 Hz SolarSim ticker is the exception: its RNG-driven state can be read
  by the run's solar injection path above. It must be addressed in D4 by
  recording/resolving its seed and ensuring deterministic study/headless
  behavior without changing the solar equations. Interactive live operation
  remains wall-clock driven as required.

## Gate finding and D4 implementation status

The advisory-output trace remains clear: automatic agents can change proposal
artifacts but not dispatch, setpoints, commitment, or other physical fields.
The inventory identified null-seeded Kube/generator/diesel streams,
hash-based fabric seeding, API solar inputs derived from current time or
external model output, and the process-wide SolarSim ticker as D4 concerns.

The candidate now resolves a root and named consumer seeds through the single
`runtime/seed_resolution.py` manifest function, records the manifest in run
metadata/study artifacts, replaces `hash(run_id)` for fabric, records
materialized generated inputs, and keeps the same SolarSim input trace for
headless replay. The implementation and verification are recorded in
`tools/dr_isl/phase6/6_2_IMPLEMENTATION_NOTES.md`,
`6_3A_TICK_FIELD_COMPARISON.json`, `6_3A_METRIC_COMPARISON.json`,
`6_3B_UNPINNED_RESULTS.json`, `6_3B_SEED_SOURCES.json`, and
`6_3C_REPLAY_RESULTS.json`.

The explicit-seed-42 study comparisons directly replayed on the pre-D4 base
(`f6ac658`) and the candidate produced zero differing physical tick fields for
all six base-demo/H1/H2 arm runs; 31 compared metric fields per arm were equal.
The saved hashes in `6_0_EXPLICIT_STUDY_CHECK.json` did not match the fresh
base/candidate hashes, and that discrepancy is documented in
`6_3A_BASE_DEMO_GATE.json`; the retained 6.0 per-tick source rows are not
available for a field-level comparison.
