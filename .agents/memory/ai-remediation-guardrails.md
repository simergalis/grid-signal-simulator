---
name: AI remediation guardrails
description: Safety boundary for operator-facing AI recommendations in the simulator.
---

AI remediation may recommend only typed simulator commands that are revalidated against the latest tick at approval time; model output never mutates physics state directly.

**Why:** Alert telemetry can become stale while an operator reviews a recommendation, and broad natural-language actions could bypass simulator operating constraints.

**How to apply:** Keep the allowlist narrow, require explicit reviewer identity, reject stale recommendations, and route accepted commands through RunManager validation so the physics engine remains authoritative.

Alert modals are incident-level, not tick-level: retain one latch while an alert is active, suppress repeats after an operator command until telemetry recovers, and allow explicit acknowledgement to expose a later alert.

**Why:** Alert flags can remain true across many telemetry ticks, and treating each tick as a new incident repeatedly interrupts the operator after the action is already underway.

**How to apply:** Keep the active latch stable, clear action suppression only after the relevant flag is false, and preserve the existing explicit-acknowledgement path for genuinely new operator review.