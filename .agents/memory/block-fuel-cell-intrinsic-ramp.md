---
name: Intrinsic block fuel-cell ramp
description: Physical layering and default derivation for block-addressable fuel-cell output changes.
---

Every synchronized, producing block obeys an intrinsic real-power ramp before optional pressure, delivered-fuel, and utilisation constraints. Fuel constraints may reduce the ramp-limited request but never increase it.

**Why:** Without a declared fuel system, blocks could move instantly from minimum stable output to full command. Optional manifold physics must add constraint, not be the only source of one.

**How to apply:** The proposed default is effective real MW per block divided by three times the canonical three-second fuel-to-power constant: about 667%/min and full scale in nine seconds. It is an engineering placeholder based on approximate 95% settling, not a validated manufacturer specification.

The manufacturer's 2,000%/min extreme-case figure includes supercapacitor assistance while the stack recovers; never present it as intrinsic stack capability. No manufacturer-published step-load response time in seconds exists for this equipment. The aggregate 60%/min and block placeholder bracket an unknown response.

Synchronization establishes the minimum-stable floor after start dwell; only productive seconds remaining in the interval earn above-floor ramp credit. Stops and protection trips disconnect to zero instead of operating below the stable floor.

**Why:** Giving a just-synchronized block the entire report interval's ramp allowance recreates an instantaneous step at coarse tick sizes.

**How to apply:** Test exact dwell/tick boundaries, multi-block redistribution, and no-fuel-system operation separately. Use one-second traces for ramp comparisons because the standard five-second cadence can hide the trajectory. Keep the legacy aggregate model and prohibited fault-current/transformer/inverter-current surfaces unchanged.