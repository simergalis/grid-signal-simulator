# GS-IMPL-JOBQ-001 — Addendum 2: Multi-Instance KubeDemandAgent for Multi-Tenant Jobs Tab
**Replit Agent Implementation Prompt**
**Supersedes:** Addendum 1's Decision C (tenant_id/scheduler_type resolution)
**Traces to:** Functional Spec v2.5 §19.1 (Jobs tab, multi-tenant), §23.8 CL-4 (multi-tenant fairness, open)

---

## Context (read before starting)

Phase 0 discovery (original ticket) and the pre-implementation trace (this addendum's predecessor) established:

- `_PendingAdmission` and `_ActiveJob` have no `tenant_id` or `scheduler_type` — `KubeConfig` is single-tenant, single-scheduler by construction ("swapping Slurm for Kubernetes changes this file and nothing else").
- The only place multi-tenant behavior (three tenants, weighted 40/35/25, each with a scheduler type) currently exists is `gpuGeneratorStore.ts` — the synthetic frontend source being retired.
- Retiring that source without replacing multi-tenant behavior would make the Jobs tab **less** multi-tenant than it is today, directly undercutting the cross-tenant differentiation story this product is built on. That is not acceptable.

**Decision:** Run multiple `KubeDemandAgent` instances — one per tenant — each with a fixed `tenant_id` and `scheduler_type` in its own `KubeConfig`. This is config-level threading, not new stochastic/ranking logic, but it changes how `simulation_core.py` orchestrates demand and admission, which is why this is its own phase with its own stop gate.

---

## Phase A — Discovery: does admission assume a single agent?

Before writing any code, answer these and report back:

1. In `simulation_core.py`, how is `KubeDemandAgent.evaluate_tick()` (or equivalent) currently called — once per tick against a single agent instance? Cite the call site.
2. Does the power-cap admission check (headroom vs. requested draw) operate on one agent's `_reorder_buffer` directly, or is there already an intermediate aggregation step (e.g., a list of pending admissions from "somewhere") that a second agent's buffer could plug into with moderate change?
3. Is `evaluate_tick()`'s signature/internals written in a way that assumes it owns the full tick's admission decision, or does it return a proposal that something else arbitrates? This determines whether multi-agent support means "call it N times and merge" or "restructure the admission arbitration."
4. Confirm: does anything else in the codebase (BESS dispatch, turbine staging, `CurtailmentLadder`) read `_reorder_buffer` or `_active_jobs` directly by reaching into a single `KubeDemandAgent` instance, or does everything already go through the tick broadcast / `TickResult`? This matters because direct reach-ins would need updating at every call site, not just the admission loop.

**Stop and report Phase A findings before proceeding.** If admission logic assumes single-agent ownership at a structural level (not just "called once"), do not restructure it as part of this ticket — report back with a scope estimate and let's decide whether that's this ticket or its own design pass.

---

## Phase B — Implementation (proceed only after Phase A is reviewed and approved)

**Config:**
- Add `tenant_id: str` and `scheduler_type: Literal["SLURM","K8S","RAY"]` to `KubeConfig`.
- Instantiate three `KubeDemandAgent` instances at scenario setup, matching current tenant split (A/K8S ~40%, B/SLURM ~35%, C/RAY ~25%, or whatever the exact current `gpuGeneratorStore.ts` mapping is — confirm exact values from that file before hardcoding, and tag the arrival-rate split itself `PROPOSED_HERE` in the parameter catalogue if it isn't already sourced).

**Admission arbitration:**
- Headroom and turbine/BESS capacity are site-level, not per-tenant. All three agents' pending admissions compete for the same shared headroom each tick. Implement (or extend, per Phase A finding) the admission check to evaluate across all three agents' buffers together, not three independent single-tenant checks.
- Preserve AT-7 determinism: iteration order across agents must be fixed and deterministic (e.g., tenant A→B→C, not dict/set iteration), since admission order can affect which jobs get admitted vs. requeued when headroom is tight.

**Propagate `tenant_id`/`scheduler_type`:**
- Thread through `_PendingAdmission` and `_ActiveJob` from each agent's fixed config values, per Addendum 1 Decision C.

**Broadcast contract:**
- Proceed with Addendum 1's `pending_jobs` / `active_jobs_detail` broadcast additions, now populated across all three agents' combined state.

---

## Do-not list

- Do NOT implement per-tenant fairness logic in the admission arbitration (e.g., "give each tenant a fair share of headroom"). That's CL-4, explicitly open, explicitly out of scope. Admission order/arbitration for this ticket should be the simplest deterministic rule that produces correct combined headroom accounting (e.g., first-come by `observed_at` across all agents) — not a fairness policy.
- Do NOT let any agent's config values drift from a single source of truth for the tenant/scheduler split — if `gpuGeneratorStore.ts` values are being ported over, port them once into the parameter catalogue, don't hardcode them separately in two places.
- Do NOT restructure admission arbitration beyond what's needed to combine three agents' buckets, if Phase A shows deeper restructuring is required — stop and report instead, per Phase A's gate.
- Do NOT skip the AT-7 determinism check on the new multi-agent iteration order.

---

## Acceptance criteria

1. Jobs tab shows three tenants with distinct scheduler types, sourced entirely from the physics engine (no synthetic frontend data).
2. Admission/headroom accounting is correct in aggregate across all three agents — total admitted draw never exceeds actual site headroom, verified against a scenario with tight capacity.
3. AT-7 determinism holds for a fixed-seed multi-agent scenario replay.
4. No fairness logic introduced under this ticket; CL-4 remains explicitly open and untouched in the open-items registry.
5. Phase A findings reported and reviewed before any Phase B code is written.

---

## Stop-and-report gates

- After Phase A (mandatory).
- Mid-Phase B, if admission arbitration turns out to require restructuring beyond "combine three buffers deterministically."
- Before finalizing, if the tenant/scheduler split values in `gpuGeneratorStore.ts` don't cleanly map to three fixed configs (e.g., if weights are dynamic/scenario-configurable rather than fixed).
