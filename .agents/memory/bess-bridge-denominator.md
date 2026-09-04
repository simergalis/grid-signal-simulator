---
name: BESS bridge denominator
description: Defines the demand basis for BESS bridge power and endurance reporting.
---

BESS bridge readiness must be calculated against the residual power gap after measured non-BESS generation, with any larger pending predicted shortfall allowed to bind.

**Why:** Comparing the BESS ceiling with total site demand falsely reports “cannot bridge” when fuel cells or turbines are already serving enough load to leave a bridgeable residual.

**How to apply:** Use the same post-generation physical shortfall that drives BESS dispatch. Keep predicted-peak shortfall as an alternate binding basis, and report zero endurance only when that binding residual exceeds usable BESS power.