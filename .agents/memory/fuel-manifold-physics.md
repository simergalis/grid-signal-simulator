---
name: Fuel manifold physics
description: Non-obvious Stage 2 pressure defaults, conservation boundary, and common-mode reserve rule.
---

Fuel pressure bands are evaluated at the hydraulically furthest block inlet, after distribution loss. Preserve the vendor supply/minimum values of 15/12 psig; use the revised proposed 9.5 psig trip threshold and 920 ft³ default manifold volume.

**Why:** With 138 blocks and the specified first-order pressure-drop equation, the original 10 psig trip and 767 ft³ default conflicted with the requested outcomes after the 0.5 psi distribution loss. Revising only proposed values keeps vendor inputs intact: 500 ft³ derates without tripping, 767 ft³ derates, and 920 ft³ avoids derate.

**How to apply:** Test the full pre-staged fuel-flow step at requested electrical commitment rates from 0.5–4 blocks/s; manifold minima should remain rate-invariant. Pressure alerts are one common-mode manifold event, and constrained blocks must not regain independent fast-reserve credit.

The manifold is an explicit gas inventory buffer. Blocks may temporarily draw more than a capped regulator supplies; that deficit must appear as falling pressure. Do not hard-cap cell flow directly to regulator flow or the capacitance model disappears.

**Why:** The governing balance is regulator inflow minus block draw. A larger manifold legitimately bridges a supply shortfall longer, while a finite manifold eventually reaches derate/trip pressure.

**How to apply:** Enforce the regulator cap at initialization and every substep, integrate pressure from the inflow/outflow difference, and integrate consumed fuel from delivered cell flow.