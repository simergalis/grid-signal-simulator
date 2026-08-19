---
name: PUE calibration contract
description: Durable interpretation, provenance, persistence, and validation rules for site PUE calibration.
---

Treat `pue_base` as non-cooling overhead and `alpha_max` as the separate additive cooling fraction. Derive steady-state effective PUE as `pue_base × (1 + alpha_max)`; do not set `pue_base` equal to a published total-PUE target.

**Why:** The simulator applies `pue_base` to compute and adds cooling separately. Using a published total PUE as the base would count cooling twice.

**How to apply:** Persist the two authoritative source values and expose effective PUE as a read-only computation. For SJ-1, the 1.37 target is Equinix’s disclosed 2025 global portfolio average; the 80% cooling / 20% non-cooling split is an industry estimate, not site-specific evidence.

The declared-range guard must compare the actual runtime `pue_base` with the catalogue’s live PARAM-06 min/max rather than duplicating bounds in scenario data or assertion parameters.

**Why:** API editing limits are intentionally permissive, while the catalogue owns declared parameter ranges.

**How to apply:** Keep the assertion parameterless, supply runtime PUE and catalogue bounds at verdict evaluation, and leave broad API validation independent from the native scenario guard.