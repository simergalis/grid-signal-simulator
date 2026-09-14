---
name: Simulator workflow ownership
description: Which managed workflow serves the GridSignal FastAPI simulator during local verification.
---

The GridSignal FastAPI simulator is served by the managed `artifacts/gridsignal: web` workflow. The similarly named `artifacts/api-server: GridSignal Simulator` workflow is a separate Node service and does not load the simulator code.

**Why:** Restarting the Node workflow does not reload simulator changes and can make API verification appear stale; the simulator process also keeps custom scenario state in memory across its own lifetime only.

**How to apply:** After changing simulator backend code, restart `artifacts/gridsignal: web`, then restore or recreate any custom in-memory scenario before testing.