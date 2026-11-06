---
name: Facility-cap reservation decay
description: Approved behavior for opt-in facility-cap admission reservations.
---

For grid-cap-enabled scheduler agents, reservation remainder must decay over time using the simulator's existing GPU ramp and cooling response. Do not release reservations by looking up per-job physical draw: aggregate K8S cohorts can use a different identity or disappear during scale-down. If a job ends before its projected load is realized, retain only the existing future-cooling-minus-current-cooling tail until it settles. With the feature disabled, preserve prior scenario behavior, telemetry, and RNG usage; do not change dispatch or cooling physics.

**Why:** per-job draw lookups missed aggregate cohorts, leaving reservations counted after their demand was already present. Lloyd approved timer-based decay instead of repairing lookup-based release.

**How to apply:** keep future admission-reservation changes opt-in and derive realization from the existing ramp and thermal-envelope functions, while preserving supply dispatch and physical cooling behavior.

For seeded Proxim8 queue-wave calibration, preserve the committed job-to-wave assignment in every untouched wave. Changing an early wave count before slicing a shuffled session list shifts job identities in later waves even when their counts are unchanged; transfer only the intended sessions between waves and verify unaffected IDs and arrival times byte-for-byte.

**Why:** a first-wave calibration initially changed downstream K8S assignments because allocation used a sequentially consumed shuffled list. Count-only comparisons did not reveal the unintended schedule changes.

**How to apply:** build wave membership from the baseline allocation, make explicit transfers only for waves being calibrated, and compare all other wave job/time mappings against the prior scenario.
