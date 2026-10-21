---
name: Diesel dispatch minimum scope
description: Approved scope of the diesel minimum-load proxy versus the unloading trajectory
---

The proposed 30%-of-rated diesel minimum applies to SYNCHRONISED operation, not to UNLOADING. UNLOADING may follow its existing ramp below 30%, while remaining counted in on-bus power and fuel until breaker opening.

**Why:** The user explicitly selected “Allow the existing unloading ramp below 30% (recommended)” when the minimum and preserved unloading trajectory conflicted. The 30% figure is a modelling proxy from the user's NFPA 110 test-load reference, not a claim that NFPA mandates this continuous-operation minimum.

**How to apply:** Do not clamp an unloading tail to the synchronized minimum or open its breaker early to enforce that minimum. Keep the configured unloading trajectory distinct from the normal synchronized dispatch bound.
