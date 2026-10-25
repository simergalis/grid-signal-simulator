---
name: S10 data publication boundary
description: User-imposed licensing and public-repository boundary for S10 trace material.
---

Lloyd ruled on 2026-10-25 that the S10 scenario-description licence warning and the S10 catalogue route comment are unnecessary because the source data comes from MIT's public repository. The user authorized removing both. Other SuperCloud developer/tool notes remain unless separately directed. Per-tick diagnostic channel CSVs must stay local and out of Git.

For D11 evidence hygiene the user explicitly clarified: “Keep the S10 scenario and non-CSV evidence tracked; exclude channel CSVs.” Do not untrack the scenario or non-CSV evidence on the basis of the earlier ambiguous wording.

**Why:** The 2026-10-25 rulings authorize removing the two S10-specific notices, but do not authorize deleting general SuperCloud developer notes or publishing raw data and channel CSVs.

**How to apply:** Keep the S10 description, generator output, and catalogue comment free of the removed licence note. Leave general SuperCloud tool comments unchanged unless separately directed, and keep raw data and per-tick channel CSVs out of Git.
