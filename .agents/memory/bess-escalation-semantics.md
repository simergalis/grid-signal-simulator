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

Zero bridge duration does not by itself mean stored energy is exhausted. When
the binding predicted shortfall exceeds the anchor-adjusted BESS MW ceiling,
label the condition as power-limited even if state of charge is 100%.

**Why:** Bridge duration intentionally collapses to zero for an infeasible power
request; describing that as depleted reserve contradicts the live SoC reading.

**How to apply:** Use the bridging basis when writing operator copy. Predicted-
peak zero-bridge states should name the power limit; do not infer energy
depletion from duration alone.