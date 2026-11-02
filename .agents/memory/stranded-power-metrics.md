---
name: Stranded power metrics
description: Shared formulas for stranded-capacity metrics across run surfaces.
---

Any live, completed-run, or study-harness stranded-power output must use the existing `study_harness.stranded.compute_stranded` helper. Do not port its formulas into the frontend, API route, or another metrics module.

**Why:** The user approved one shared calculation path so live and post-run figures stay consistent.

**How to apply:** Feed the shared helper the relevant tick rows, available-capacity value, reserve policy, and tick interval; add adapters or presentation around its result, not a second implementation.
