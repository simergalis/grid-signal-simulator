---
name: Phase 2b Stage 2b-1
description: Reference-scenario expansion and deterministic demand replay for Addendum H Phase 2b-1.
---

Compact Phase 2b catalogue records must be metadata-only. Runtime expansion must start from the unchanged Phase 2a base and must not overlay Pydantic model_dump defaults such as empty turbine, BESS, or workload arrays.

**Why:** A compact record is often passed through ScenarioSpec.model_dump() before run construction; defaulted empty arrays otherwise silently erase the base topology.

For power-reactive background agents, capture the live baseline workload-signal stream and its per-tick compute plus lagged cooling demand, then replay the demand trace identically in baseline and informed comparisons. Keep signal capture opt-in for normal runs. Stage 2b physical energy closure uses the authoritative supply/load ledger; retain D4 routing defects as diagnostics rather than conflating them with the physical-ledger gate.

**How to apply:** Use this pattern for later reference-scenario comparisons whenever demand generation can observe prior-tick dispatch state. Do not run Stage 2b-2 or sensitivity sweeps until the user explicitly confirms.