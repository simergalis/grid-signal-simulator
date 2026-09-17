---
name: Addendum H Phase 2a authority boundary
description: Durable rules for baseline and informed turbine commitment behavior and evidence.
---

Baseline is measured-core-only: it must not consume forecast input, create forecast-controller actions, preload turbines, or enforce a minimum synchronized floor. Informed mode makes forecast control the single commitment authority; measured core starts and stops are proposals that receive an explicit accept/veto record. Both modes use the same physical topology and constraints, and every physical turbine transition carries source, reason, before/after state, and authority metadata.

**Why:** The fix round separates policy comparison from physical topology so smoke results are attributable to controller behavior rather than different starting assets.

**How to apply:** Preserve this boundary when extending Phase 2a reporting or tests; do not move alert lifecycle behavior or Phase 2b policy into the commitment controller.