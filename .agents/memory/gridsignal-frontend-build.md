---
name: gridsignal-frontend-build
description: Frontend build requirement and GpuNodeGeneratorModal variable naming traps.
---

## Frontend build requirement

The gridsignal web artifact runs `start_prod.sh`, which serves a **pre-compiled** static bundle from `frontend/dist/`. Source edits to `frontend/src/` are invisible until you:

1. Run `bash scripts/build_prod.sh` from `gridsignal_sim/`
2. Restart the `artifacts/gridsignal: web` workflow

**Why:** `start_prod.sh` only starts uvicorn — it does not rebuild. `build_prod.sh` runs `tsc --noEmit && vite build` and outputs to `frontend/dist/`.

**How to apply:** After any frontend source change that must be user-visible, always rebuild before declaring done. The build takes ~6 s.

---

## Workflow ownership

The `artifacts/gridsignal: web` workflow owns both the Python simulator API on port 22126 and the compiled frontend. The separately registered `artifacts/api-server: GridSignal Simulator` workflow is a Node service and does not reload Python route changes.

**Why:** Restarting only the Node API workflow leaves the simulator's uvicorn process unchanged, so Python tests can pass while live `/api/*` behavior still comes from stale code.

**How to apply:** After changes under `gridsignal_sim/api/`, restart `artifacts/gridsignal: web` and verify the endpoint on port 22126.

---

## GpuNodeGeneratorModal — naming traps

Two sets of lookup constants exist with similar names. Using the wrong one causes silent wrong data or TypeScript errors:

| Name | Scope | Keys | Purpose |
|---|---|---|---|
| `TENANT_COLOUR` | Module-level | `A`, `B`, `C` | Jobs tab tenant colour badges |
| `SCHEDULER_BADGE` | Module-level | `A`, `B`, `C` | Jobs tab scheduler label badges |
| `TENANT_COLOUR_BY_ID` | Component-level (inside function body) | `A`, `B`, `C` | Queue tab / kube rows |
| `SCHEDULER_BADGE_BY_TYPE` | Component-level | `SLURM`, `K8S`, `RAY` | Queue tab scheduler badges |

The Queue tab must use the **component-level** versions (`TENANT_COLOUR_BY_ID`, `SCHEDULER_BADGE_BY_TYPE`) — the scheduler keys differ (`SLURM`/`K8S`/`RAY` vs `A`/`B`/`C`).

Live-stats header variables in the component are `allLiveJobs`, `liveTotalNodes`, `liveTotalMW` — not `allJobs`/`totalGPUs`/`totalMW` (those names no longer exist).

**Why:** The component was refactored to use physics-engine broadcast data (JOBQ-001 Phase B) and variables were renamed, but the header stat section retained the old names until fixed in JOBQ-001 Addendum 4.

---

## Plant-diagram tile click-through has two independent gates

A plant-diagram node only opens a modal when clicked if **both** are true:

1. `NODE_MODAL_MAP` (in `OpeningScreen.tsx`) has an entry for the node's id.
2. The node's `NodeDef.clickable` flag (in `plantLayout.ts`) is `true` — `PlantNode.tsx` computes `canClick = def.clickable && !def.passive` and only attaches `onClick` when that's true.

**Why:** These two gates were added independently and neither one alone is sufficient. A node can have a correct `NODE_MODAL_MAP` entry, a working `PANEL_CONFIGS` panel, and correct `SubsystemModal` chrome aliasing, and still silently do nothing on click if `clickable` is `false` on its `NodeDef` — the click handler is never even attached to the DOM element, so there's no console error or other signal.

**How to apply:** When a plant-diagram tile "does nothing" on click, check both gates, not just the modal-routing map. Don't assume a fix is complete after confirming `NODE_MODAL_MAP` + `PANEL_CONFIGS` + chrome alias are correct — also grep the node's `NodeDef` literal in `plantLayout.ts` for `clickable: true`.
