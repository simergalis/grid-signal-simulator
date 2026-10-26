# IMPL-ISL-30 — announcement lead versus turbine return-to-service

**Decision:** Option A, selected by Lloyd on 2026-10-26, amended by the same-day rulings IMPL-ISL-31 (“30-minute lookahead from real queue time”) and “Never below conventional.” This is a design note only; no application, test, or scenario code is changed here.

## Rule

**Never below conventional:** the forecast-informed arm may keep turbines online longer and may start them earlier, but it must never stop a unit that the conventional measured/core commitment rule would keep online. A STOP is issued only from a core commitment proposal. Forecast-origin STOP proposals are disabled; the informed forecast adjudicator may veto or delay a core-origin stop when announced workload within that unit's return-to-service (RTS) window needs the capacity. There is no second implementation of the conventional rule.

For a candidate core stop at time `t`, use the shared per-unit RTS calculation below. Consider announced jobs whose actual simulated start lies in `(t, t + RTS]`; veto only when the existing forecast/capacity comparison shows that the unit is needed to serve one or more of those jobs. If no announced job in that interval requires the capacity, the informed adjudicator does not veto on this rule. The existing physical and core guards remain in force.

The 1,200-second support lookahead remains a forecast sampling window; it is not the announcement horizon or a substitute for per-unit RTS.

## 1. Current decision paths

- `runtime/turbine_commitment.py:20-29` defines current defaults, including a 600 s forecast lead and 1,200 s stop lookahead. `runtime/scenario_factory.py:2046-2052` currently reads `turbine_forecast_lead_seconds` (default 600 s); the new announcement cap is a separate config field described below.
- `runtime/turbine_commitment.py:809-822` skips forecast control in baseline mode and builds the informed forecast. The forecast-origin stop candidate/queue path is at `:863-911`, with `_queue` at `:1083-1110`; this path must be removed or disabled for action `"stop"` while leaving forecast-origin starts/preload behavior intact.
- The measured/core decommit proposal is handled by `core/simulation_core.py:2548-2590`. In informed mode it calls `ForecastDrivenTurbineController.adjudicate_core_proposal` (`runtime/turbine_commitment.py:1193-1202`); the existing decommit forecast checks are at `:1232-1265`, and min-run check at `:1266-1275`. `_future_burst_refusal` currently constructs another restart delay at `:675-707`; consolidate its timing inputs with the one shared per-unit RTS helper in §2. Apply the announced-job/RTS veto only to core-origin stop proposals. Do not independently run or reproduce the conventional commitment algorithm.
- A stop transitions a synchronized turbine into unloading in `core/asset_modules.py:1159-1203`. The unloading target is minimum stable load at `core/simulation_core.py:1796-1805, 2003-2005`; after level-off, the configured unload tail runs before the breaker opens at `:2038-2067`. The breaker-open time is where `_stop_time_s` and `_last_sync_stop_s` are recorded (`:2064-2066`).

## 1a. Queue-time announcement policy (IMPL-ISL-31)

For a `SLURM` event with source or synthesized `submit_time_s` and actual `start_time_s`, set forecast availability to:

`announce_time_s = max(submit_time_s, start_time_s - turbine_forecast_announcement_cap_seconds)`

For `K8S` and `RAY` events, do not synthesize `submit_time_s`; retain the configured-lead policy:

`announce_time_s = start_time_s - min(turbine_forecast_announcement_cap_seconds, turbine_forecast_lead_seconds)`

The scheduler discriminator is `scheduler_type` (`SLURM`, `K8S`, or `RAY`) in the event schema (`api/schemas.py:223-230`), carried by `WorkloadSignal` (`core/models.py:162-165`) and copied during event construction (`runtime/scenario_factory.py:1726-1732`). Treat missing/unknown scheduler type as non-SLURM and use the configured-lead policy; only explicit `SLURM` jobs draw from the S10 queue-wait distribution. **PROPOSED_HERE:** this scheduler split reflects that Kubernetes and Ray queues provide much less advance visibility than Slurm.

At run start, an event whose computed announcement time is before zero is already known and is available from simulation time zero. Once announced, the forecast uses the event's actual `start_time_s`; this is an optimism caveat, because real Slurm estimated starts are not exact and this source contains actual starts but no estimate/reservation field (`tools/dr_isl/D6I_S10_QUEUE_VISIBILITY.md:88-92`).

