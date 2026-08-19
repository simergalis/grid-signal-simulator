---
name: Grid import cap routing
description: Sign and balance conventions for enforcing an optional physical PCC import ceiling.
---

An enforced PCC import limit clamps only negative internal `grid_exchange_mw`; positive exchange is export and remains uncapped. Any deficit beyond the import ceiling must stay on `frequency_forcing_mw`, preserving the two-channel routing identity instead of inventing grid supply. In a grid-tied run frequency may remain nominal while `p_unserved_mw` and the physical balance defect expose the unmet demand.

**Why:** Grid exchange uses the opposite sign from the power-balance helper, and procurement capacity is advisory. Treating a procurement value as a limit or clamping both signs would either fail to enforce the physical interconnect or incorrectly block exports.

**How to apply:** Keep the cap optional so absent values preserve unlimited grid balancing. When changing grid-connected balance routing, test capped import, uncapped export, unserved demand, and the no-cap compatibility path together.