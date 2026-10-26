# IMPL-ISL-30 — announcement lead versus turbine return-to-service

**Decision:** Option A, selected by Lloyd on 2026-10-26. This is a design note only; no application, test, or scenario code is changed here.

## Rule

A forecast-informed stop of unit U is permitted only when the configured forecast/announcement lead is at least U's projected return-to-service (RTS) time. Otherwise, the forecast controller abstains from issuing that stop and leaves the decision to the existing measured/core commitment path. The comparison is per unit:

`forecast_lead_seconds >= rundown_and_unload_s + enabled_min_down_s + start_duration_at_earliest_restart_s + ramp_to_load_s`

The 1,200-second support lookahead remains a forecast sampling window; it is not a substitute for the per-unit RTS calculation.

## 1. Current decision paths

- `runtime/turbine_commitment.py:20-25` defines the current controller defaults: forecast lead 600 s, hot-start lookahead 300 s, ramp-to-load 60 s, and stop lookahead 1,200 s. `runtime/scenario_factory.py:2046-2052` reads `turbine_forecast_lead_seconds`, defaulting to 600 s.
- `runtime/turbine_commitment.py:809-822` skips forecast control in baseline mode and builds the informed forecast. The informed stop candidate and its min-run handling are at `:863-898`; the forecast stop is queued at `:900-911` through `:_queue` at `:1083-1110`, with source `forecast_commitment`.
- The measured/core decommit proposal is handled separately. `core/simulation_core.py:2548-2590` gates and applies it; in informed mode it calls `ForecastDrivenTurbineController.adjudicate_core_proposal`. The method is at `runtime/turbine_commitment.py:1193-1202`; its decommit forecast vetoes are at `:1232-1265`, and its min-run check is at `:1266-1275`.
- A stop transitions a synchronized turbine into unloading in `core/asset_modules.py:1159-1203`. The unloading target is minimum stable load at `core/simulation_core.py:1796-1805, 2003-2005`; after level-off, the configured unload tail runs before the breaker opens at `:2038-2067`. The breaker-open time is where `_stop_time_s` and `_last_sync_stop_s` are recorded (`:2064-2066`).

## 2. Per-unit RTS inputs

The RTS preview must live behind one shared per-unit helper, called by both the forecast-stop candidate path and the informed core-proposal adjudicator. It must read the unit's `TurbineConfig`/asset-module values; it must not copy the minimum-down or thermal-state rules into the controller.

1. **Rundown and unload:** project the existing unloading behavior from the unit's current output to its configured MSL, using its configured `r_asset_mw_per_s` and the existing tick interval, then add `unload_tail_s`. The unit is held at MSL while unloading (`core/simulation_core.py:1796-1805, 2003-2005`); the unload-tail clock starts after level-off, and the breaker opens after that configured dwell (`:2038-2067`). `TurbineConfig.r_asset_mw_per_s` is catalogue-backed (`core/models.py:767`); `unload_tail_s` is also catalogue-backed (`:855-859`). This term therefore depends on current output and per-unit configuration, not a fixed fleet-wide rundown number.
2. **Minimum down:** add `t_min_down_s` only when `min_down_enabled` is true. Factory-built scenario units default to 900 s and enabled, with per-unit overrides allowed (`runtime/scenario_factory.py:975-987`). The actual start interlock reads those values in `core/asset_modules.py:1061-1071`; its clock begins at breaker opening (`core/simulation_core.py:2064-2066`).
3. **Thermal start duration:** determine the thermal tier at the *earliest restart*, after projected breaker opening plus the enabled minimum-down interval, then use that unit's `hot_start_s`, `warm_start_s`, or `cold_start_s`. The existing resolver is `core/asset_modules.py:1073-1091`, and the actual command uses it at `:1105-1116`. The preview should reuse this resolver with the projected stop-completion reference time (or factor that resolver so actual and projected starts share one implementation). Do not classify from the unit's current online state. The model's thermal cutoffs are unit config values (`core/models.py:848-854`); a 900 s minimum-down interval is within the default one-hour hot threshold, so a just-stopped unit is HOT at its earliest restart unless its configuration overrides those values.
4. **Ramp to load:** derive time from the unit's configured ramp rate, not the controller-wide `DEFAULT_RAMP_TO_LOAD_SECONDS=60` (`runtime/turbine_commitment.py:20-25`). The proposed conservative target is the unit's rated MW, giving `rated_mw / r_asset_mw_per_s`; use the existing rate-limited loading implementation (`core/simulation_core.py:2003-2005`, per-unit rate in `core/models.py:767`). **PROPOSED_HERE:** using full rated output is a conservative capacity-restoration target because the current stop policy reasons about synchronized rated capacity. If a future design defines a smaller explicit support target, use that target instead; do not silently substitute a fixed duration.

