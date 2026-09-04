---
name: Block fuel-cell readiness
description: Physical and advisory rules for block-addressable fuel-cell arrays.
---

For block fuel-cell arrays, contingency capacity is state- and time-dependent. Count running-block upward headroom plus hot-standby blocks whose complete hot-start and readiness dwell fit the actual event lead window. Never substitute installed capacity or manufacture a longer fast window. Cold, warming, and controlled-cooling blocks contribute zero.

**Why:** Crediting running nameplate double-counts output already serving load, while crediting cold or not-yet-synchronized blocks can make reserve appear sufficient when generation cannot physically arrive.

**How to apply:** Keep declining hot-commitment and persistent cold-capacity deficits as separate records. Readiness changes remain advisory until hot-hold fuel cost is calibrated, and diesel final reserve changes consequences rather than firm-reserve sufficiency.

BESS dispatch must follow signed physical net imbalance after achieved fuel-cell output: positive imbalance discharges, negative imbalance charges, and zero leaves the battery idle. Fuel-cell commanded-versus-achieved gaps remain readiness telemetry and must not independently dispatch the battery. In island mode, grid-forming BESS discharge remains capped at rated power minus anchor reserve; excess physical deficit is unserved load.