- The current forecast cursor uses `cutoff = sim_time_s + forecast_lead_seconds` and admits starts up to that cutoff (`runtime/turbine_commitment.py:400-438`). Replace that availability test with the computed announcement time while retaining the actual start timestamp as the forecast sample time. The current 600 s lead is read by `runtime/scenario_factory.py:2046-2052`.
- Name the cap config field `turbine_forecast_announcement_cap_seconds`, read through `scenario_factory.py:2046-2052` (or the adjacent controller config construction). It must not be a code-only constant. **PROPOSED_HERE:** default the cap to 1,800 s, because Lloyd selected a 30-minute lookahead and D6i shows that this horizon captures 62.10% of summed start MW while covering 12.42% of jobs. Rationale: workload power is highly concentrated in jobs with meaningful queue time. Keep the configured legacy forecast lead separate; it still governs other forecast windows.
- S10's tracked scenario JSON currently has event start timestamps but no `submit_time_s`/submit-time field (`config/scenarios/S10_mit_supercloud_2021-08-11.json:4 onward`). The source CSV has `time_submit`; the generator/parser must preserve it on each start event, converted to seconds from the S10 day origin, alongside `timestamp` (`tools/supercloud/make_scenario.py:267-290, 448-468`; `tools/supercloud/profile_slurm_log.py:43-47, 179-192`). Carry the optional field through the scenario-event conversion at `runtime/scenario_factory.py:1683-1720` and the runtime `WorkloadSignal` model (`core/models.py:137-160`), which currently has no submit-time member. The S10 JSON must be regenerated through the generator, not edited by hand. Adding submit-time fields changes the scenario file SHA-256 and the S10 workload-event identity digest; record both new values and revalidate the S10 reference. It does not itself change baseline physics, but it can change informed decisions and therefore informed physical results.
- The base demo and compact H1/H2 synthetic workload records do not carry source submit times (`runtime/phase2b_reference.py:87-155`). Apply §9 only to their `SLURM` events. `K8S`/`RAY` events retain the configured-lead policy; H1 expansion selects `K8S`/`RAY`, while H2 selects `SLURM` (`runtime/phase2b_reference.py:123-141`).
- The generator's existing event creation has `timestamp`, node count, profile and scheduler fields but no submit-time field (`tools/supercloud/make_scenario.py:457-468`). The source-data analysis found job `s10-job-00007` submitted and started at the same second, so its announcement time is its start time and it receives 0 s warning (`tools/dr_isl/D6I_S10_QUEUE_VISIBILITY.md:64, 88-92`). Both arms therefore see that job only at start, not earlier.

## 2. Per-unit RTS inputs

The RTS preview must live behind one shared per-unit helper, used by the informed core-proposal adjudicator to decide whether a proposed stop must be vetoed. It must read the unit's `TurbineConfig`/asset-module values; it must not copy the minimum-down or thermal-state rules into the controller. It is not permission for the forecast to originate a stop.