If a required timing input is absent, non-finite, or unusable (for example a missing start duration or non-positive ramp rate), RTS is unknown. Fail closed for the *forecast stop*: do not queue it, record `return_to_service_time_unavailable`, and defer the unit to the existing core decision path. Never treat an unknown term as zero.

## 3. Meaning of “the conventional rule decides”

- For a forecast-generated stop at `runtime/turbine_commitment.py:900-911`, an RTS failure suppresses only that forecast command. It does not create a substitute stop decision and does not mutate the unit or pending-command state. The regular measured/core commitment engine continues to run.
- For a measured `decommit` proposal in informed mode, if the RTS gate says forecast authority is unavailable, the controller should abstain from its forecast-specific decommit veto/approval and pass the existing core proposal through. Keep independent physical guards: the sequential-unload gate at `core/simulation_core.py:2552-2565`, `command_stop` interlocks, and the min-run check at `runtime/turbine_commitment.py:1266-1275`. Do not call a second baseline controller or reproduce its rule. The core proposal already is the conventional decision.
- If `forecast_lead_seconds >= RTS`, the existing informed stop proposal and forecast adjudication continue under their existing thresholds. The new rule only gates whether forecast control has enough lead to own the stop.

This interpretation prevents the forecast layer from originating or overriding a stop when its announcement window is shorter than the unit's return time, while preserving one conventional decision implementation.

## 4. Refusal and evidence

Recommended reason string:

`forecast stop deferred: announcement lead {lead_s:.0f}s < return-to-service time {rts_s:.0f}s; conventional core decision retained`

For an unknown term, use:

`forecast stop deferred: return-to-service time unavailable ({missing_term}); conventional core decision retained`

Record a no-state-change refusal (`accepted=false`, `changed_state=false`, source `forecast_commitment`) for the suppressed forecast command. For a core proposal passed through by abstention, retain source `core_commitment_proposal` and mark controller approval as abstained (`null`), rather than claiming the forecast approved it. Keep the existing timestamp, unit, action, reason/refusal reason, state transition, and approval fields (`runtime/turbine_commitment.py:138-177, 1120-1141, 1277-1298`). Add auditable RTS evidence to the record/metadata: configured lead; rundown/unload; minimum-down enabled/value; projected breaker-open and earliest-restart times; projected thermal tier and start duration; ramp target, rate and duration; total RTS; and any missing-term reason.

## 5. Test plan

The current test search found D6e IDs `TC-ISL-74` through `TC-ISL-79`; no collisions were found for the proposed `TC-ISL-80` through `TC-ISL-85`.

- **TC-ISL-80 — equality/allowed:** lead exactly equals computed per-unit RTS; a forecast stop may proceed.
- **TC-ISL-81 — insufficient lead:** lead below RTS; no forecast stop is queued and the refusal contains both values.
- **TC-ISL-82 — per-unit calculation:** units with different minimum-down, start duration, rate, or unload configuration produce their own RTS; changing one unit does not change another's result.
- **TC-ISL-83 — missing timing input:** RTS is unknown, the forecast stop is deferred (not treated as zero), the reason identifies the missing term, and the core path remains available.
- **TC-ISL-84 — baseline untouched:** baseline mode still bypasses forecast control and its measured/core decision and physical result are unchanged.
- **TC-ISL-85 — S10 regression case:** with the 600 s forecast lead, the forecast stops seen at 16,160–16,170 s are refused as forecast-origin commands when the target unit's RTS exceeds 600 s. Assert that this does not assert the absence of a conventional core proposal or a core-origin stop.

