---
name: AI remediation guardrails
description: Safety boundary for operator-facing AI recommendations in the simulator.
---

AI remediation may recommend only typed simulator commands that are revalidated against the latest tick at approval time; model output never mutates physics state directly.

**Why:** Alert telemetry can become stale while an operator reviews a recommendation, and broad natural-language actions could bypass simulator operating constraints.

**How to apply:** Keep the allowlist narrow, require explicit reviewer identity, reject stale recommendations, and route accepted commands through RunManager validation so the physics engine remains authoritative.