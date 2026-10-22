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