1. **Rundown and unload:** project the existing unloading behavior from the unit's current output to its configured MSL, using its configured `r_asset_mw_per_s` and the existing tick interval, then add `unload_tail_s`. The unit is held at MSL while unloading (`core/simulation_core.py:1796-1805, 2003-2005`); the unload-tail clock starts after level-off, and the breaker opens after that configured dwell (`:2038-2067`). `TurbineConfig.r_asset_mw_per_s` is catalogue-backed (`core/models.py:767`); `unload_tail_s` is also catalogue-backed (`:855-859`). This term therefore depends on current output and per-unit configuration, not a fixed fleet-wide rundown number.
2. **Minimum down:** add `t_min_down_s` only when `min_down_enabled` is true. Factory-built scenario units default to 900 s and enabled, with per-unit overrides allowed (`runtime/scenario_factory.py:975-987`). The actual start interlock reads those values in `core/asset_modules.py:1061-1071`; its clock begins at breaker opening (`core/simulation_core.py:2064-2066`).
3. **Thermal start duration:** determine the thermal tier at the *earliest restart*, after projected breaker opening plus the enabled minimum-down interval, then use that unit's `hot_start_s`, `warm_start_s`, or `cold_start_s`. The existing resolver is `core/asset_modules.py:1073-1091`, and the actual command uses it at `:1105-1116`. The preview should reuse this resolver with the projected stop-completion reference time (or factor that resolver so actual and projected starts share one implementation). Do not classify from the unit's current online state. The model's thermal cutoffs are unit config values (`core/models.py:848-854`); a 900 s minimum-down interval is within the default one-hour hot threshold, so a just-stopped unit is HOT at its earliest restart unless its configuration overrides those values.
4. **Ramp to load:** derive time from the unit's configured ramp rate, not the controller-wide `DEFAULT_RAMP_TO_LOAD_SECONDS=60` (`runtime/turbine_commitment.py:20-25`). The proposed conservative target is the unit's rated MW, giving `rated_mw / r_asset_mw_per_s`; use the existing rate-limited loading implementation (`core/simulation_core.py:2003-2005`, per-unit rate in `core/models.py:767`). Share this ramp-to-rated calculation between start horizon and RTS; replace the separate fixed ramp addition in `_future_burst_refusal` (`runtime/turbine_commitment.py:692-707`). **PROPOSED_HERE:** using full rated output is a conservative capacity-restoration target because the current stop policy reasons about synchronized rated capacity. If a future design defines a smaller explicit support target, use that target instead; do not silently substitute a fixed duration.

If a required timing input is absent, non-finite, or unusable (for example a missing start duration or non-positive ramp rate), RTS is unknown. Fail closed for a core-origin stop: the informed adjudicator must not approve a stop whose safety cannot be evaluated; record `return_to_service_time_unavailable` and retain the unit online. Never treat an unknown term as zero. This only makes the informed arm more conservative than the core decision; it cannot create an additional stop.

## 3. Meaning of “never below conventional”

- Disable the `"stop"` branch that queues a forecast-origin command (`runtime/turbine_commitment.py:863-911`). Forecast control can still create starts/preload requests, but no forecast-only condition can decommit a turbine.
- A stop occurs only when the existing core commitment proposes `decommit` (`core/simulation_core.py:2548-2590`). The informed adjudicator at `runtime/turbine_commitment.py:1193-1202, 1232-1265` may accept that proposal or veto/delay it. It vetoes when an already-announced event is within the unit's RTS interval and the existing forecast capacity comparison says that unit is needed. If no such event needs the capacity, it does not veto on the new rule and the core proposal proceeds through the same existing sequential-unload, command-stop, and min-run guards.
- This is not “run the conventional controller a second time.” The core proposal is the conventional decision; the informed path only has authority to preserve additional capacity, never to create a stop the core did not propose.
- **Delay semantics:** a veto leaves the unit online and does not enqueue a stop. The next core proposal is evaluated again against the current announced-event set and per-unit RTS. No stop-in-rundown cancellation behavior is added by this design.

## 4. Refusal and evidence

Recommended reason string for the informed veto:

`forecast controller veto: announced workload needs unit within RTS window ({rts_s:.0f}s)`

For an unknown term, use:

`forecast controller veto: return-to-service time unavailable ({missing_term})`

Record the veto against the core proposal (not as a forecast-origin stop), preserving its unit, action, timestamp, original reason, refusal reason, state transition and approval fields (`runtime/turbine_commitment.py:138-177, 1120-1141, 1277-1298`). Include the triggering announced job IDs, submit and announcement times, actual forecast start times, required-capacity comparison, and auditable RTS terms: rundown/unload; minimum-down enabled/value; projected breaker-open and earliest-restart times; projected thermal tier/start duration; ramp target/rate/duration; total RTS; and any missing-term reason.

## 5. Test plan

The earlier search found D6e IDs `TC-ISL-74` through `TC-ISL-79`; proposed IDs begin at `TC-ISL-80`. Check these IDs again before implementation.

