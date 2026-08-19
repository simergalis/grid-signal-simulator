---
name: Cost-based local source dispatch
description: Durable merit-order and physical-floor rules for BESS, turbine, and fuel-cell dispatch
---

# Cost-based local source dispatch

## Rule

Live local dispatch must follow configured marginal cost for discretionary
capacity:

1. BESS — $38/MWh
2. Gas turbine — $55/MWh
3. Fuel cell — $65/MWh

Already committed turbine output at minimum-stable load, in a ramp, or held by
a minimum-run constraint is a physical must-run floor. Rank only discretionary
capacity above that floor. The fuel cell fills residual demand only after
actual cheaper-source delivery is known.

**Why:** A fuel-cell-first override contradicted the configured economics and
could allocate fuel-cell output against turbine MW that could not instantly
disappear, producing a generation/consumption mismatch.

**How to apply:** Use one catalogue-backed ranker for live physics and advisory
telemetry. Allocate BESS first, then incremental turbine headroom, then
fuel-cell capacity. Reconcile final fuel-cell output from actual BESS and
turbine delivery so ramp or SoC clipping cannot double-count supply, and
preserve the source-sum identity.

## SJ-1 storage interpretation

The SJ-1 site keeps its 30 MW / 60 MWh BESS as storage. “Only fuel cell and
grid” excludes solar generation; it does not disable battery discharge.

**Why:** The site specification deliberately includes the BESS, and the
confirmed merit order makes its lower-cost discharge the expected first source
while energy remains available.

**How to apply:** Treat a zero-solar SJ-1 tick with BESS output as correct.
Fuel-cell and grid output take over only after the battery cannot meet demand
within its state-of-charge and power constraints.
