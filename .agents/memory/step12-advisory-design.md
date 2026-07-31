---
name: Step 12 advisory design
description: Build order, LP-1 short-circuit, TC-29/TC-30 wire guarantees, proposal lifecycle, and key constraints for the advisory scaffolding.
---

**Build order (non-negotiable)**
1. `core/deident.py` — egress filter; must predate any model client
2. `runtime/advisory_router.py` — model backend routing + HTTP calls
3. `runtime/advisory_gate.py` — TC-30 bounds check + proposal lifecycle
4. `runtime/advisory_principal.py` — orchestration

**LP-1 short-circuit**
Both AdvisoryRouter and AdvisoryPrincipal check `has_agent` (bool: either key present) at the top of every public method. No key → immediate None return, no network calls, no errors. Keys are read once at `__init__` — changing env vars mid-run has no effect.
**Why:** prevents race conditions; LP-1 test monkeypatches env before import.

**TC-29 (at the wire)**
`deidentify(ticks, site_id=..., job_id=..., hardware_profile_ids=...)` — identifiers are function arguments consumed inside and never stored in EvidenceWindow. `assert_no_pii()` serialises the window to JSON and checks all forbidden tokens and their 4+-char subwords. Tests call it immediately after deidentify().

**TC-30 (at generation)**
`gate.validate(proposal)` is the single choke point. Called before any reviewer sees the proposal. Checks: kind in VALID_PROPOSAL_KINDS, impact in [0.1, 20.0] MW, confidence in [0.0, 1.0], lifetime in [30, 3600] s. Out-of-bounds → state=REJECTED, returns False, never enters pending_proposals().

**Proposal lifecycle (hold questions)**
- Lifetime bounded by `expires_at_sim_time = created_at + clamped(lifetime_s, 30–3600)`. No proposal is PENDING indefinitely.
- Terminal states: ACCEPTED, REJECTED, EXPIRED, SUPERSEDED — once terminal, no further transition permitted (raises ValueError).
- Reviewing event never arrives: `gate.tick(sim_time)` scans PENDING proposals and transitions any where `sim_time >= expires_at_sim_time` to EXPIRED. Driven by sim clock forwarded from AdvisoryPrincipal.tick(), called once per sim tick.

**Advisory throttle**
ADVISE_EVERY_N_TICKS = 12 (60 s at 5 s/tick). EVIDENCE_WINDOW_TICKS = 60 (5 min). Warm-up: needs at least EVIDENCE_WINDOW_TICKS ticks before first advisory call.

**Module placement**
core/deident.py is pure computation (no I/O, no imports from runtime/). Gate/router/principal are runtime/ — they make HTTP calls or are called from the run loop. Plane separation gate covers 10 core/ files, 7 api/ files.

**RunContext access pattern**
Use `ctx.sim_state` (not `ctx.state`) — attribute name. `ctx.sink.append(result)` is async — call with `await`. Manual tick loop: `result = ctx.step()` then `await ctx.sink.append(result)`.
