#!/usr/bin/env python
"""
Static control-plane purity check — Step 4 / Design Spec §4.3.

Scans every core/*.py with the stdlib ast module and exits non-zero if
any core module imports from runtime.* or from a forbidden I/O /
async-transport package.

Covers ALL import nodes regardless of nesting depth (module-level AND
function-level late imports) — a naive line-grep would miss the latter.

Run standalone (build-breaking):
    PYTHONPATH=. python scripts/check_plane_separation.py

Also wired into the test suite via tests/test_plane_separation.py so it
runs automatically with `pytest` (already CI-breaking for any violation).
"""

from __future__ import annotations

import ast
import pathlib
import sys

CORE_DIR = pathlib.Path(__file__).parent.parent / "core"

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


def scan_source(filename: str, source: str) -> list[str]:
    """Return a list of violation strings found in `source`.

    Uses ast.walk() to cover imports at every nesting level — a module-
    level-only check would miss late imports inside function bodies.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [f"{filename}: SyntaxError — {exc}"]

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in FORBIDDEN_TOP_LEVEL:
                    violations.append(
                        f"{filename}:{node.lineno}: "
                        f"import {alias.name!r} — forbidden in core/ "
                        f"(top-level package {top!r} is in FORBIDDEN_TOP_LEVEL)"
                    )
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod in FORBIDDEN_TOP_LEVEL:
                violations.append(
                    f"{filename}:{node.lineno}: "
                    f"from {node.module} import ... — forbidden in core/ "
                    f"(top-level package {mod!r} is in FORBIDDEN_TOP_LEVEL)"
                )
    return violations


def check_all(core_dir: pathlib.Path = CORE_DIR) -> list[str]:
    """Scan all *.py files in core_dir and return all violations."""
    all_violations: list[str] = []
    for path in sorted(core_dir.glob("*.py")):
        all_violations.extend(scan_source(path.name, path.read_text()))
    return all_violations


if __name__ == "__main__":
    violations = check_all()
    if violations:
        print("FAIL — core/ plane-separation violations:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        sys.exit(1)
    print(f"OK — {len(list(CORE_DIR.glob('*.py')))} core/ files are clean.")
    sys.exit(0)