- **TC-ISL-80 — no forecast-origin stops:** informed evaluations never enqueue action `"stop"` from the forecast branch; start/preload behavior remains available.
- **TC-ISL-81 — announced job needs capacity:** a core-origin stop is vetoed when an announced start lies within that unit's computed RTS interval and the existing capacity comparison requires the unit; verify refusal reason and evidence fields.
- **TC-ISL-82 — no required announced job:** a core-origin stop is not vetoed by this new rule when there is no announced job needing that capacity within RTS.
- **TC-ISL-83 — per-unit RTS:** units with different minimum-down, start duration, rate, or unload configuration produce their own RTS; changing one unit does not change another's result.
- **TC-ISL-84 — unknown RTS input:** missing timing data never becomes zero; the informed adjudicator vetoes/delays the core stop with `return_to_service_time_unavailable`.
- **TC-ISL-85 — late submit, job 00007:** because `submit_time == start_time`, announcement warning is 0 s; before that event is announced, baseline and informed arms receive no advance workload notice and no event-driven difference is attributed to this job.
- **TC-ISL-86 — baseline untouched:** baseline mode bypasses forecast control; the core commitment decisions and physical results remain unchanged.
- **TC-ISL-87 — S10 16,160–16,170 s:** job 00009 is announced at `max(13,812, 16,771−1,800)=14,971 s`; at the stop evaluation it is already announced and its start lies inside the target turbine's RTS interval. Assert the core-origin stop is vetoed if the capacity comparison requires that unit; do not expect or assert a forecast-origin stop.
- **TC-ISL-88 — thermal-aware start horizon:** candidate start horizon equals the shared current-tier start duration plus rated MW divided by that unit's configured ramp rate; verify distinct hot/warm/cold and per-unit values.
- **TC-ISL-89 — cold unit starts early enough:** with an announced event and a cold eligible S10 unit, the forecast can request the start using its 600 s cold-start duration plus its configured full-load ramp time; baseline mode remains unchanged.
- **TC-ISL-90 — synthetic submit-time reproducibility:** the same resolved seed and event identity produce the same synthetic submit time across processes and both arms; a different seed may produce a different value.
- **TC-ISL-91 — scheduler-specific announcement:** verify the Slurm formula `max(submit_time_s, start_time_s-cap_s)`, the K8S/RAY configured-lead formula, capped waits, and job 00007's zero-warning case.
- **TC-ISL-92 — identity/cache isolation across run surfaces:** the prepared Slurm submit-time timeline and derivation inputs are included in base/H identity before cache lookup; changing the timeline cannot reuse a stale record in StudyRunExecutor or MCP.
- **TC-ISL-93 — baseline physics unchanged:** submit-time metadata and forecast changes do not alter the conventional baseline physical ticks or metrics.
- **TC-ISL-94 — scheduler split:** only `scheduler_type == "SLURM"` receives a synthetic submit time; K8S/RAY and missing scheduler types preserve configured lead and have no synthetic submit time.

## 6. Configuration-based expected scope (no simulation runs)

All four requested study inputs use the 600 s legacy forecast-lead default unless overridden (`runtime/scenario_factory.py:2050-2052`). A factory turbine has minimum down enabled for 900 s by default (`:975-987`), so RTS generally exceeds 600 s after including start, ramp and rundown. Under “never below conventional,” this does not authorize forecast-origin stops; it defines how far ahead announced demand can make the informed adjudicator preserve a unit after a core stop proposal:

