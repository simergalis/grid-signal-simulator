---
name: Reserve alert dispositions
description: Addendum E lifecycle for insufficient-reserve operator alerts.
---

An insufficient-reserve alert is linked to a deterministic Generation `turbine_ramp_rate` proposal. Approve and Reject use the existing advisory gate and must not alter physics or dispatch; Modify is intentionally not offered until Generation exposes alternatives.

**Why:** The current simulator computes aggregate reserve/ramp shortfall and exposes no ranked or alternate generation choices, so a deterministic single recommendation is safer than inventing candidate controls.

**How to apply:** Carry the proposal ID in the tick payload, record reviewer identity and disposition time in the proposal, and keep local alert dismissal contingent on a successful review response.