---
name: Facility-cap admission reservations
description: Keep cap-gated admissions from treating unrealized GPU and cooling load as free headroom.
---

Opt-in facility-cap admission must reserve the unrealized remainder of previously admitted jobs across ticks, then release each reservation as the engine's GPU ramp and cooling response materialize.

**Why:** Per-tick headroom based only on the previous facility demand allowed new admissions to stack while thermal load lagged, producing a transient import-cap overshoot.

**How to apply:** Track reservations per admitted job only on the opt-in admission path. Reuse the engine's own load-realization functions and keep physical dispatch, BESS, and default-off scenarios unchanged.
