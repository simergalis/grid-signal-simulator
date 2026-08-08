# Replit Agent Prompt — NAR-001 Phase A′ Part 2b: Generate Runs

Paste everything below the line.

---

## LEADING-TICKS RULING — proceed, do not fix

Correctly stopped. The answer is to accept the loss and record it, not to work around it.

The cost is small and bounded: I1, I2, I3, I4 and I6 are per-tick, so one missing sample out of thousands is immaterial. I5 loses exactly one difference pair. Only assertions about a run's opening state are actually damaged, and `missed_leading_ticks` already marks those recordings. Slowing every run to 1× to recover one tick is a bad trade.

**#269 — no replay buffer and no subscribe-before-start handshake.** A subscriber attaching after `POST /runs` returns cannot receive ticks already broadcast, and `broadcast()` fans out only to currently-subscribed sockets. Log it. **Do not fix it** — a replay buffer is a server-side change to `WebSocketHub` and belongs in its own task.

Two cheap additions so the race is measured rather than reasoned about:

- Record `post_returned_utc` and `ws_subscribed_utc` in the manifest, plus the derived `subscribe_window_ms`. That turns "the handshake takes roughly 0.5–1 s" into a number.
- Include **one run at `playback_speed: 1.0`** in the 2b set, specifically to test your claim that the race is narrower at 1×. Report whether `missed_leading_ticks` is false for it. Settle it with data rather than argument.

---

## TWO ITEMS TO RESOLVE BEFORE GENERATING RUNS

### R1 — The catalogue snapshot is dropping two keys

Your loader resolves **74** keys. The NAR-001 inventory §J tallies **13 adjustable + 8 enumerated + 55 locked = 76**, and states that total explicitly.

The catalogue snapshot is the entire reason the manifest exists — a snapshot that silently omits keys will produce a `ConfigDelta` that misses changes to exactly those keys, which is worse than having no snapshot at all, because it looks complete.

Identify the two missing keys by name. State whether the inventory's 76 was wrong, or your extraction is dropping entries, and which. Likely candidates are `enumerated` keys carrying `options_source` rather than a literal default, but do not assume — check.

### R2 — `scenario_id` is not sufficient run identity

You reported that `POST /runs` returns only after a pre-run generator pipeline completes — an `asyncio.gather` of solar, cluster, stressor and param-sampler generators — and that this accounts for 17.7 s against a 6 s theoretical minimum.

If those generators author scenario values at run start, then two runs of the same `scenario_id` may not be the same scenario, and two recordings would not be comparable even with identical catalogue hashes. Answer:

1. Are those generators stochastic, LLM-backed, or seeded-deterministic? Name each and say which.
2. Is there a materialised `ScenarioSpec` object after the pipeline completes, and can it be read at run-start time?
3. If it exists, **capture it verbatim in the manifest** as `scenario_spec`, plus `scenario_spec_hash`. If it cannot be captured without a server-side change, say so and stop.

Answer R1 and R2 in chat, then **stop**.

---

## PART 2b — Scenario selection

Once R1 and R2 are settled, generate the run set. The set must satisfy every criterion below; report which run covers which, and why you chose it.

| # | Criterion | Why |
|---|---|---|
| C1 | At least one scenario with `kube_config` set | `kube_metrics` was null on all 11 smoke ticks, so **I2b is currently unexercised**. Without this, the job-attribution identity is never tested. |
| C2 | At least one islanded run long enough that decommitment occurs | `t_min_run_s` is 1800 s, so this needs roughly 45–60 minutes of sim time. Exercises I6 through commit, hold, and decommit. |
| C3 | At least one grid-connected run | `grid_exchange_mw` is exactly 0.0 islanded, so I1's grid term is untested otherwise. |
| C4 | At least one run where BESS actually discharges | `bess_usable_mwh` is 2.0 on the smoke run — roughly 8 minutes at 15 MW rated. I5 is meaningless on a run where `bess_output_mw` stays at zero. Needs a step-load exceeding turbine ramp capability. |
| C5 | At least one run at `playback_speed: 1.0` | Per the ruling above. |
| C6 | At least one run reaching a shed or unserved condition, **if one exists in the scenario library** | `p_unserved_mw` was non-null but presumably zero throughout. If no such scenario exists, say so — do not construct one. |

One run may satisfy several criteria. Prefer fewer, longer runs over many short ones — the residual distributions need ticks.

Use raised `playback_speed` for the long runs where C5 does not apply, and record the value in every manifest.

---

## NOTES FROM THE SMOKE RUN

**Nullability was better than the inventory predicted, in one direction only.** `p_served_mw`, `p_unserved_mw`, the four per-block served/unserved fields, and `contingency_coverage` were all present and non-null on every tick, despite the inventory marking them Optional. Do not weaken the null rule on that basis — `kube_metrics` was null on all 11 ticks, and the checkers must still treat null as `NOT_EVALUABLE` rather than as zero or as an error.

**Log the dual-wired names as a minor defect.** `p_compute_mw` and `p_compute_demand_mw`, `p_cooling_mw` and `p_cooling_demand_mw`, `p_total_mw` and `p_demand_mw` are all emitted simultaneously with identical values. Two names for one quantity means a UI component and a checker can read different keys and never notice if they diverge. Your reading that this is deliberate backwards-compatibility is plausible but is an inference about intent — record it as an observation, not a conclusion. The checkers read the ORM-attribute names as canonical, as you proposed.

---

## DO NOT

1. Do not fix #266, #267, #268, or #269.
2. Do not modify `WebSocketHub`, `run_manager.py`, or any server-side code to close the subscribe race.
3. Do not construct or author a new scenario to satisfy a criterion. Use what is in the library; report any criterion you cannot cover.
4. Do not transform or filter the payload. Verbatim still means verbatim.
5. Do not discard a recording because `missed_leading_ticks` is true. Flag and keep.
6. Do not proceed to the checkers. That is Part 2c.
7. Do not proceed past a stop point without my reply.

## STOP AND REPORT IF

- The two missing catalogue keys cannot be identified.
- The materialised `ScenarioSpec` cannot be captured without a server-side change.
- The generator pipeline is stochastic and unseeded, so the same `scenario_id` does not reproduce.
- No scenario in the library sets `kube_config`, leaving I2b permanently unexercised.
- A recording ends with `stop_reason: dropped`.
