---
name: Reserve threshold reconciliation
description: The normal BESS reserve and diesel-derived SoC floor share one live threshold with a one-tick emergency release.
---

The final retained-energy threshold is the maximum of the configured normal-dispatch reserve and the diesel synchronization floor. The live path must compute that threshold once, use it for upstream normal/reserve ceilings, and pass the same per-unit values downstream. The existing balance-based emergency-release condition may authorize the retained energy for that tick by passing a zero physical floor; no separate contingency state is implied.

**Why:** Independent upstream and downstream reserve controls can disagree, either blocking an authorized emergency release or creating a setpoint/actual-output mismatch.

**How to apply:** Any future reserve or contingency exception must preserve the single reconciled threshold and explicitly define whether it changes the upstream allocation ceiling, the downstream physical floor, or both.

## Bridge timing and dynamic-floor evidence

For a STARTING turbine, bridge timing uses its remaining startup countdown,
not another full start duration or another eligibility wait.

**Why:** The user explicitly approved remaining-countdown semantics; that start
is already in progress.

**How to apply:** Reuse the current machine countdown when extending a
grid-forming reserve; keep the start-eligibility conditions unchanged.

Distinguish a new below-floor discharge from holding or charging while stored
energy is already below a changed reserve target.

**Why:** A minimum restart-time basis can jump upward when a STARTING unit
synchronises and leaves the candidate set. Counting every subsequent
below-target observation as a fresh emergency release gives false violations.

**How to apply:** Evidence must retain the current floor, pre/post stored energy,
discharge power, on-bus synchronous sources and the actual physical guard. Test
the discharge action, and report below-target holdings separately.