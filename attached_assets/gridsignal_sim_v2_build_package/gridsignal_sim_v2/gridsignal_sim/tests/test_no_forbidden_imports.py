"""test_no_forbidden_imports.py — Structural import boundary enforcement.

GS-IMPL-PSP-002 §9 / §6.4 / §5 / Phase 1.

TC-C11: core/ has zero dependency on runtime/ — static import check passes.
TC-C12: runtime/ has zero dependency on:
          - southbound protocol clients (Modbus, DNP3, OPC UA, IEC 61850)
          - LLM clients (mistralai, openai, anthropic, etc.) at runtime
          - RNG (random) for determinism
TC-C13-structural: PMSTestDouble is in runtime/, not core/
                   (runtime reachability from core/ is caught by TC-C11).

Why static import scanning?
----------------------------
An import that is conditional (gated by an env flag or a runtime check) still
violates the boundary — the code path exists even if it is normally unreachable.
This test catches any import statement, conditional or not.

scripts/ rules (§3.5 / §5)
----------------------------
- scripts/ MAY import mistralai (scenario_author.py's offline Mistral call).
- scripts/ MUST NOT be imported by core/ or runtime/ (TC-C11 / §6.2).
- scripts/ is NOT checked for LLM imports here (they are expected and correct).

What counts as a "runtime" LLM import?
--------------------------------------
Any import of a client library that would cause a live API call at tick time.
The test looks for top-level module names used by the major providers:
  mistralai, openai, anthropic, google.generativeai, cohere, replicate, together
Within runtime/ only.  scripts/ is exempt.

Southbound protocol clients (banned in ALL directories including scripts/)
--------------------------------------------------------------------------
  pymodbus, dnp3, dnp3_python, opendnp3, opcua, asyncua, free_opc_ua,
  iec61850, libiec61850, pydnp3
"""
from __future__ import annotations

import ast
import pathlib
import sys
from typing import Dict, List, NamedTuple, Set, Tuple


# ── Paths ──────────────────────────────────────────────────────────────────────

_BACKEND_ROOT = pathlib.Path(__file__).parent.parent
_CORE_DIR     = _BACKEND_ROOT / "core"
_RUNTIME_DIR  = _BACKEND_ROOT / "runtime"
_SCRIPTS_DIR  = _BACKEND_ROOT / "scripts"


# ── Forbidden import sets ──────────────────────────────────────────────────────

# Top-level module name prefixes for southbound protocol clients.
# Banned in ALL directories.
_SOUTHBOUND_MODULES: frozenset[str] = frozenset({
    "pymodbus",
    "dnp3",
    "dnp3_python",
    "opendnp3",
    "opcua",
    "asyncua",
    "free_opc_ua",
    "iec61850",
    "libiec61850",
    "pydnp3",
})

# LLM client modules banned in runtime/ (not banned in scripts/).
_LLM_MODULES_RUNTIME_BANNED: frozenset[str] = frozenset({
    "mistralai",
    "openai",
    "anthropic",
    "google",         # google.generativeai
    "cohere",
    "replicate",
    "together",
    "litellm",
})

# RNG module banned in the PSP-002 subsystem files within runtime/.
# The ban is narrow by design: pre-existing simulation generators
# (cluster_gen, stressor_gen, param_sampler, stressor_gen, telemetry_corruption,
# run_manager) legitimately use random with seeds for scenario reproducibility.
# The determinism requirement (INV-7 / TC-C14) applies specifically to
# PMSTestDouble — the PMS decision loop must replay identically given the same
# OperatorResponseProfile.  Banning random across all of runtime/ would break
# the simulation infrastructure.
_RNG_MODULES_RUNTIME_BANNED: frozenset[str] = frozenset({
    "random",
})

# Files in runtime/ that are pre-existing simulation generators and are
# legitimately exempt from the RNG ban.  Each exemption must document why.
_RNG_EXEMPTED_RUNTIME_FILES: dict[str, str] = {
    "cluster_gen.py": (
        "[Simulation generator — seeded RNG] cluster_gen.py generates synthetic "
        "GPU cluster job streams for scenario replay. Uses random with a fixed "
        "seed per scenario, making runs reproducible. Predates PSP-002; not part "
        "of the PMS decision path."
    ),
    "stressor_gen.py": (
        "[Simulation generator — seeded RNG] stressor_gen.py generates workload "
        "stress patterns for scenario testing. Same seeded-RNG rationale as "
        "cluster_gen.py."
    ),
    "param_sampler.py": (
        "[Simulation parameter sampler — seeded RNG] param_sampler.py samples "
        "from parameter distributions for Monte Carlo scenario variants. Seeded "
        "per run, reproducible. Predates PSP-002."
    ),
    "run_manager.py": (
        "[Simulation orchestrator — conditional seeded RNG] run_manager.py uses "
        "random for ID generation and scenario initialization, seeded by scenario "
        "spec. Predates PSP-002; not on the PMS decision path."
    ),
    "telemetry_corruption.py": (
        "[Telemetry corruption injector — seeded RNG] telemetry_corruption.py "
        "injects synthetic sensor faults for scenario testing. Seeded per scenario "
        "for reproducibility. Predates PSP-002."
    ),
}


