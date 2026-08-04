---
name: Frontend rebuild required after source changes
description: The Replit workflow runs start_prod.sh which serves a pre-built dist/. Source changes are invisible until npm run build is run.
---

## Rule

Any edit to files under `gridsignal_sim_v2/frontend/src/` (or `frontend/public/`) is **not visible to the running app** until the frontend is rebuilt. The workflow (`start_prod.sh`) serves the static `frontend/dist/` compiled output — it does not hot-reload or watch source files.

## Required step after every frontend source change

```bash
cd /home/runner/workspace/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend
npm run build   # runs: tsc --noEmit && vite build  (~7 s)
```

Then restart the `artifacts/gridsignal: web` workflow.

**Why:** `start_prod.sh` is a single-process production entrypoint; `build_prod.sh` is the separate build step (run at deploy time). In the Replit dev environment there is no separate dev-server workflow, so the build must be triggered manually after code edits.

## How to apply

- After any edit to `frontend/src/**` or `frontend/public/**`, always run the build command above before restarting the workflow.
- TypeScript errors surface here too (`tsc --noEmit` runs first), so a clean build = no TS errors.
- The build takes ~7 s; running `tsc --noEmit` first is redundant (it's included in `npm run build`) but acceptable as an early-fail check.
