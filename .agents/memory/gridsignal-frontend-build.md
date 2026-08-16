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
