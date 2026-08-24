---
name: Standalone analytical proposals
description: Analytical Capacity Outlook proposals use the normal advisory gate without requiring a physics RunContext.
---

Capacity Outlook submissions can be tied to a synthetic analytical registry ID instead of an active simulation run. The AgentRegistry/AdvisoryGate owns proposal validation and pending review; RunContext is only needed for simulation time and tick-driven expiry.

**Why:** Reusing the simulation proposal route had incorrectly made an unrelated active run a prerequisite for a read-only analytical workflow.

**How to apply:** Preserve the existing `reservation` kind, AdvisoryGate validation, and pending human-review state; use a dedicated analytical registry when no run ID is supplied rather than weakening authorization or bypassing the gate.