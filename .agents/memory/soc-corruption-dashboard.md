---
name: soc-corruption-dashboard
description: How corrupted SoC is surfaced to the operator dashboard (Task #61), the field-ordering trap in TickResult, and the source-level bounds audit.
---

# SoC Corruption Dashboard Wiring (Task #61)

## The rule
`_apply_soc_corruption()` must stamp **both** `contingency_coverage` and `bess_soc_corrupted_fraction` in the same `_dc_replace` call. These two must always agree:

    bess_soc_corrupted_fraction × total_usable_mwh ≈ contingency_coverage.bess_usable_energy_mwh

**Why:** Without this stamp the dashboard showed `bess_soc_fraction` (clean physics), not the sensor reading the physics engine used for contingency. Operators saw a different SoC than what drove the contingency state.

## Field ordering trap
`TickResult` is a frozen dataclass. `bess_soc_corrupted_fraction: Optional[float] = None` must come **after** `confidence: ConfidenceBand` (which has no default), otherwise Python raises `TypeError: non-default argument 'confidence' follows default argument`. Any new Optional/default field must be placed after all required (no-default) fields.

**How to apply:** When adding a new `Optional[…] = None` field to TickResult, scan for the last bare required field (currently `confidence: ConfidenceBand`) and insert after it.

## Semantics
- `None` on clean ticks, dropout ticks, and when `|corrupted − clean| < 1e-9` after clamping.
- Non-None = the clamped corrupted reading normalised by `total_usable_mwh`, in `[0, 1]`.
- `bess_soc_fraction` (clean physics) is never altered by corruption.