## 6. Configuration-based expected scope (no simulation runs)

All four requested study inputs use the 600 s factory forecast-lead default unless overridden (`runtime/scenario_factory.py:2050-2052`). A factory turbine has minimum down enabled for 900 s by default (`:975-987`). Thus the minimum-down term alone exceeds the configured lead for all such units; start, ramp and rundown terms are additional. The new gate will therefore change which layer owns at least some stop decisions in each of these scenarios:

| Scenario | Config evidence | Expected RTS comparison |
|---|---|---|
| S10 | Five 15 MW units; `r_asset_mw_per_s=0.5`; 900 s min-down enabled; `cold_start_s=600` on its cold units (`config/scenarios/S10_mit_supercloud_2021-08-11.json:2169-2180`, unit details including `:2292-2305`). At earliest restart after 900 s, the configured hot threshold means HOT timing is used where a hot-start duration is available; the cold-start value applies only if the projected thermal age is cold. | Lead 600 s < RTS for units with enabled 900 s min-down. The D6h stops of turbines 4, 3 and 2 at 16,160–16,170 s are forecast-origin and should be deferred by the test case. |
| Base demo | Four 25 MW units at 0.5 MW/s, hot/warm/cold starts 300/360/600 s (`config/scenarios/scenario-uneven-multisched-01.json:173-180`); factory defaults supply 900 s enabled min-down where not overridden (`runtime/scenario_factory.py:979-987`). | 600 s < RTS for units with enabled min-down; forecast stop authority can defer to the core decision. |
| H1-24h | Compact record names the base scenario (`config/scenarios/scenario-h1-k8s-ray-24h.json:2-6`). Expansion deep-copies the base and applies the H workload/cluster expansion (`runtime/phase2b_reference.py:95-115, 123-141`); it does not replace turbine timing fields. | Same per-unit min-down and start/ramp configuration as base; 600 s < RTS. H1 informed outcomes may change and require its protected-study gate. |
| H2-24h | Compact record names the base scenario (`config/scenarios/scenario-h2-slurm-24h.json:2-6`). The same expansion retains the base turbine configuration while selecting the H2 workload family (`runtime/phase2b_reference.py:95-115, 123-155`). | Same per-unit min-down and start/ramp configuration as base; 600 s < RTS. H2 informed outcomes may change and require its protected-study gate. |

For scale only, and assuming a just-stopped unit remains within the configured hot threshold, the start durations are 300 s; a full-rated ramp is 30 s for S10 (15/0.5) and 50 s for the 25 MW base/H units (25/0.5). Adding only the configured 60 s unload tail and 900 s minimum down gives lower bounds of 1,290 s and 1,310 s respectively, before any descent from current output to MSL. These are configuration-derived estimates, not run measurements. The D6h S10 cold-start example of 600 s is not the appropriate restart tier after only 900 s offline when the configured hot threshold is one hour.

The gate is therefore expected to affect informed stop decisions in **S10, base demo, H1 and H2**. It does not change the baseline arm's policy; H1/H2 informed records are protected and must be revalidated before implementation is accepted.

## 7. Constants and assumptions

- No new numeric timing constant is proposed. Forecast lead, start durations, thermal thresholds, minimum-down duration, ramp rates, MSL, rated MW, unload tail, and tick interval come from the scenario, factory defaults, or turbine configuration.
- **PROPOSED_HERE:** use rated MW as the conservative ramp-to-load target when the existing capacity decision does not provide a smaller explicit per-unit target. Rationale: the stop decision is based on remaining synchronized capacity, so a unit should not be counted as restored capacity before it can ramp to its configured rating.
- If any configured term is unavailable, defer forecast stop authority rather than adding a fallback duration.