| Scenario | Config evidence | Expected effect (reasoning only) |
|---|---|---|
| S10 | Five 15 MW units; `r_asset_mw_per_s=0.5`; 900 s min-down enabled; `cold_start_s=600` on its cold units (`config/scenarios/S10_mit_supercloud_2021-08-11.json:2169-2180`, unit details including `:2292-2305`). At earliest restart after 900 s, use the configured thermal state, normally HOT where the hot threshold applies. | Real submit/start queue times are available in the source analysis. Job 00009 has 49m19s queue wait and is announced 1,800 s before its actual start (14,971 s); it is known by the 16,160–16,170 s evaluations and may cause a core stop to be vetoed if RTS/capacity require it. Job 00007 has zero warning and affects both arms only when it starts. Removing forecast-origin stops should reduce avoidable early decommitment; informed fuel savings versus baseline will likely shrink, but only a later gated run can establish the amount. |
| Base demo | Four 25 MW units at 0.5 MW/s, hot/warm/cold starts 300/360/600 s (`config/scenarios/scenario-uneven-multisched-01.json:173-180`); factory defaults supply 900 s enabled min-down where not overridden (`runtime/scenario_factory.py:979-987`). | No source submit times exist; §9 samples modeled waits only for Slurm events, while K8S/RAY use configured lead. Forecast-origin stops disappear; core-origin stops may be vetoed when an announced burst falls inside RTS. Fuel savings from informed decommitment will likely shrink. |
| H1-24h | Compact record names the base scenario (`config/scenarios/scenario-h1-k8s-ray-24h.json:2-6`). Expansion deep-copies the base and applies H workload/cluster expansion (`runtime/phase2b_reference.py:95-115, 123-141`); turbine timing fields remain those of base. | H1 selects K8S/RAY events, so no synthetic Slurm waits apply; the configured lead is retained. Informed stops become a subset of core proposals and may be vetoed around announced demand; reduced forecast-origin decommitment likely shrinks fuel savings. Protected H1 results require a later gate. |
| H2-24h | Compact record names the base scenario (`config/scenarios/scenario-h2-slurm-24h.json:2-6`). Expansion retains the base turbine configuration and selects the H2 workload family (`runtime/phase2b_reference.py:95-115, 123-155`). | H2 selects Slurm events, so §9's seeded MW-weighted method applies; the configured lead remains the fallback for events without explicit Slurm type. Informed stops become a subset of core proposals and may be vetoed around announced demand; fuel-savings impact requires a later protected H2 gate. |

For scale only, and assuming a just-stopped unit remains within the configured hot threshold, the start durations are 300 s; a full-rated ramp is 30 s for S10 (15/0.5) and 50 s for the 25 MW base/H units (25/0.5). Adding only the configured 60 s unload tail and 900 s minimum down gives lower bounds of 1,290 s and 1,310 s respectively, before any descent from current output to MSL. These are configuration-derived estimates, not run measurements. The D6h S10 cold-start example of 600 s is not the appropriate restart tier after only 900 s offline when the configured hot threshold is one hour.

The design changes informed stop authority in **S10, base demo, H1 and H2**: it removes forecast-origin stops and permits only core-origin stops, with an informed veto where announced demand needs the unit within RTS. Baseline behavior is untouched. H1/H2 informed records are protected and must be revalidated before implementation is accepted.

## 7. Constants and assumptions

- **PROPOSED_HERE:** add the optional config field `turbine_forecast_announcement_cap_seconds`, default 1,800 s. Rationale: this is Lloyd's selected 30-minute maximum queue-visibility horizon, supported by D6i's MW-weighted queue-wait distribution. It must be configurable, not hard-coded in controller logic.
- **PROPOSED_HERE:** use the S10 empirical queue-wait CDF weighted by event MW for synthetic base/H starts. Rationale: D6i shows long waits account for a much larger share of start MW than job count; this models queue visibility as experienced by capacity.
- **PROPOSED_HERE:** apply empirical sampling only to explicit `scheduler_type == "SLURM"` events; K8S/RAY and missing scheduler types retain the configured lead. Rationale: Kubernetes and Ray queues provide much less advance visibility than Slurm.
- **PROPOSED_HERE:** sample the empirical wait distribution with replacement and one deterministic draw per job. Rationale: synthetic jobs are separate queue arrivals, while keyed per-job sampling guarantees reproducibility without coupling draws to iteration order.
- **PROPOSED_HERE:** use a dedicated D4 keyed consumer label `synthetic_queue_wait`. Rationale: keep synthetic submission-time randomness isolated from other run consumers.
- Other timing values—start durations, thermal thresholds, minimum-down duration, ramp rates, MSL, rated MW, unload tail, and tick interval—come from scenario, factory defaults, or turbine configuration.
- **PROPOSED_HERE:** use rated MW as the conservative ramp-to-load target when the existing capacity decision does not provide a smaller explicit per-unit target. Rationale: the stop decision is based on remaining synchronized capacity, so a unit should not be counted as restored capacity before it can ramp to its configured rating.
- If any configured RTS term is unavailable, do not invent a fallback duration. Forecast-origin stops remain disabled; a core-origin stop whose RTS cannot be established is handled by the fail-closed rule above and records the missing term.

## 8. Thermal-aware start horizon

Replace the fixed start horizon `DEFAULT_HOT_START_LOOKAHEAD_SECONDS + DEFAULT_RAMP_TO_LOAD_SECONDS` (currently 300 s + 60 s = 360 s at `runtime/turbine_commitment.py:20-25, 844-856`, and summed again for core-proposal adjudication at `:1222-1231`) with a per-candidate-unit horizon:

