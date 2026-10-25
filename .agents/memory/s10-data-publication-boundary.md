---
name: S10 data publication boundary
description: User-imposed licensing and public-repository boundary for S10 trace material.
---

Lloyd ruled on 2026-10-25 that the specific S10 scenario-description licence warning is unnecessary because the source data comes from MIT's public repository. The user authorized removing that sentence from the tracked S10 description and generator output. This does not remove other licence notes; the route comment and SuperCloud tool comments were left for a separate decision. Per-tick diagnostic channel CSVs must stay local and out of Git.

For D11 evidence hygiene the user explicitly clarified: “Keep the S10 scenario and non-CSV evidence tracked; exclude channel CSVs.” Do not untrack the scenario or non-CSV evidence on the basis of the earlier ambiguous wording.

**Why:** The 2026-10-25 ruling supersedes the S10 description warning only; it did not authorize deleting other notices or publishing raw data and channel CSVs.

**How to apply:** Keep the S10 description and generator free of the removed sentence. Leave remaining notices unchanged unless separately directed, and keep raw data and per-tick channel CSVs out of Git.