# ── AST import scanner ────────────────────────────────────────────────────────

class _ImportHit(NamedTuple):
    filepath: pathlib.Path
    lineno: int
    imported_module: str       # first component of the dotted module name


def _first_component(dotted_name: str) -> str:
    """Return the top-level package name from a dotted module path."""
    return dotted_name.split(".")[0]


def _collect_imports(py_file: pathlib.Path) -> List[_ImportHit]:
    """Return all import first-components found in *py_file*."""
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    except (SyntaxError, UnicodeDecodeError):
        return []

    hits: List[_ImportHit] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                hits.append(_ImportHit(py_file, node.lineno, _first_component(alias.name)))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                hits.append(_ImportHit(py_file, node.lineno, _first_component(node.module)))
    return hits


def _scan_dir(directory: pathlib.Path) -> List[_ImportHit]:
    """Scan all .py files under *directory* (skipping __pycache__ and tests)."""
    hits: List[_ImportHit] = []
    for py_file in sorted(directory.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        if py_file.stem.startswith("test_"):
            continue
        hits.extend(_collect_imports(py_file))
    return hits


def _fmt(hit: _ImportHit) -> str:
    try:
        rel = hit.filepath.relative_to(_BACKEND_ROOT)
    except ValueError:
        rel = hit.filepath
    return f"  {rel}:{hit.lineno}  imports {hit.imported_module!r}"


# ── TC-C11: core/ must not import from runtime/ ───────────────────────────────

def test_tc_c11_core_has_no_runtime_dependency() -> None:
    """TC-C11: core/ has zero dependency on runtime/.

    Static import check — catches conditional imports too.
    Any file in core/ that imports 'runtime' (or any submodule thereof)
    fails this test.

    Rationale: core/ contains the physics and dispatch logic that must be
    callable identically in a simulator, a replay, and a production system.
    If core/ imports runtime/, the simulator's PMSTestDouble bleeds into the
    production path — a boundary violation that no runtime flag can fix (§5).
    """
    violations: List[_ImportHit] = []
    for hit in _scan_dir(_CORE_DIR):
        if hit.imported_module == "runtime":
            violations.append(hit)

    if violations:
        lines = ["\nTC-C11 FAILED — core/ imports runtime/:\n"]
        lines.extend(_fmt(h) for h in violations)
        lines.append(
            "\nThe production escalation path (§4.3) must never import PMSTestDouble "
            "from core/. The simulator/production fork lives at the harness level, "
            "outside both core/ and runtime/ (§5). Remove the import."
        )
        msg = "\n".join(lines)
        print(msg, file=sys.stderr)
        assert len(violations) == 0, msg


# ── TC-C12: runtime/ must not import southbound/LLM/RNG ──────────────────────

def test_tc_c12_runtime_no_southbound_clients() -> None:
    """TC-C12 (southbound): runtime/ has zero southbound protocol client imports.

    Southbound clients are banned everywhere (§6.1): core/, runtime/, scripts/.
    """
    violations: List[_ImportHit] = []
    for hit in _scan_dir(_RUNTIME_DIR):
        if hit.imported_module in _SOUTHBOUND_MODULES:
            violations.append(hit)

    # Also check core/ for southbound (belt-and-suspenders).
    for hit in _scan_dir(_CORE_DIR):
        if hit.imported_module in _SOUTHBOUND_MODULES:
            violations.append(hit)

    if violations:
        lines = ["\nTC-C12 (southbound) FAILED — forbidden protocol client import:\n"]
        lines.extend(_fmt(h) for h in violations)
        lines.append(
            "\n§6.1: No module anywhere in this subsystem holds a Modbus TCP, "
            "DNP3, OPC UA, or IEC 61850 client. This includes PMSTestDouble, "
            "which simulates a decision, never a live connection."
        )
        msg = "\n".join(lines)
        print(msg, file=sys.stderr)
        assert len(violations) == 0, msg


def test_tc_c12_runtime_no_llm_imports() -> None:
    """TC-C12 (LLM): runtime/ has zero LLM client imports.

    §6.2: scenario_author.py's Mistral calls happen once, offline, before a
    run starts.  Nothing in core/ or runtime/ calls any LLM API, ever.
    scripts/ is exempt (it IS the offline caller).
    """
    violations: List[_ImportHit] = []
    for hit in _scan_dir(_RUNTIME_DIR):
        if hit.imported_module in _LLM_MODULES_RUNTIME_BANNED:
            violations.append(hit)

    if violations:
        lines = ["\nTC-C12 (LLM) FAILED — runtime/ imports an LLM client:\n"]
        lines.extend(_fmt(h) for h in violations)
        lines.append(
            "\n§6.2: No runtime LLM calls. scenario_author.py's Mistral calls "
            "happen once, offline, before a run starts. Move LLM call logic to "
            "scripts/scenario_author.py and remove the import from runtime/."
        )
        msg = "\n".join(lines)
        print(msg, file=sys.stderr)
        assert len(violations) == 0, msg


def test_tc_c12_runtime_no_rng_imports() -> None:
    """TC-C12 (RNG): PSP-002 runtime files must not import the random module.

    PMSTestDouble must be deterministically reproducible (INV-7 / §3.4 /
    TC-C14).  The ban is scoped to PSP-002 subsystem files — pre-existing
    simulation generators (cluster_gen, stressor_gen, etc.) are explicitly
    exempted because they use seeded RNG for scenario reproducibility and
    are not part of the PMS decision loop.

    Any NEW file added to runtime/ that is part of the PSP-002 subsystem
    must not import random.  If a new simulation generator needs random,
    add it to _RNG_EXEMPTED_RUNTIME_FILES with a documented reason.
    """
    violations: List[_ImportHit] = []
    for hit in _scan_dir(_RUNTIME_DIR):
        if hit.imported_module in _RNG_MODULES_RUNTIME_BANNED:
            filename = hit.filepath.name
            if filename not in _RNG_EXEMPTED_RUNTIME_FILES:
                violations.append(hit)

    if violations:
        lines = [
            "\nTC-C12 (RNG) FAILED — PSP-002 runtime file imports 'random':\n"
        ]
        lines.extend(_fmt(h) for h in violations)
        lines.append(
            "\nINV-7 / TC-C14: PSP-002 runtime/ files must be deterministic. "
            "pms_test_double.py must use OperatorResponseProfile's approve/latency "
            "dicts (deterministic by construction) rather than random draws. "
            "If this is a legitimate simulation generator, add it to "
            "_RNG_EXEMPTED_RUNTIME_FILES with a documented reason."
        )
        msg = "\n".join(lines)
        print(msg, file=sys.stderr)
        assert len(violations) == 0, msg


# ── TC-C12 (scripts/ southbound): scripts/ also banned from southbound ────────

def test_tc_c12_scripts_no_southbound_clients() -> None:
    """scripts/ must not import southbound protocol clients (§6.1)."""
    violations: List[_ImportHit] = []
    for hit in _scan_dir(_SCRIPTS_DIR):
        if hit.imported_module in _SOUTHBOUND_MODULES:
            violations.append(hit)

    if violations:
        lines = ["\nTC-C12 (southbound / scripts) FAILED:\n"]
        lines.extend(_fmt(h) for h in violations)
        msg = "\n".join(lines)
        print(msg, file=sys.stderr)
        assert len(violations) == 0, msg


# ── TC-C13 structural: PMSTestDouble not reachable from core/ ─────────────────

def test_tc_c13_pms_test_double_not_in_core() -> None:
    """TC-C13 (structural): PMSTestDouble lives in runtime/, not core/.

    TC-C11 catches any actual import of runtime/ from core/, so this test
    is belt-and-suspenders: it confirms the class file is in the correct
    directory.  A misplaced file would satisfy TC-C11 vacuously (no import
    needed if it's already in core/).
    """
    in_core: List[pathlib.Path] = []
    for py_file in sorted(_CORE_DIR.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "PMSTestDouble" in source and "class PMSTestDouble" in source:
            in_core.append(py_file)

    if in_core:
        lines = ["\nTC-C13 FAILED — PMSTestDouble class defined in core/:\n"]
        lines.extend(f"  {f.relative_to(_BACKEND_ROOT)}" for f in in_core)
        lines.append(
            "\nPMSTestDouble must live in runtime/ only (§3.4 / §5). "
            "Move it to runtime/pms_test_double.py and remove from core/."
        )
        msg = "\n".join(lines)
        print(msg, file=sys.stderr)
        assert len(in_core) == 0, msg

    # Confirm it IS in runtime/ as expected.
    in_runtime = list(_RUNTIME_DIR.rglob("pms_test_double.py"))
    assert in_runtime, (
        "PMSTestDouble must be in runtime/pms_test_double.py — file not found."
    )
