---
name: Diesel dispatch minimum scope
description: Approved scope of the diesel minimum-load proxy versus the unloading trajectory
---

The proposed 30%-of-rated diesel minimum applies to SYNCHRONISED operation, not to UNLOADING. UNLOADING may follow its existing ramp below 30%, while remaining counted in on-bus power and fuel until breaker opening.

**Why:** The user explicitly selected “Allow the existing unloading ramp below 30% (recommended)” when the minimum and preserved unloading trajectory conflicted. The 30% figure is a modelling proxy from the user's NFPA 110 test-load reference, not a claim that NFPA mandates this continuous-operation minimum.

**How to apply:** Do not clamp an unloading tail to the synchronized minimum or open its breaker early to enforce that minimum. Keep the configured unloading trajectory distinct from the normal synchronized dispatch bound.

The user superseded the prior authorization for a dispatch-aware availability gap. The coordinator must receive the achieved pre-diesel residual after all non-diesel allocation, including emergency BESS release, computed once in that allocation pass.

**Why:** The user explicitly replaced “Authorize a dispatch-aware gap signal” with the post-dispatch residual and retained the requirement that actual diesel START timing must not change.

**How to apply:** Keep the coordinator as lifecycle owner. Do not substitute capacity or availability for achieved delivery, add a second allocation, or alter START/debounce/minimum-run/restore/cooldown settings. Compare residuals and accepted starts against the approved pre-D10 baseline; stop on a difference rather than adjusting other allocation terms.

The approved gap amendment must also preserve actual diesel START timing; retaining the same Boolean predicate and timers alone does not establish this.

**Why:** The user explicitly required STOP-and-report if the gap change alters a scenario's start ticks.

**How to apply:** Compare accepted starts across affected scenarios before accepting the signal amendment. A base-demo-only match is insufficient; stop on a counterexample without implementing a repair.

Conformance must also preserve the pre-D10 non-diesel allocation whenever no diesel unit is on bus, using the same allocator with zero diesel contributions.

**Why:** The user explicitly made off-bus turbine/BESS/FC/gap equality and unchanged accepted START lists acceptance gates, not merely unchanged dispatch policy code.

**How to apply:** Gate whole trajectories as requested, including off-bus ticks after prior diesel operation. Do not weaken the gate to identical instantaneous formulas or to ticks before the first diesel start.
