---
name: BESS escalation semantics
description: Compatibility rules for bridge-floor and turbine catch-up operator warnings.
---

The bridge-floor warning and turbine-catch-up warning are independent. A site
without eligible turbines suppresses only the catch-up warning; it may still
raise the bridge-floor warning.

Keep their active state on a dedicated BESS escalation channel rather than
folding it into the legacy insufficient-reserve alert.

**Why:** The legacy reserve alert feeds historical scenario assertions and
verdicts. Reusing it for the new early warning silently changes those verdict
semantics, while suppressing both warnings on no-turbine sites defeats the
independent bridge-floor protection.

**How to apply:** New operator surfaces may latch or display the dedicated BESS
escalation evidence, but existing reserve assertions should retain their prior
meaning. Eligibility checks apply only to turbine convergence logic.