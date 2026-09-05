---
name: Intrinsic block fuel-cell ramp
description: Physical layering and default derivation for block-addressable fuel-cell output changes.
---

Every synchronized, producing block obeys an intrinsic real-power ramp before optional pressure, delivered-fuel, and utilisation constraints. Fuel constraints may reduce the ramp-limited request but never increase it.

**Why:** Without a declared fuel system, blocks could move instantly from minimum stable output to full command. Optional manifold physics must add constraint, not be the only source of one.

**How to apply:** The proposed default is effective real MW per block divided by the canonical three-second fuel-to-power constant. This is the first-order lag's initial-slope equivalent, not a claim that a linear ramp reproduces an exponential response.

Synchronization establishes the minimum-stable floor after start dwell; only productive seconds remaining in the interval earn above-floor ramp credit. Stops and protection trips disconnect to zero instead of operating below the stable floor.

**Why:** Giving a just-synchronized block the entire report interval's ramp allowance recreates an instantaneous step at coarse tick sizes.

**How to apply:** Test exact dwell/tick boundaries, multi-block redistribution, and no-fuel-system operation separately. Keep the legacy aggregate model and prohibited fault-current/transformer/inverter-current surfaces unchanged.