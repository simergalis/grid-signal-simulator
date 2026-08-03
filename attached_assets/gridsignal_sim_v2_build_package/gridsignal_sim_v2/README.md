# GridSignal Simulator — v2.2

A full-stack data-centre energy-management simulator. An operator starts a seeded scenario, observes live physics (solar PV, BESS, gas turbines, cooling), and reviews recommendations from an LLM-backed advisory layer. The physics engine is fully deterministic and runs without any LLM keys.

## What's in this archive

```
gridsignal_sim_v2/
├── README.md                     ← this file
├── .gitignore
├── gridsignal_sim/               ← Python backend (FastAPI + asyncio)
│   ├── api/                        REST + WebSocket endpoints; auth (OTP/JWT)
│   ├── core/                       deterministic simulation engine (no I/O)
│   ├── runtime/                    asyncio concurrency + run management
│   ├── renewable/                  SolarSim — 1 Hz per-bank solar console
│   ├── advisory/                   LLM-backed advisory agents
│   ├── tests/                      763 pytest tests
│   ├── audit_tests/                13 audit-finding regression tests
│   └── scripts/                    load_test.py, determinism_gate.py, etc.
├── frontend/                     ← React 18 + Vite + TypeScript dashboard
│   ├── src/                        TypeScript source
│   └── dist/                       pre-built bundle (served by the backend)
├── audit_tests/                  ← audit-finding executable tests (12 closed)
├── docs/                         ← design documents
│   └── GridSignal_Replit_Build_Plan_v2.2.md  ← BUILD PLAN (see gridsignal_sim/docs/ for full set)
└── reference/                    ← reference implementations (do not drop in directly)
```

> The authoritative docs live in `gridsignal_sim/docs/`.  This directory contains the top-level build plan only; `gridsignal_sim/docs/` has the full design review, remediation pack, skeleton audit, and acceptance matrix.

## Quick start

```bash
cd gridsignal_sim

# Required env vars
export JWT_SECRET=<generate-a-strong-random-secret>
export INITIAL_ADMIN_EMAIL=admin@example.com
export INITIAL_ADMIN_NAME="Admin"

# Optional — physics fallback is used when absent
export MISTRAL_API_KEY=...        # solar forecast + geocoding
export ANTHROPIC_API_KEY=...      # advisory agents

# Install dependencies
pip install \
  fastapi uvicorn websockets \
  sqlalchemy aiosqlite "bcrypt>=4.0" "passlib[bcrypt]" "python-jose[cryptography]" \
  httpx pydantic mistralai anthropic python-multipart

# Start the server (also installs missing deps automatically)
PORT=8080 bash scripts/start_prod.sh
```

Open `http://localhost:8080`.  Log in with the admin OTP sent to `INITIAL_ADMIN_EMAIL`.

> **JWT_SECRET is required.** `api/auth_utils.py` raises at import time without it, which causes five test modules to fail at collection. Set it before running tests or starting the server.

## Verify the baseline

```bash
cd gridsignal_sim

PYTHONPATH=. pytest tests/ -q                        # 763 passed
PYTHONPATH=. pytest ../audit_tests/ -q               # 13 passed (all 12 audit findings closed)
PYTHONPATH=. python scripts/check_plane_separation.py    # PASS — 19 core / 16 api files clean
PYTHONPATH=. python scripts/determinism_gate.py          # PASS — 9/9 scenarios, hash A == hash B
```

## Rebuild the frontend

`frontend/dist/` is committed as a pre-built artifact. To rebuild from source:

```bash
cd frontend
npm ci
npm test         # vitest unit tests (4 suites)
npm run build    # tsc typecheck + vite build → dist/
```

## Architecture in one paragraph

`core/` is a pure-Python synchronous simulation engine — no I/O, no asyncio, fully deterministic. `runtime/` is the asyncio concurrency layer: it drives `core/` via `RunContext.step()` once per tick, manages WebSocket broadcast, and persists results via SQLAlchemy + SQLite. `api/` is the HTTP/WS surface built on FastAPI; it reads `app.state` for shared singletons (RunManager, SolarSim, ScenarioStore) and never touches `core/` directly. The plane-separation rule (`core/ → runtime/` imports forbidden, `api/ → core/` imports forbidden) is enforced by `scripts/check_plane_separation.py` and CI Gate 2.

## CI gates

Eight gates run on push to `main`, `develop`, or `feature/**`:

| Gate | What it checks |
|------|----------------|
| 1 | Full pytest suite (763 TCs) |
| 2 | Plane separation — api/ → core/ import wall |
| 3 | TC-29 — no-PII egress guarantee |
| 4 | TC-68 — SCADA zero-protection-commands boundary |
| 5 | Verdict acceptance — demo-20mw PASS, demo-alert FAIL |
| 6 | Load / NFR — 5 concurrent runs, tick latency < 1 s (triggers on core/runtime/advisory changes) |
| 7 | Determinism — 9 seeded scenarios × 2 concurrent runs, hash A == hash B + distinct-hash check |
| 8 | Shipped-scenario smoke — column-3 acceptance tests |
| Frontend | tsc typecheck + vitest + vite build |

## Known design notes

- **p_expected_mw / banks_reporting** are `None` in the tick payload on the run path. The run engine has no independent expectation model; a copy of `p_renewable_mw` would be a tautology that makes fault detection structurally unreachable. Use `GET /api/solar/state` → `power.p_expected_mw` / `power.banks_reporting` for the honest per-bank figures (computed by the 1 Hz SolarSim).
- **Site location** is persisted to `gridsignal_site.json` on `PUT /api/location` and restored on startup, so a server restart under an open browser tab no longer silently reverts to San Diego physics.
- **Determinism gate** now includes a distinct-hash assertion: all 9 seeded scenarios must produce different dispatch traces. Identical hashes indicate a scenario's feature branch is not reaching dispatch.
