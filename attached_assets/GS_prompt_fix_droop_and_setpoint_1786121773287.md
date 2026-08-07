# Fix: droop bound, offline setpoint, warmup sweep, surplus netting

**Follows:** Diagnosis of the remaining 15. Five received their first real diagnosis; the D3/I4a attribution is now established with evidence.
**Baseline:** 15 failed / 976 passed / 16 xfailed backend; 29 frontend; `tsc --noEmit` clean.
**Scope:** four items in sequence. Items 1–2 are engine defects. Item 3 is a sweep. Item 4 is the D1 hypothesis. No test edits except where named.

The diagnosis session was the most productive in this sequence. Two of its findings are larger than the report treated them as, and one clue in it was not followed.

---

## Item 1 — The droop correction is unbounded (highest priority)

The Item 2 trace reported:

> `reserve_floor_mw` = **1 811.08 MW** … the floor is large because with turbines ramping from 0 MW, the droop correction drives `_p_dispatch_droop_mw` well above the raw GPU demand.

Raw demand was ~35 MW on a 45 MW fleet. The correction pushed it to ~1 796 MW — **a 50× amplification.** That is not a correction; it is a runaway. A real islanded plant with units at zero output sees frequency collapse, but electrical demand does not multiply by fifty.

It does not stay in the harness. `_p_dispatch_droop_mw` feeds `reserve_floor_mw`, which the fleet modal now renders as the operator's N−1 figure, so a transient during any commitment sequence can put a four-digit MW reserve floor on screen. It also plausibly shares a cause with the I3 findings — both are the frequency path behaving badly when units sit far from their setpoints.

**Diagnose before fixing.** Report:

1. The full expression for `_droop_correction_mw`, with `file:line`, and every input to it.
2. A tick-by-tick trace across the runaway: frequency, deviation from nominal, correction, and resulting `_p_dispatch_droop_mw`.
3. Whether the correction is bounded anywhere. If not, what a physically defensible bound would be — and what governs it: governor gain limits, unit rated capacity, some multiple of raw demand.
4. Whether the same unboundedness explains the I3 sign inversions.

Then propose a bound; do not implement it until the diagnosis is reported. Any constant it introduces goes in the catalogue with `CHOSEN` provenance.

## Item 2 — A setpoint is being assigned to OFFLINE units

```
gt_setpoint_mw        = 0.10506   ← full demand assigned as setpoint
turbine_output_mw     = 0.000000
pending_start_unit_id = 'gt-1'    ← still OFFLINE
```

Assigning a dispatch setpoint to a unit that cannot act on it is wrong independently of any test. Two consequences the diagnosis did not draw:

**It perturbs the frequency model.** `asset_delivery_error` is not display-only — the B1a trace shows forcing tracking it. A staged-but-unstarted unit therefore injects a spurious delivery error into the frequency path.

**The modal will draw a setpoint marker on an empty bar.** The per-unit bar renders `setpoint_mw`; an OFFLINE unit with a non-zero setpoint gets a cyan marker floating above no fill.

**Take disposition (A): gate `gt_setpoint_mw` on `SYNCHRONISED`.** Reject disposition (B) — updating D3, D3-islanded and I4a to accept the transient would record a defect as expected behaviour.

Report every consumer of `gt_setpoint_mw` before changing it, and confirm which of D4, D5 and D6 go green. Any that do not have a second cause worth reporting.

**Gate for Items 1–2: report before starting Item 3.**

---

## Item 3 — Sweep for warmup fixtures broken by the new start times

`test_tc_gt2` failed because `_N_WARMUP_TICKS = 5` gives 25 s against start times now 300–900 s, so no turbine reaches SYNCHRONISED and the contingency evaluator takes a degenerate early-exit path.

**That is a class, not an instance — and the dangerous members are the ones that now pass.** A test asserting "no contingency shortfall" against an empty `online` list goes green for exactly the wrong reason. `test_tc_gt2` failed loudly and was caught; a silently-passing sibling would not be.

Sweep every fixture that runs a bounded warmup and then asserts something about turbine state, contingency coverage, or reserve. For each, report:

- warmup duration in simulation seconds
- the start time of the turbines in that fixture
- whether any turbine reaches SYNCHRONISED within the warmup
- if not, whether the assertion is still meaningful or is now trivially satisfied

**Report the list; fix nothing.** A test passing for the wrong reason is a finding that needs a decision about whether to lengthen the warmup or pre-force the state, and that decision is per-fixture.

## Item 4 — The BESS/surplus contradiction in `test_d10`

The diagnosis left this unsettled and did not follow the clue in its own trace: **BESS pegged flat at rated 5 MW while `demo-20mw` runs turbines against a 40% MSL floor.**

A fleet in sub-MSL surplus and a BESS discharging at maximum are contradictory. Generation is above demand by construction, yet the shortfall path fires every tick.

**Hypothesis to test:** `sub_msl_surplus_mw` is not netted against `fleet_shortfall` before the BESS is dispatched — the same surplus that shows as `4.0 MW` in the I3 trace. If so, the shortfall is computed from a quantity the surplus should have cancelled, which would also explain why the taper is never eligible.

Produce a tick-by-tick trace of `p_dispatch_required_mw`, total turbine output, `sub_msl_surplus_mw`, computed `fleet_shortfall`, and `bess_output_mw`. Confirm or refute the hypothesis. **Report only — no fix.**

If confirmed, note whether it also bears on the §7.2 amendment measurement, which assumed the BESS covers a gap on the way down.

---

## Prohibited

- Implementing a droop bound before the Item 1 diagnosis is reported.
- Taking disposition (B) on the OFFLINE setpoint — no test edits for D4/D5/D6.
- Fixing anything found in Items 3 or 4.
- Editing any test assertion or fixture.
- Writing any new constant as a code literal. Catalogue it.
- Adding a module-scope numeric constant to `panels/`.
- Modifying `gridsignal_logger.py`.
- Proceeding past the Item 1–2 gate without reporting.

## Acceptance criteria

- [ ] `_droop_correction_mw` expression reported with `file:line` and all inputs.
- [ ] Runaway traced tick-by-tick; boundedness established; a defensible bound proposed with its governing physics.
- [ ] Stated whether the same unboundedness explains the I3 sign inversions.
- [ ] `gt_setpoint_mw` gated on `SYNCHRONISED`; every consumer reported.
- [ ] D4, D5, D6 status after the gate reported; any still failing given a second cause.
- [ ] Warmup sweep reported per fixture, including tests that now pass trivially.
- [ ] `test_d10` traced; surplus-netting hypothesis confirmed or refuted with the trace.
- [ ] Bearing on the §7.2 amendment stated if confirmed.
- [ ] No fixes in Items 3 or 4; no test assertions edited.
- [ ] Guards D1, D2, D3, E green; `tsc --noEmit` clean.
- [ ] Suite reported against 15 / 976 / 16 xfailed, every delta attributed.
