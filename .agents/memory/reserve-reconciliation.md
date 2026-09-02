---
name: Reserve threshold reconciliation
description: The normal BESS reserve and diesel-derived SoC floor share one live threshold with a one-tick emergency release.
---

The final retained-energy threshold is the maximum of the configured normal-dispatch reserve and the diesel synchronization floor. The live path must compute that threshold once, use it for upstream normal/reserve ceilings, and pass the same per-unit values downstream. The existing balance-based emergency-release condition may authorize the retained energy for that tick by passing a zero physical floor; no separate contingency state is implied.

**Why:** Independent upstream and downstream reserve controls can disagree, either blocking an authorized emergency release or creating a setpoint/actual-output mismatch.

**How to apply:** Any future reserve or contingency exception must preserve the single reconciled threshold and explicitly define whether it changes the upstream allocation ceiling, the downstream physical floor, or both.