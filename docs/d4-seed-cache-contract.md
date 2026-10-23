# D4 seed and cache contract

This is the Phase 6 D4 seed-contract note requested under the GS-DES-SSH-001
work. The repository contains `docs/addendum-h-phase2b-results/s1-metrics-replay.md`,
which is an S1 replay report, but no separate GS-DES-SSH-001 seed-contract
design document.

## Seeded cache reuse

The run/cache identity includes the resolved root seed. A request with an
explicit seed may look up and reuse a cached result under that seed. A request
with `seed=None` draws and records a fresh root seed, always executes a fresh
run, and does not look up a cached result. If the caller later supplies that
recorded root seed explicitly, the run may be reused from the cache.

When `reuse_cache=true` but no seed was supplied, the start response reports
`cache_hit=false` and `cache_bypass_reason="seed_not_provided"`. The fresh run
is still written under its resolved-seed identity so an explicit replay can
reuse it. This preserves D4's recorded-seed replay contract while preventing
an unseeded request from being served an unrelated prior realization.

**Decision source:** DR-2026-10-20-ISLAND-COLLAPSE Phase 6c, Lloyd approval
2026-10-23. This narrows cache lookup behavior; it does not change seed
resolution, simulation physics, or physical identity.
