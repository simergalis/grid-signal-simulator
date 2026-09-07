---
name: soc-corruption-dashboard
description: Stored-domain telemetry corruption, deliverable contingency energy, and the TickResult field-ordering trap.
---

# SoC Corruption Dashboard Wiring

## The rule
Telemetry corruption applies to stored SoC first. Discharge efficiency applies afterwards when contingency logic converts that corrupted stored reading to deliverable energy.

The dashboard's corrupted SoC remains a stored-domain fraction. Contingency usable energy is a deliverable-domain quantity, so these values must not be equated after round-trip-efficiency support lands.

**Why:** A sensor fault changes the measured stored charge, not the stored-to-deliverable conversion. Equating stored SoC with deliverable energy either omits efficiency or risks applying corruption in the wrong domain.

**How to apply:** Preserve both the corrupted stored fraction and the corresponding deliverable contingency energy. Tests should verify `deliverable = corrupted_stored × discharge_efficiency`, while comparisons between dashboard SoC and physical SoC must continue to compare stored quantities.

## Field ordering trap
`TickResult` is a frozen dataclass. `bess_soc_corrupted_fraction: Optional[float] = None` must come **after** `confidence: ConfidenceBand` (which has no default), otherwise Python raises `TypeError: non-default argument 'confidence' follows default argument`. Any new Optional/default field must be placed after all required (no-default) fields.

**How to apply:** When adding a new `Optional[…] = None` field to TickResult, scan for the last bare required field (currently `confidence: ConfidenceBand`) and insert after it.

## Semantics
- `None` on clean ticks, dropout ticks, and when `|corrupted − clean| < 1e-9` after clamping.
- Non-None = the clamped corrupted reading normalised by `total_usable_mwh`, in `[0, 1]`.
- `bess_soc_fraction` (clean physics) is never altered by corruption.
