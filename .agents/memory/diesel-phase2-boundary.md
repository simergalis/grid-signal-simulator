---
name: Diesel Phase 2 boundary
description: Phase 2 diesel behavior is coordinated and tested independently of live dispatch.
---

Phase 2 diesel state and fleet coordination must remain standalone; do not add diesel to dispatch arithmetic, balance residuals, UI, or telemetry until the later integration phase.

**Why:** The state machine, failover, unloading reversal, and shared fuel-yard behavior need deterministic regression coverage before changing the simulator's established power-balance path.

**How to apply:** Use `SimulationState.diesel_units` and `DieselFleetCoordinator` for isolated scenarios. Treat live dispatch/EDL/balance wiring as a separate, explicitly scoped change.