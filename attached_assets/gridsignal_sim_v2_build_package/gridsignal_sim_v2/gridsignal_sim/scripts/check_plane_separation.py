#!/usr/bin/env python
"""
Static purity gate — Step 4 / Step 6 / Design Spec §4.3.

Two independent scan targets, each with its own forbidden list:

TARGET 1 — core/
  core/ must not import from runtime.* or from any I/O / async-transport
  package.  The control plane is a synchronous, deterministic numeric
  pipeline; pulling in asyncio, fastapi, or httpx would make it
  non-reproducible and untestable in isolation.

TARGET 2 — api/
  api/ must not import directly from core.*.  The permitted call chain is
  api/ → runtime/ → core/.  Bypassing runtime/ would let request handlers
  construct SimClock objects, call evaluate_tick(), or read the wall clock
  — all of which are RunContext.step()'s sole responsibilities (Step 5,
  Design Spec §4.2).  api/ legitimately imports FastAPI/Starlette/asyncio,
  so it has its own forbidden list rather than sharing core/'s.

Both targets are scanned by the same AST walker so late imports inside
function bodies are caught as reliably as module-level ones.

Run standalone (build-breaking):
    PYTHONPATH=. python scripts/check_plane_separation.py

Also wired into the test suite via tests/test_plane_separation.py so it
runs automatically with `pytest`.
"""

from __future__ import annotations

import ast
import pathlib
import sys

CORE_DIR = pathlib.Path(__file__).parent.parent / "core"
API_DIR  = pathlib.Path(__file__).parent.parent / "api"

# ---- core/ forbidden list ---------------------------------------------------
# Any top-level package name that must never appear in a core/ import.
FORBIDDEN_TOP_LEVEL: frozenset[str] = frozenset({
    "runtime",           # control-plane must not depend on the concurrency layer
    # I/O, async transports, network, web frameworks — forbidden in the
    # synchronous deterministic core (Design Spec §4.3).
    "asyncio", "anyio", "trio", "concurrent",
    "httpx", "aiohttp", "requests", "urllib3",
    "websockets", "uvicorn", "fastapi", "starlette",
    "flask", "django", "tornado",
    "boto3", "botocore", "aiobotocore",
    "aiofiles", "httpcore",
})

# ---- api/ forbidden list ----------------------------------------------------
# api/ must not reach into core/ directly.  The chain is api/ → runtime/ → core/.
# api/ legitimately imports FastAPI, Starlette, asyncio, etc., so the list is
# intentionally narrower than FORBIDDEN_TOP_LEVEL.
FORBIDDEN_API_TOP_LEVEL: frozenset[str] = frozenset({
    "core",   # blocks core.*, core.sim_clock, core.simulation_core, core._plane_guard, …
})


# ---------------------------------------------------------------------------
# Scanner (shared by both targets)
# ---------------------------------------------------------------------------

def scan_source(
    filename: str,
    source: str,
    forbidden_top_level: frozenset[str] = FORBIDDEN_TOP_LEVEL,
) -> list[str]:
    """Return a list of violation strings found in *source*.

    Uses ast.walk() to cover imports at every nesting level — a module-
    level-only check would miss late imports inside function bodies.

    The default *forbidden_top_level* is the core/ list; pass
    FORBIDDEN_API_TOP_LEVEL when scanning api/ files.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [f"{filename}: SyntaxError — {exc}"]

    target = "core/" if forbidden_top_level is FORBIDDEN_TOP_LEVEL else "api/"
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in forbidden_top_level:
                    violations.append(
                        f"{filename}:{node.lineno}: "
                        f"import {alias.name!r} — forbidden in {target} "
                        f"(top-level package {top!r} is in forbidden list)"
                    )
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod in forbidden_top_level:
                violations.append(
                    f"{filename}:{node.lineno}: "
                    f"from {node.module} import ... — forbidden in {target} "
                    f"(top-level package {mod!r} is in forbidden list)"
                )
    return violations


# ---------------------------------------------------------------------------
# check_all — scan core/*.py  (unchanged from Step 4)
# ---------------------------------------------------------------------------

def check_all(core_dir: pathlib.Path = CORE_DIR) -> list[str]:
    """Scan all *.py files directly under core_dir and return all violations."""
    all_violations: list[str] = []
    for path in sorted(core_dir.glob("*.py")):
        all_violations.extend(
            scan_source(path.name, path.read_text(), FORBIDDEN_TOP_LEVEL)
        )
    return all_violations


# ---------------------------------------------------------------------------
# check_api — scan api/**/*.py  (Step 6 addition)
# ---------------------------------------------------------------------------

def check_api(api_dir: pathlib.Path = API_DIR) -> list[str]:
    """Scan all *.py files recursively under api_dir and return all violations.

    api/ has subdirectories (routes/, …) so rglob is used instead of glob.
    Paths are reported relative to api_dir's parent so violations are readable
    alongside the core/ violations in combined output.
    """
    all_violations: list[str] = []
    for path in sorted(api_dir.rglob("*.py")):
        rel = str(path.relative_to(api_dir.parent))   # e.g. "api/routes/runs.py"
        all_violations.extend(
            scan_source(rel, path.read_text(), FORBIDDEN_API_TOP_LEVEL)
        )
    return all_violations


# ---------------------------------------------------------------------------
# __main__ — standalone build-breaking invocation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    core_violations = check_all()
    api_violations  = check_api()

    any_violation = bool(core_violations or api_violations)

    if core_violations:
        print("FAIL — core/ plane-separation violations:", file=sys.stderr)
        for v in core_violations:
            print(f"  {v}", file=sys.stderr)

    if api_violations:
        print("FAIL — api/ plane-separation violations:", file=sys.stderr)
        for v in api_violations:
            print(f"  {v}", file=sys.stderr)

    if any_violation:
        sys.exit(1)

    core_count = len(list(CORE_DIR.glob("*.py")))
    api_count  = len(list(API_DIR.rglob("*.py")))
    print(f"OK — {core_count} core/ files and {api_count} api/ files are clean.")
    sys.exit(0)
