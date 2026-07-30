---
name: Step 4 control-plane purity gate
description: Two-layer guard (static AST scan + ContextVar sentinel) that enforces core/ never imports runtime/ or I/O packages, and evaluate_tick() is only called from the runtime harness.
---

**Layer 1 — Static (AST scan, scripts/check_plane_separation.py):**
- `scan_source(filename, source)` walks ALL ast nodes (not just module-level) — catches late imports inside function bodies too.
- `FORBIDDEN_TOP_LEVEL`: runtime, asyncio, httpx, aiohttp, requests, websockets, fastapi, starlette, uvicorn, flask, django, tornado, boto3, botocore, anyio, trio, concurrent, urllib3, aiofiles, httpcore.
- Wired into CI via tests/test_plane_separation.py (pytest returns non-zero on failure).
- Standalone: `PYTHONPATH=. python scripts/check_plane_separation.py` (exits 1 on violation).

**Layer 2 — Runtime (ContextVar sentinel):**
- `core/_plane_guard.py` defines `_EVALUATE_TICK_PERMITTED: ContextVar[bool]` (default False).
- `evaluate_tick()` checks it at entry and raises `RuntimeError("evaluate_tick.*runtime guard")` if absent.
- SET BY THE CALLER: `runtime/run_manager.py:RunContext.step()` wraps each call in `set(True)/reset()`.
- evaluate_tick() itself must NEVER set it — self-signing defeats the guard.
- Sentinel is ContextVar-scoped: concurrent asyncio tasks cannot cross-contaminate each other's state.

**Test helper for direct evaluate_tick() calls:**
- `_plane_guard_active()` context manager: defined in tests/test_formulas.py AND tests/test_plane_separation.py.
- Use for any test that calls evaluate_tick() directly (not via RunContext.step()).
- The three pre-existing direct callers (test_d7, test_d9, test_d10) now wrap their loops with this.

**Both guards demonstrated failing (test_plane_separation.py):**
- Static: inject `import httpx` at module level → violation caught; inject `import asyncio` inside a function body → still caught (proving ast.walk covers all nesting).
- Runtime: call evaluate_tick() with sentinel explicitly set False → RuntimeError; call via RunContext.step() → passes; bare call after step() → fails (sentinel was reset).

**Why:** Design Spec §4.3 requires core/ to be synchronous, pure, side-effect-free. Any I/O import or runtime/ dependency makes evaluate_tick() non-deterministic or non-portable. The static layer catches accidents at build time; the runtime layer catches unauthorized callers at execution time — two orthogonal failure modes.
