# GS-IMPL-JOBQ-001 — Addendum 3: Phase B Implementation (Go-Ahead)
**Replit Agent Implementation Prompt**
**Authorizes:** Phase B per Addendum 2, using the exact plan from the Phase A report
**Prerequisite reading:** Original ticket, Addendum 1, Addendum 2, and the Phase A discovery report — all findings and decisions there stand.

---

## Phase A verdict (confirmed, proceed)

No structural restructuring required. The admission arbitration loop stays as-is; multi-agent support is achieved by threading a running admitted-node count between three serial `tick()` calls in fixed order. Proceed with the five-step plan from the Phase A report, detailed below with the do-not constraints from prior addenda still in force.

---

## Phase B implementation steps

**1. `SimulationState`**
- Change `kube_agent: KubeDemandAgent | None` → `kube_agents: list[KubeDemandAgent]`.
- Add a `kube_agent` property returning `kube_agents[0]` for backward compatibility with the four existing post-call read sites (`simulation_core.py:552, 579, 583, 1622–1623`) — do not rewrite those four sites in this step; let the property absorb the change.
- Instantiate three `KubeDemandAgent`s at scenario setup, each with its own `KubeConfig` carrying fixed `tenant_id` and `scheduler_type` (per Addendum 1 Decision C / Addendum 2). Confirm exact tenant split values (currently ~40/35/25, A/B/C) against `gpuGeneratorStore.ts` before hardcoding — port the split into the parameter catalogue once, don't duplicate it.

**2. `KubeDemandAgent.tick()` signature**
- Add `already_admitted_nodes: int = 0` parameter.
- Capacity check at `kube_demand.py:423–427` becomes:
  ```python
  current_nodes = (
      sum(j.node_count for j in self._active_jobs)
      + sum(j.node_count for j in newly_admitted)
      + already_admitted_nodes
  )
  if current_nodes + pa.node_count > FLEET_MAX_NODES:
      ...
  ```
- `FLEET_MAX_NODES` replaces the per-agent `self.config.max_nodes` in this check specifically — source it from a new fleet-level config (see step 4), not from any single agent's `KubeConfig.max_nodes`.
- Default `already_admitted_nodes=0` preserves single-agent callers/tests without modification.

**3. `simulation_core.py` call loop**
- Replace the single `tick()` call at line 521 with a fixed-order loop: A → B → C (deterministic — do not iterate a dict/set).
- Accumulate `running_total` across calls; pass it as `already_admitted_nodes` to each subsequent agent.
- Merge returned `KubeMetrics` across the three calls: sum count-type fields (`active_jobs`, `admitted_nodes`, `arrivals_this_tick`, `requeued_this_tick`, `queued_jobs`, `queued_nodes`); OR the `power_cap_active` boolean across agents (cap is active if any agent reports it, since headroom is shared and binding for all).
- Concatenate `pending_jobs` / `active_jobs_detail` (the new per-job arrays from Addendum 1) across all three agents into the single lists the broadcast contract expects — this is where `tenant_id`/`scheduler_type` per job actually reach the frontend.

**4. Fleet-level `max_nodes`/`min_nodes`**
- Add a fleet-level config value (not per-agent) for the ramp-patch and utilization-denominator reads at lines 579/583. Sum of the three agents' individual `max_nodes`/`min_nodes` is the straightforward default — confirm this matches intended site capacity semantics before hardcoding the sum; if the three tenants are meant to share one physical ceiling rather than have three additive ones, that's a different fleet config, not a sum. Tag whichever is chosen `PROPOSED_HERE` if no measured basis exists yet.

**5. `step_phase`/`step_kind`**
- Use agent A (primary) for these fields for now, per the Phase A report's recommendation, since the step scheduler is fleet-level. Leave a code comment noting this is a known simplification: if per-tenant step phases ever matter (e.g., for CL-4 fairness work), this will need revisiting. Do not build per-tenant step-phase logic now — out of scope.

---

## Do-not list (cumulative — still in force from prior addenda)

- Do NOT implement per-tenant fairness in admission ordering (CL-4 stays open). Fixed A→B→C order is a determinism requirement, not a fairness policy — do not present it as one anywhere in code comments or UI.
- Do NOT add `curtailment_eligible`/`ladder_position` fields (Addendum 1 Decision B stands).
- Do NOT duplicate the tenant/scheduler split values — one source in the parameter catalogue.
- Do NOT rewrite the four existing single-agent read sites beyond what the `kube_agent` property absorbs, unless the fleet-config work in step 4 requires it.
- Do NOT introduce non-deterministic iteration anywhere in the multi-agent loop (AT-7).

---

## Acceptance criteria

1. Three `KubeDemandAgent` instances run per tick, fixed order, sharing one `KubeGridState`.
2. Combined capacity accounting is correct: no scenario admits more nodes than `FLEET_MAX_NODES` allows, verified against a tight-capacity test scenario.
3. Broadcast `pending_jobs`/`active_jobs_detail` contain jobs from all three tenants with correct `tenant_id`/`scheduler_type` stamped.
4. Jobs tab renders three tenants with distinct scheduler badges, sourced entirely from the physics engine — `gpuGeneratorStore.ts` no longer feeds the Jobs tab display.
5. AT-7 determinism: identical output across repeated runs of a fixed-seed multi-agent scenario.
6. `payload_guard` test updated and passing for the new broadcast fields.
7. No fairness logic introduced; CL-4 open-item entry unchanged.

---

## Stop-and-report gate

- If the fleet `max_nodes` question in step 4 (sum of three vs. one shared physical ceiling) isn't resolvable from existing site-capacity assumptions elsewhere in the codebase, stop and report rather than guessing — this affects real admission behavior, not just display.
- After implementation, before marking the ticket closed: report final `payload_guard` diff and confirm no other call site outside `kube_demand.py`/`simulation_core.py` referenced the old scalar `kube_agent` field in a way the compatibility property doesn't cover.
