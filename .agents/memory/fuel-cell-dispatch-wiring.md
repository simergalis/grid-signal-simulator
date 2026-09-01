---
name: Cost-based local source dispatch
description: Durable merit-order and physical-floor rules for BESS, turbine, and fuel-cell dispatch
---

# Cost-based local source dispatch

## Rule

Live local dispatch must follow configured marginal cost for discretionary
capacity, while a configured fuel-cell array's fixed baseload output remains
an asset measurement rather than a residual-fill command:

1. BESS — $38/MWh
2. Gas turbine — $55/MWh
3. Fuel cell — $65/MWh

Already committed turbine output at minimum-stable load, in a ramp, or held by
a minimum-run constraint is a physical must-run floor. Rank only discretionary
capacity above that floor. Read the fuel-cell module's measured output before
calculating BESS shortfall or surplus; any FC surplus is a BESS charging input.

**Why:** A fuel-cell-first override contradicted the configured economics and
could allocate fuel-cell output against turbine MW that could not instantly
disappear, producing a generation/consumption mismatch. A later residual-fill
override was also wrong once the module became rate-limited and baseload-driven.

**How to apply:** Use one catalogue-backed ranker for live physics and advisory
telemetry. Allocate BESS first, then incremental turbine headroom, then
fuel-cell capacity for the remaining discretionary requirement, but never
overwrite the module's measured output with that allocation. Preserve the
source-sum identity for turbine, BESS, fuel cell, and renewable output.

## SJ-1 storage interpretation

The SJ-1 site keeps its 30 MW / 60 MWh BESS as storage. “Only fuel cell and
grid” excludes solar generation; it does not disable battery discharge.

**Why:** The site specification deliberately includes the BESS, and the
confirmed merit order makes its lower-cost discharge the expected first source
while energy remains available.

**How to apply:** Treat a zero-solar SJ-1 tick with BESS output as correct.
Fuel-cell and grid output take over only after the battery cannot meet demand
within its state-of-charge and power constraints.

## Regression-test contract

Tests for FC-backed scenarios must derive expected output from the module's
minimum stable floor, ramp rate, timestep, and fixed target. Small-load cases
should expect BESS charging when FC output exceeds demand, not an idle FC or
positive BESS dispatch.

**Why:** The old tests encoded residual-fill behavior and therefore failed even
when the measured asset output and aggregate balance were correct.

**How to apply:** Advance commitment fixtures through the module's real ramp to
cross utilization thresholds. To test hysteresis re-arm, change the configured
baseload target and let the module ramp down/up; changing site demand alone must
not change fixed FC output. Keep positive cascade coverage in direct commitment
tests; the kube black-box fixture is below its cascade threshold once FC is
fixed-baseload-driven.

## Ordinary commitment with fixed FC baseload

Ordinary turbine commitment must evaluate `max(0, dispatch_required - measured
FC output)`. The former FC-output threshold trigger is compatibility-only; it
must not release hot standby or override ordinary commitment.

**Why:** FC output is a fixed, rate-limited asset contribution. Treating its
startup ramp as a turbine-staging signal can commit generation without a site
reserve need, while failing to net its measured contribution makes reserve
utilisation overly conservative.

**How to apply:** Keep hot-standby exclusion in the ordinary offline candidate
filter until a separate release design exists. Test demand-based starts with
non-hot offline units, and separately assert that FC ramp crossings alone do
not stage turbines.
