---
name: Addendum H Phase 2a physics ordering
description: Ordering contract for islanded surplus, frequency forcing, and explicit dispatch curtailment.
---

Lloyd's D11/D11-t decisions supersede the earlier sustained-surplus ordering: preserve rotor exposure as a finite dump-response transient, not indefinite forcing from energy already absorbed by the sink. Keep the physical ledger and control policy separate from this frequency-only change.

Public frequency forcing follows the post-trip reconciliation contract minus the reconciled ledger sink. It is not necessarily the last integrated substep's forcing: a fuel-cell trip can occur after that substep.

**Why:** Lloyd explicitly amended the D11 telemetry requirement after it conflicted with IMPL-ISL-10's post-trip accounting assertion. Changing trip timing or physics to make public telemetry equal the last substep would violate that decision.

**How to apply:** Distinguish substep integrator evidence from reconciled end-of-tick telemetry in tests and reports. Preserve same-tick transient exposure without changing the ledger sink, dispatch, protection or trip logic. Frequency-only changes require non-frequency hash and metric identity checks.