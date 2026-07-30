---
name: Step 6 FastAPI wiring
description: Structure of the api/ package, asyncio mode fix, enforcement points for the single RunManager invariant, and TC numbering for Step 6.
---

**Package layout:**
- `api/__init__.py` — imports from runtime/ only; never core/ directly
- `api/app.py` — `create_app()` factory + module-level `app` singleton for uvicorn
- `api/schemas.py` — Pydantic wire models (no core/ imports)
- `api/routes/runs.py` — POST/GET/DELETE /runs; dependency `_run_manager(request)` pulls from app.state
- `api/routes/ws.py` — WS /ws/{run_id}; hub pulled from `websocket.app.state.ws_hub`

**Lifespan pattern:**
```python
@asynccontextmanager
async def _lifespan(application: FastAPI):
    hub = WebSocketHub()
    manager = RunManager(hub)
    application.state.ws_hub = hub
    application.state.run_manager = manager
    yield
```
ONE RunManager + ONE WebSocketHub created here, never in request handlers.
Step 12 enforcement: agents interact through the API and thus share the same RunManager (same concurrency budget + audit trail). Any agent that bypasses the API and constructs its own RunManager would be invisible to rate limiting and audit.

**Invariants enforced:**
- api/ never imports from core/ directly — chain is api/ → runtime/ → core/
- api/ never constructs SimClock or calls evaluate_tick() — these stay in RunContext.step()
- Static gate (scripts/check_plane_separation.py) only scans core/; api/ pureness is by design, not by gate

**asyncio mode fix:**
- pytest.ini (asyncio_mode=auto) DELETED
- gridsignal_sim/pyproject.toml CREATED with asyncio_mode="strict"
- Root cause: workspace pyproject.toml (no asyncio setting → defaults to STRICT) won over pytest.ini when combined invocation widened rootdir
- All 6 async tests in test_persistence.py got @pytest.mark.asyncio
- test_concurrency.py already had markers

**Tests (TC-36 … TC-43) in tests/test_api.py:**
All sync, using TestClient(create_app()) — each test gets a fresh lifespan. TestClient handles lifespan correctly; httpx.AsyncClient with ASGITransport does NOT send lifespan events (app.state would be unpopulated).
- TC-36: POST /runs → 201 + run_id
- TC-37: run appears in GET /runs
- TC-38: GET /runs/{run_id} → active=True while in flight
- TC-39: GET /runs/missing → 404
- TC-40: DELETE /runs/{run_id} → 204, removed from list
- TC-41: DELETE /runs/missing → 404
- TC-42: POST /runs with empty body → 422 (both job_id and node_count missing)
- TC-43: WebSocket /ws/{run_id} receives a tick payload with required fields; wall_stamp_utc must NOT appear in broadcast

**Test count after Step 6:** 62 unit tests (tests/), 13 audit tests (audit_tests/)

**Package installation:**
FastAPI 0.141.1, httpx 0.28.1, uvicorn 0.52.0 installed via:
`uv pip install --target /home/runner/workspace/.pythonlibs/lib/python3.13/site-packages fastapi httpx uvicorn`
(standard pip and the package skill's uv add both fail due to NixOS immutable store; --target flag works)