`start_horizon_s(U) = start_duration_for_current_thermal_tier(U, now) + U.rated_mw / U.r_asset_mw_per_s`

Use the same `start_timing_at(sim_time)` resolver at `core/asset_modules.py:1073-1091` that selects the actual hot/warm/cold start duration. Reuse the same per-unit ramp-to-rated calculation as the RTS helper in §2; do not add a second thermal resolver or a fixed ramp estimate. A cold S10 unit therefore uses its configured `cold_start_s` (600 s) plus its configured ramp-to-rated duration. With an event announced sufficiently ahead of its actual start, this horizon lets the informed controller request the unit early enough; it cannot provide advance action for a late-submitted job before that job is announced.

At `runtime/turbine_commitment.py:844-856`, select the eligible candidate first, compute that unit's horizon, then compare the forecast peak over that interval with synchronized capacity plus BESS allowance before queueing a start. At `:1222-1231`, use the proposed unit's own horizon when adjudicating a core commit. The baseline controller remains on its existing measured/core path and does not consume the forecast horizon.

Remove `DEFAULT_HOT_START_LOOKAHEAD_SECONDS` from the start-horizon path. Remove `DEFAULT_RAMP_TO_LOAD_SECONDS` and the corresponding fixed `ramp_to_load_seconds` controller setting after migrating both start-horizon sites (`:844-856, :1222-1231`) and `_future_burst_refusal` (`:692-707`) to the shared per-unit timing helper. Do not keep either value as a fallback. If the unit's thermal duration or positive ramp rate is unavailable, the forecast cannot calculate a reliable proactive horizon and must fail closed for forecast-origin starts (no forecast start is queued, with a diagnostic reason). Existing core start behavior and safety interlocks remain unchanged.

Test coverage is **TC-ISL-88** (formula and per-unit thermal tiers) and **TC-ISL-89** (cold S10 start lead); **TC-ISL-86/93** confirm baseline behavior and physics are unchanged.

## 9. Seeded synthetic submit times by scheduler

Use `scheduler_type` to decide whether a synthetic submit time is appropriate. For synthetic `SLURM` jobs in base/H workloads, draw one queue wait from the S10 empirical distribution and set `submit_time_s = start_time_s - sampled_wait_s` on the job's first start event. Reuse that value for later events for the same job; STARTING/SCALE updates do not draw again. Apply §1a's Slurm announcement rule. `K8S` and `RAY` jobs receive no synthetic `submit_time_s`; they retain the existing configured-lead policy `announce_time_s = start_time_s - min(cap_seconds, turbine_forecast_lead_seconds)`, currently 600 s. **PROPOSED_HERE:** this scheduler split reflects Lloyd's ruling that Kubernetes and Ray queues provide much less advance visibility than Slurm. A missing/unknown scheduler type follows the non-Slurm configured-lead rule.

**Chosen method — option (i), MW-weighted empirical queue waits for Slurm only.** Reconstruct the empirical distribution from D6i's S10 source population and the same event-power calculation, weighting each observed wait by that job's MW at start. The sample is one day: 153 jobs, including 19 jobs at or above 10 MW, so results are illustrative rather than a broad Slurm population estimate (`tools/dr_isl/D6I_S10_QUEUE_VISIBILITY.md:8-29, 53-86`). D6i reports that waits of at least 30 minutes represent 12.42% of jobs but 62.10% of summed start MW; MW weighting better represents queue visibility of capacity-relevant work than sampling uniformly by job. However, per-job MW-weighted draws only reproduce S10's aggregate MW shares approximately when the synthetic target jobs have different sizes. Use an aggregate weighted CDF/histogram without job IDs or row-level source records; provenance is in `tools/dr_isl/D6I_S10_QUEUE_VISIBILITY.md:8-29, 43-51`.

Alternatives considered:

- **Job-count empirical sampling:** preserves the frequency of job waits, but D6i's job-count median is 1 s and only 12.42% of jobs wait at least 30 minutes; this would underrepresent long-warning, high-MW work in turbine commitment.
- **Parametric distribution:** compact and easy to sample, but choosing a family and fitting its tail would add unsupported distribution assumptions and could distort the long-wait tail.
- **Size-dependent wait rule:** intuitively reflects the D6i difference between job-count and MW-weighted results, but the published report does not establish a conditional wait curve by workload size. Do not infer that relationship from aggregate statistics alone.

