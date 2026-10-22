---
name: Diesel dispatch minimum scope
description: Approved scope of the diesel minimum-load proxy versus the unloading trajectory
---

The proposed 30%-of-rated diesel minimum applies to SYNCHRONISED operation, not to UNLOADING. UNLOADING may follow its existing ramp below 30%, while remaining counted in on-bus power and fuel until breaker opening.

**Why:** The user explicitly selected “Allow the existing unloading ramp below 30% (recommended)” when the minimum and preserved unloading trajectory conflicted. The 30% figure is a modelling proxy from the user's NFPA 110 test-load reference, not a claim that NFPA mandates this continuous-operation minimum.

**How to apply:** Do not clamp an unloading tail to the synchronized minimum or open its breaker early to enforce that minimum. Keep the configured unloading trajectory distinct from the normal synchronized dispatch bound.

The user superseded the prior authorization for a dispatch-aware availability gap. The coordinator must receive the achieved pre-diesel residual after all non-diesel allocation, including emergency BESS release, computed once in that allocation pass.

**Why:** The user explicitly replaced “Authorize a dispatch-aware gap signal” with the post-dispatch residual.

**How to apply:** Keep the coordinator as lifecycle owner. Do not substitute capacity or availability for achieved delivery, add a second allocation, or alter START/debounce/minimum-run/restore/cooldown settings.

The user withdrew the criterion requiring identical START lists. START trigger code must remain unchanged; START outcomes may differ after the first diesel on-bus tick because D10 changes subsequent site state.

**Why:** The user explicitly revised acceptance to distinguish unchanged trigger code from changed outcomes due to diesel output and BESS SoC history.

**How to apply:** Require physical-tick identity before the first on-bus tick in either version and trace later output/SoC/decision divergence rather than rejecting a later changed START list by itself.

Conformance requires same-state allocation equality while diesel is off bus, using the same allocator with zero diesel contributions.

**Why:** The user replaced whole-trajectory off-bus equality with restoration of identical historical simulation states into both versions before comparing one allocation.

**How to apply:** Compare turbine/BESS/FC output, curtailment and pre-diesel residual on the same restored state, within the user's 1e-12 MW tolerance or float-exact. Keep this distinct from the pre-on-bus whole-tick identity gate.

The reviewed lifecycle audit permits D10 plumbing in addition to IMPL-ISL-14/15; it is not restricted to an IMPL-ISL-14/15-only full-method diff. START logic must remain unchanged.

**Why:** The user accepted the reviewed audit in substance and explicitly amended the too-narrow criterion to “START logic unchanged; stop/unloading changes limited to D10 plumbing and IMPL-ISL-14/15”.

**How to apply:** Classify delivery/capability/fuel-phase plumbing separately from trigger predicates. Report concurrent synchronized-unit stop requests while another unit unloads; the user made this report-only, not a stop condition.
