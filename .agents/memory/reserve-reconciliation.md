---
name: Reserve threshold reconciliation
description: Single-threshold reserve reconciliation, conditional emergency release, and approved bridge-time semantics.
---

Reserve extensions must preserve one reconciled retained-energy threshold across upstream allocation ceilings and the downstream physical guard. Emergency release does not mean every floor term may always be zeroed: the user-approved grid-forming bridge reserve stays hard while the BESS is the sole grid-forming source. No separate contingency state is implied.

**Why:** Independent upstream and downstream reserve controls can disagree, either blocking an authorized emergency release or creating a setpoint/actual-output mismatch.

**How to apply:** Any future reserve or contingency exception must preserve the single reconciled threshold and explicitly define whether it changes the upstream allocation ceiling, the downstream physical floor, or both.

## Bridge timing and dynamic-floor evidence

For a STARTING turbine, bridge timing uses its remaining startup countdown,
not another full start duration or another eligibility wait.

**Why:** The user explicitly approved remaining-countdown semantics; that start
is already in progress.

**How to apply:** Reuse the current machine countdown when extending a
grid-forming reserve; keep the start-eligibility conditions unchanged.

The user-approved bridge population also includes OFFLINE non-hot-standby
restart candidates (eligibility wait plus thermal startup), and hot standby
that the existing contingency path can release (zero wait plus thermal
startup). Diesel is excluded from this population; its separate floor remains.

**Why:** The user clarified that the reserve bridges until the soonest
synchronous machine can be on bus, including an explicitly releasable reserve,
not only a machine eligible for an ordinary direct start.

**How to apply:** Observe the existing release interlocks rather than changing
the hot-standby guard or triggering a release. Preserve basis labels
`starting_remaining`, `offline_restart`, `hot_standby_release`, or
`no restartable synchronous unit`. Warning attribution uses `d2r_bridge`;
the above-capacity warning still describes build-time state only.

For the reserve's hot-standby population, "can release" means the existing
unit interlocks under explicit release authority, before a risk event; it does
not require an active, confirmed contingency episode.

**Why:** The user explicitly selected unit readiness before an event rather
than every live contingency-release gate.

**How to apply:** Reuse the existing release-path unit helper and shared start
predicate. Do not trigger a release or change the event gates while querying
reserve readiness.

Distinguish a new below-floor discharge from holding or charging while stored
energy is already below a changed reserve target.

**Why:** A minimum restart-time basis can jump upward when a STARTING unit
synchronises and leaves the candidate set. Counting every subsequent
below-target observation as a fresh emergency release gives false violations.

**How to apply:** Evidence must retain the current floor, pre/post stored energy,
discharge power, on-bus synchronous sources and the actual physical guard. Test
the discharge action, and report below-target holdings separately.