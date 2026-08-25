---
name: Production baseline seeding
description: Deployment behavior for persisted reference datasets that must exist before read-only API routes can serve them.
---

Required persisted baseline data must be bootstrapped from the application lifespan, not only from a shell entrypoint. Published artifacts can start the FastAPI module without visibly executing the configured script, and development and production databases are separate.

**Why:** The published reference-forecast route was registered and healthy but returned 404 because production had zero dataset and resolved rows; a shell-only importer did not run in the published process.

**How to apply:** Keep the importer idempotent, ensure its runtime dependencies in the production build, and log the seed/skip result during FastAPI startup. Republish before validating production behavior.