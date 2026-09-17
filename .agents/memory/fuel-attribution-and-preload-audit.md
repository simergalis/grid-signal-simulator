---
name: Fuel attribution and preload audit
description: Rules for reporting turbine fuel components and compact forecast preload evidence.
---

Turbine fuel telemetry components are cumulative run counters: use the final
telemetry row per unit for total and component fuel. Dispatch-curtailment fuel
is interval attribution: add only positive per-tick increments on ticks with
explicit dispatch curtailment. Preload evidence should log target/unit
signature changes, attach suppressed-repeat counts to the prior record, and
emit one outcome per forecast burst.

**Why:** Summing cumulative telemetry once per tick inflated fuel totals and
made the informed-minus-baseline attribution unauditable; repeated forecast
evaluations also obscured the number of actual burst decisions.

**How to apply:** Preserve the distinction whenever adding smoke metrics,
acceptance reports, or tests around turbine fuel, dispatch curtailment, or
forecast preload.