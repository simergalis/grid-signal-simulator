---
name: Scenario catalog persistence
description: How authored simulator scenarios survive workflow and deployment restarts.
---

The simulator's ScenarioStore is process-local. A scenario created or edited only through POST/PUT exists until the FastAPI process restarts. Any scenario that must appear after publish must be represented in the checked-in seeded catalog path, preferably as a generated spec when node-level Slurm data would make a JSON fixture very large.

**Why:** Publishing restarts the simulator process, so in-memory custom scenarios disappear even though the application itself is healthy.

**How to apply:** Add durable scenarios to the seed builder with a stable ID, then verify their presence through GET /scenarios after a clean GridSignal workflow restart.