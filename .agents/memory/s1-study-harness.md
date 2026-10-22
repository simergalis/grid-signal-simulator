---
name: S1 study harness
description: Durable S1 harness decisions for replay metrics, start-fuel accounting, and bounded study artifacts.
---

The S1 harness must import the simulator engine and keep all cumulative-counter
arithmetic in its metrics collector.  Committed tick streams are replayed
without re-simulation, while executor runs capture baseline demand and replay
that trace in the comparison mode.

**Why:** The H-2 Slurm baseline has 940 MMBtu of measured start fuel from 71
engine start-counter events but only 30 compact recorded start/release events.
Normalizing that mismatch would hide an evidence defect.

**How to apply:** Treat hot-standby release as a charged start-fuel event
(`PROPOSED_HERE` harness policy), reconcile the event count and tier sum, and
surface mismatches as `StartFuelReconciliationError`.  Keep run records
bounded; preserve exact counts and replay assertions separately from
representative logs.

## Certified-record approval boundary

Permission to implement an engine fix does not authorize changing certified
Addendum H study records.

**Why:** The user reserves certified-record decisions for separate review.

**How to apply:** If a certified reference baseline rejects a turbine start,
report where and the resulting before/after metric deltas, then stop before
committing until the reviewer decides. Do not silently recertify the record.
The user explicitly distinguishes certified H1-24h (must remain metric- and
tick-identical) from H2-24h informed (not certified and permitted to change
under turbine start-eligibility correction, with before/after deltas reported).

For the approved start-eligibility comparison, pre-rejection differences may
affect only commitment decision telemetry (action, target, blocked-by, reason),
and only when the baseline proposed an ineligible unit and actually vetoed it.
Every such tick must be enumerated with both values and the veto evidence.
Physical fields must still match; canonical full hashes retain their contract.

**Why:** The baseline exposes a core proposal in tick telemetry even when the
informed controller vetoes it before any start command. Moving eligibility
earlier can therefore change decision telemetry before the first rejected
command without changing physical state. The reviewer approved this limited
acceptance amendment on 2026-10-22, not a general waiver for prefix differences.

**How to apply:** Keep the full hash and the decision-excluded prefix comparison
separate, prove each allowed exception against the native baseline veto, and
preserve the certified H1 physical/metric identity requirement.