Implement this once in the shared scenario-expansion/workload-preparation path, not in `StudyRunExecutor` alone. The single implementation site is `runtime/scenario_factory.py:1683-1730`, the `_scripted_signal` conversion within `build_run_context_from_spec` (`:670-678`); refactor the event preparation there into one reusable helper that assigns/retains the submit-time metadata and returns the prepared event list. Carry `submit_time_s` through `WorkloadSignal` (currently `core/models.py:164` has `scheduler_type` but no submit-time field). The schema's scheduler field is `api/schemas.py:229`, copied to the signal at `scenario_factory.py:1730`.

All run surfaces must use that same helper:

- REST and UI-started runs call `build_run_context_from_spec` at `api/routes/runs.py:697-704`.
- `StudyRunExecutor` uses it for the probe at `study_harness/executor.py:395-401` and for each mode at `:463-470`; `run_pair` resolves the seed and shares the resulting replay between both arms at `:741-767`.
- MCP `start_run` executes through `mcp_server/server.py:575-584` → `StudyRunExecutor.run_mode` → `_probe` at `study_harness/executor.py:703-710` → the same context builder. MCP currently computes identity and checks cache before execution at `mcp_server/server.py:480-493`; it must invoke the same preparation helper before that lookup and pass the prepared events through, never implement scheduler-specific sampling itself. Study and MCP identities/cache keys must include the canonical prepared timeline before their cache lookups.

H1/H2 event expansion remains in `runtime/phase2b_reference.py:87-141`; its output is passed through the same helper. Do not put per-run random submit times into the checked-in base scenario or compact H1/H2 JSON. Once announced, jobs use their actual start times; this is optimistic because real Slurm estimates are not exact.

Seed each job's draw from the D4 `seed_manifest.root_seed` (`study_harness/executor.py:375-384, 741`) and a stable keyed digest of the consumer label (for example `synthetic_queue_wait`) plus the canonical job/event identity. This makes submit times reproducible across processes and identical across the two arms while allowing a different resolved run seed to produce another deterministic synthetic timeline. **PROPOSED_HERE:** use an MW-weighted empirical CDF rather than job-count sampling; rationale is that commitment responds to MW and D6i shows long queue waits are disproportionately associated with summed start MW. **PROPOSED_HERE:** use a dedicated keyed consumer label `synthetic_queue_wait`; rationale is to isolate this deterministic draw stream from all other D4 consumers.

### Identity, cache and physical-hash consequences

The checked-in base-demo JSON SHA and compact H1/H2 JSON SHAs remain unchanged because submit times are synthesized at runtime. The prepared event timeline does change. Before enabling it, fix **IMPL-ISL-28**: `study_harness/executor.py:123-140` currently removes `workload_events` from base/H identity parameters, while only S10 records a canonical workload-events digest. Include the canonical prepared timeline digest and derivation inputs (scheduler policy, queue-rule/CDF version, cap and resolved seed) in base/H and MCP identities before cache lookup; otherwise a changed synthetic timeline could reuse a stale cache entry. This changes the base/H identity digests and cache keys, so protected identity gates must be re-recorded and checked. **PROPOSED_HERE:** bump the study identity version when this identity contract changes, to prevent old cache entries from being interpreted under the new rules.

Submit-time metadata alone does not change the baseline physical hash: baseline mode does not use forecast input. The informed arm's forecasts and decisions can change, so informed physical hashes and metrics must be revalidated. The generated timestamps must be present in the shared run artifact/identity so that a recorded seed can replay the same announced workload.

Test coverage is **TC-ISL-90** (seeded Slurm waits are stable across processes, arms and run surfaces), **TC-ISL-91** (Slurm and K8S/RAY announcement formulas, including capped/late waits), **TC-ISL-92** (prepared timeline in identity/cache before lookup), **TC-ISL-93** (baseline physics unchanged), and **TC-ISL-94** (only Slurm receives synthetic waits; K8S/RAY and missing scheduler type retain configured lead).
