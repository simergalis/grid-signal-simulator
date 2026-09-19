---
name: Forecast-history determinism
description: Durable result of comparing bounded and unbounded forecast history in the H-1 informed replay.
---

The forecast-history bound is currently diagnostic storage, not a control input:
the H-1 24-hour informed replay produced identical fuel, unserved energy, peak
unserved power, compute trace, and the full determinism metric set with two
retained snapshots and with unbounded logical history.

**Why:** A retained-history change should not be treated as a physics defect
without a strict same-input comparison; the controller consumes only the
latest forecast in this path.

**How to apply:** If forecast history is changed again, rerun the H-1 bounded
versus unbounded comparison before changing commitment policy or engine
physics. A first divergent simulated time makes the bound a behavioral defect
candidate.