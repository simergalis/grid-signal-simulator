# GS-IMPL-JOBQ-001 — Addendum: Phase 0 Decisions & Revised Phase 1 Scope

Resolves the two stop gates raised in the Phase 0 discovery report. Read that report first — this addendum assumes its findings (1–4) as given.

---

## Decisions

**A. Duplicate source (Finding 3) — resolved: consolidate, don't dual-label.**
`gpuGeneratorStore.ts` is retired as the data source for the Jobs tab. It may continue to exist purely as a scenario-seed generator feeding the physics engine (`KubeDemandAgent`), if that's its other role — but nothing in the Jobs tab UI reads from it directly going forward. The Jobs tab reads exclusively from the physics engine broadcast. This is a consolidation onto the single authoritative source per the spec's no-dual-implementation rule, not a new parallel system.

**B. Per-job curtailment fields (Finding 2) — resolved: defer, do not build a surrogate.**
`curtailment_eligible` and `ladder_position` are **out of scope** for this ticket. Do not derive a surrogate value from tier MW-capacity thresholds. Omit these columns from the Jobs tab entirely — no placeholder, no dash, no "coming soon." Log a new open item (or extend CL-3/CL-4) for per-job curtailment ranking as its own design/implementation effort under §23.

**C. Missing `tenant_id` / `scheduler_type` (Finding 1) — resolved: in scope, minimal backend addition.**
Add `tenant_id: str` and `scheduler_type: Literal["SLURM","K8S","RAY"]` to `_PendingAdmission` in `kube_demand.py`. Apply the same addition to whatever record backs active/running jobs if those fields aren't already present there. This is exposing context already known at record-creation time, not new logic — confirm with a quick check of where `_PendingAdmission` and its active-job counterpart are instantiated, and thread the values through from there.

---

## Revised Phase 1 scope (supersedes original Phase 1 §1–§4)

Given decision A, the broadcast needs per-job detail for **both** active and pending jobs, not just the power-cap queue — the original ticket only anticipated the queue side.

**New/changed dataclasses (backend, `kube_demand.py`):**
- `_PendingAdmission`: add `tenant_id`, `scheduler_type`.
- Active-job record (name TBD per Finding 1 follow-up): add `tenant_id`, `scheduler_type` if not already present.

**Broadcast contract (`run_manager.py` / `KubeMetrics` and payload_guard, both sides of `types.ts`):**
- Add `pending_jobs: List[QueuedJobSummary]` — fields: `event_id`, `tenant_id`, `scheduler_type`, `node_count`, `hardware_profile_id`, `observed_at`, `duration_s`. (`wait_seconds` stays derived at render time, not stored, per original ticket.)
- Add `active_jobs_detail: List[ActiveJobSummary]` — equivalent fields for running jobs, replacing whatever `gpuGeneratorStore.ts` was synthesizing for the Jobs tab today (name, GPU/node count, estimated draw, status).
- `queued_jobs` / `queued_nodes` (existing count-only fields) stay as-is for the Compute tile summary — no need to remove, the new arrays are additive.
- Every new field: matching typed field in `TickPayload`/`KubeMetrics`, enforced by the existing `payload_guard` test. No untyped passthrough.
- `est_draw_mw` per job: derive from `node_count × hardware_profile_id` lookup against the Hardware Power Profile Library (§5) at broadcast time — do not store a redundant computed value.

**Frontend:**
- Jobs tab: re-source from `pending_jobs` + `active_jobs_detail`. Remove `curtailment`/`ladder` columns from scope (per decision B).
- New Queued view: as originally specified in Phase 3, sourced from `pending_jobs`.
- Delete (or clearly repurpose as scenario-authoring-only, not display) the `tenantA`/`tenantB`/`tenantC` synthetic arrays in `gpuGeneratorStore.ts` insofar as the Jobs tab used them for display.

---

## Do-not list (additions to original)

- Do NOT add `curtailment_eligible` / `ladder_position` in any form, including placeholders.
- Do NOT leave `gpuGeneratorStore.ts` wired into the Jobs tab display path "just in case" — full cutover, not a fallback.
- Do NOT infer `tenant_id`/`scheduler_type` from naming conventions or heuristics if they're not already threaded through at creation time — trace them properly or stop and report.

---

## Next stop-and-report gate

After implementing the `_PendingAdmission` / active-job-record field additions, report back the actual field names and instantiation sites found for the active-job record (Finding 1 flagged this as needing its own lookup) before touching the broadcast contract, in case the active-job side has its own structural surprise symmetric to Finding 3.
