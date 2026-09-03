---
name: Production baseline seeding
description: Deployment behavior for persisted reference datasets that must exist before read-only API routes can serve them.
---

Required persisted baseline data must be bootstrapped from the application lifespan, not only from a shell entrypoint. Published artifacts can start the FastAPI module without visibly executing the configured script, and development and production databases are separate.

**Why:** The published reference-forecast route was registered and healthy but returned 404 because production had zero dataset and resolved rows; a shell-only importer did not run in the published process.

**How to apply:** Keep the importer idempotent, ensure its runtime dependencies in the production build, and log the seed/skip result during FastAPI startup. Republish before validating production behavior.

Seeded scenario JSON loading currently resolves relative paths from the simulator
backend's working directory, so local probes and tests must run from the
`gridsignal_sim` service directory (the configured service does this already).

**Why:** Running the same seeder from the package parent silently skipped every
JSON entry because the relative `config/scenarios` path no longer resolved.

**How to apply:** When validating seeded scenarios outside the service workflow,
change into the backend directory first; do not interpret a missing catalog entry
from another working directory as a missing seed file.