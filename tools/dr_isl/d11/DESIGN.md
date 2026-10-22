# D11 design and diagnostic-before-fix plan

Application reference: 5225a05. D11.0 excludes channel CSVs, retaining scenario/non-CSV evidence per the user's clarification.

Original source: attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py.

- Lines 3213–3235 advance the dispatch-curtailment timer by the outer tick before frequency integration.
- Lines 3438–3440 establish the substep duration; 3458–3489 integrate frequency using the sustained pre-dump residual.
- Lines 3492–3502 apply FC ride-through changes to dynamic forcing. These lines and UFLS logic must remain unchanged.
- Lines 3693–3707 reconcile served/unserved and curtailment; 3748–3765 check the physical ledger. These must remain unchanged.
- Lines 3716 onward use the original forcing in D4 decomposition; changing that variable upstream would invalidate a non-frequency identity.

## Proposed single response calculation

One helper implements the existing linear response fraction, used for both the unchanged scheduled end-of-outer-tick ledger sink and the achieved sink at a substep. Snapshot the episode elapsed time before integration. Calculate the scheduled ledger amount from the predicted end-of-tick elapsed time, without advancing state there. Advance elapsed time from the snapshot plus elapsed substep time during integration; use exact outer dt on the last substep to avoid accumulated timer rounding changing the next tick's ledger amount.

Subtract the achieved sink from dynamic forcing immediately before the swing update. Preserve the raw supply/demand residual, FC loss adjustments and UFLS terms. Preserve reset at surplus <= 1e-12 MW. Do not introduce a new response constant.

This preserves b74830d's rotor response as a finite transient: the rotor sees the part of surplus not yet absorbed during the configured response delay, not sustained surplus after full response.

## Public telemetry definition

For islanded ticks, report the pre-damping net MW used by the last executed swing substep (dynamic supply/demand forcing, less achieved dump sink, plus shed already active for that substep). It excludes motor damping. If no swing substep executes, report zero. Grid-tied telemetry remains unchanged. Do not overwrite the raw variable used for D4; select the public field only at TickResult construction. frequency_forcing_mw is excluded from the required ISL19 non-frequency hash.

## Diagnostic before application edits

Compile the proposed evaluate_tick body in an isolated worker from a scratch source, keeping application files unchanged. Stream base/candidate TickResult pairs, excluding exactly the ISL19 non-frequency fields, and stop at the first differing field or non-frequency metric. No full tick export is written.

If a frequency-driven output changes, D11.3(a) cannot hold without violating the hard boundaries: stop with the first tick/field, retain base application code, and do not alter dispatch/protection or weaken acceptance.
