---
name: websockets package installation
description: uvicorn requires the websockets (or wsproto) library for WebSocket support; it is NOT included by default and must go into .pythonlibs, not the system Nix store.
---

## Rule

Install `websockets` via `pip3 install --target=/home/runner/workspace/.pythonlibs/lib/python3.13/site-packages websockets`.

**Why:** The Nix Python store is read-only — `pip install websockets` and `pip install --break-system-packages websockets` both fail with EPERM. `uv add websockets` (the Replit package manager) also fails with the same EPERM. The correct target is the writable `.pythonlibs` directory, which is already on `sys.path` and where uvicorn itself lives.

**How to apply:** Without this package, uvicorn logs "No supported WebSocket library detected" and returns HTTP 404 for every WS upgrade request. The frontend shows the LIVE badge (run detected via polling) but never receives any tick data — node MW values stay at their static defaults. Install once; the package persists across workflow restarts.

## Demo scenario duration

All 13 seeded demo scenarios use `end_sim_time=300.0 s` (5-minute sims). At MAX speed (`playback_speed=0`), a single run completes in ~1–2 s wall-clock. For a "running" screenshot with visible data, use `playback_speed=10` and start the screenshot 8+ seconds after run start (sim_time ~80 s, past the job-event at t=60 s).

## Run auto-detection in App.tsx

`App.tsx` polls `GET /runs` every 2 s when `runId === null` and sets the run_id automatically. This lets a curl-started run be picked up by the browser without clicking the START button. Once a run is detected, `handleRunStarted` no longer calls `setCurrentPage('overview')` — the opening screen stays visible during the run so flow lines can thicken live.
