---
name: Diesel Phase 2 boundary
description: Phase 2 diesel state coordination is now consumed by the Phase 3 live accounting path.
---

Keep DieselFleetCoordinator outside DispatchArbitrator: evaluate_tick() supplies the pre-diesel measured gap, steps the coordinator once, then reuses its aggregate measured output for curtailment and local-generation accounting.

**Why:** Diesel remains advisory/read-only under TC-68, while its validated state machine must affect both the curtailment gap and physical balance without becoming a commanded arbitrator source.

**How to apply:** Preserve the empty-fleet `0.0` output contract and never add diesel commands or an arbitrator constructor/tick parameter unless a later phase explicitly changes the authority boundary.