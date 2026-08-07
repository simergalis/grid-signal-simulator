"""test_no_hardcoded_parameters.py — Guard D (GS-DES-CFG-001 §D).

Guard D scans backend Python source files and compares hard-coded numeric
literals against the values in gridsignal_parameters.json.

Guard D1 (BLOCKING — test_guard_d1_no_drift)
  Fails if any literal disagrees with its catalogue counterpart.
  Three drifts exist in the current (Phase 0) tree and are expected.
  Do not fix them in Phase 0.  Fix them in Phase 1.

Guard D2 (INFORMATIONAL — test_guard_d2_backlog_reported)
  Always passes.  Prints every literal that agrees with the catalogue
  but is still hard-coded rather than read via site_parameters.value().
  Migrate all D2 literals in Phase 2.

Scan target: backend/core/, backend/renewable/
  Per GS-DES-CFG-001: NOT in scope are gridsignal_logger.py,
  test files, or any file outside the two target packages.

Key normalisation (code name → catalogue key)
  1. Exact match.
  2. Strip one recognised suffix: _seconds → try bare key.
  (e.g. "tau_seconds" → "tau"; "dt_thermal_seconds" → "dt_thermal")
  No other normalisation — guard exemptions are decisions on the record
  and must not be widened to make the backlog shorter.

Value comparison
  Numeric equality within 1 × 10⁻⁶ (relative) to handle float
  representation differences (e.g. 0.20 == 0.2).

State field exemptions
  _STATE_FIELD_EXEMPTIONS lists names that are legitimately 0.0 /
  False in code but appear with a non-zero default in the catalogue
  (runtime state vs. configuration default).  Currently exactly one
  entry.  Adding an exemption requires a stated reason.
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys
from typing import Any, Dict, List, NamedTuple, Optional


# ── Configuration ─────────────────────────────────────────────────────────────

# Root of the gridsignal_sim package — the directory that contains core/, tests/,
# renewable/, etc.  Derived from this file's location (tests/test_no_hardcoded_...py)
_BACKEND_ROOT = pathlib.Path(__file__).parent.parent

_SCAN_DIRS = [
    _BACKEND_ROOT / "core",
    _BACKEND_ROOT / "renewable",
]

_PARAMS_JSON = _BACKEND_ROOT / "gridsignal_parameters.json"

# _SCAN_EXEMPTIONS: code identifiers whose catalogue name matches but whose
# code value intentionally differs from the catalogue default.  Each entry
# MUST document why the exemption is sound; vague exemptions are prohibited
# (GS-DES-CFG-001 §D: "exemptions are decisions on the record").
#
# Two legitimate reasons:
#   A. RUNTIME STATE — field is a quantity accumulated during a tick, not a
#      configuration default.  Same name, different physical slot.
#   B. SAME-NAME / DIFFERENT-QUANTITY — the code field and the catalogue key
#      share a name but represent different physical parameters or scales.
#      The production simulation overrides via a more specific source.
_SCAN_EXEMPTIONS: Dict[str, str] = {
    "p_renewable_mw": (
        "[Reason A — runtime state] "
        "TickResult.p_renewable_mw default = 0.0 is runtime state — the quantity "
        "produced by the renewable subsystem this tick, not the scenario-config default "
        "(catalogue PARAM-10 = 3.0 MW). Different slots, same name."
    ),
    "bess_rated_mw": (
        "[Reason B — same name / different quantity] "
        "renewable.config.SiteConfig.bess_rated_mw = 10.0 is an intentional operating "
        "assumption for the SolarSim fixture (de-rated / test-convenience value). "
        "PARAM-07 bess_rated_mw = 15.0 MW (VENDOR_RATING) is the hardware nameplate. "
        "Production simulations always override via BessUnitSpec.rated_mw (scenarios.py "
        "uniformly uses 18.0 MW). Changing to 15.0 makes "
        "test_compound_event_is_additive_and_fails_at_seed erroneously pass because "
        "bridging capacity then exceeds the sizing-case shortfall by 11 kW."
    ),
    "t_min_run_s": (
        "[Reason B — disable-flag default vs. CHOSEN production default] "
        "TurbineConfig.t_min_run_s = 0.0 is the disable-flag sentinel: 0.0 means "
        "'no minimum run time constraint' and is required by the majority of unit tests "
        "that create TurbineConfig() directly without a scenario spec.  "
        "The catalogue value (1800.0 s, CHOSEN / §7.1.3.6) is the production scenario "
        "default applied by the scenario factory (_turbine() helper) and "
        "runtime/scenario_factory.py for all seeded scenarios.  Both values are "
        "intentional and represent different physical slots: the code default is a "
        "feature-off switch; the catalogue value is the CHOSEN operating constraint.  "
        "Phase E Item 8."
    ),
    "t_min_down_s": (
        "[Reason B — disable-flag default vs. CHOSEN production default] "
        "TurbineConfig.t_min_down_s = 0.0 is the disable-flag sentinel: 0.0 means "
        "'no minimum down time constraint' and is required by unit tests (e.g. TC-203-3) "
        "that explicitly exercise the zero-cooldown path.  "
        "The catalogue value (900.0 s, CHOSEN / §7.1.3.6) is the production scenario "
        "default applied by the scenario factory and _turbine() helper.  Symmetric "
        "justification to t_min_run_s.  Phase E Item 8."
    ),
}

# Suffixes to strip when trying to map a code name to a catalogue key.
_STRIP_SUFFIXES = ("_seconds",)


# ── Catalogue loading ─────────────────────────────────────────────────────────

def _load_catalogue() -> Dict[str, Any]:
    """Return key → catalogue_default for all adjustable and locked entries."""
    with open(_PARAMS_JSON, encoding="utf-8") as fh:
        raw = json.load(fh)
    result: Dict[str, Any] = {}
    for section in ("adjustable", "locked"):
        for entry in raw.get(section, []):
            key = entry["key"]
            # locked entries use "value"; adjustable entries use "default"
            val = entry.get("value") if section == "locked" else entry.get("default")
            if val is not None and isinstance(val, (int, float)):
                result[key] = float(val)
    return result


# ── AST scanner ───────────────────────────────────────────────────────────────

class _Hit(NamedTuple):
    filepath: pathlib.Path
    lineno: int
    code_name: str
    catalogue_key: str
    code_value: float
    catalogue_value: float


def _try_map_to_catalogue(name: str, catalogue: Dict[str, float]) -> Optional[str]:
    """Map a code identifier to a catalogue key, or return None."""
    if name in catalogue:
        return name
    for suffix in _STRIP_SUFFIXES:
        if name.endswith(suffix):
            bare = name[: -len(suffix)]
            if bare in catalogue:
                return bare
    return None


def _numeric_value(node: Optional[ast.expr]) -> Optional[float]:
    """Extract a numeric literal value from an AST expression node."""
    if node is None:
        return None
    # Python 3.8+: ast.Constant covers int and float literals
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    # Negative literal: UnaryOp(op=USub, operand=Constant(...))
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    ):
        return -float(node.operand.value)
    return None


def _scan_file(path: pathlib.Path, catalogue: Dict[str, float]) -> List[_Hit]:
    """Scan one Python file and return all catalogue-matching literals."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    hits: List[_Hit] = []

    for node in ast.walk(tree):
        # ── Annotated assignment: name: Type = value ────────────────────────
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if not isinstance(target, ast.Name):
                continue
            code_name = target.id
            if code_name in _SCAN_EXEMPTIONS:
                continue
            cat_key = _try_map_to_catalogue(code_name, catalogue)
            if cat_key is None:
                continue
            num = _numeric_value(node.value)
            if num is None:
                continue
            hits.append(_Hit(
                filepath=path,
                lineno=node.lineno,
                code_name=code_name,
                catalogue_key=cat_key,
                code_value=num,
                catalogue_value=catalogue[cat_key],
            ))

        # ── Plain assignment: name = value ──────────────────────────────────
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if not isinstance(tgt, ast.Name):
                    continue
                code_name = tgt.id
                if code_name in _SCAN_EXEMPTIONS:
                    continue
                cat_key = _try_map_to_catalogue(code_name, catalogue)
                if cat_key is None:
                    continue
                num = _numeric_value(node.value)
                if num is None:
                    continue
                hits.append(_Hit(
                    filepath=path,
                    lineno=node.lineno,
                    code_name=code_name,
                    catalogue_key=cat_key,
                    code_value=num,
                    catalogue_value=catalogue[cat_key],
                ))

    return hits


def _scan_all() -> List[_Hit]:
    """Scan all target Python files and return all catalogue-matching literals."""
    catalogue = _load_catalogue()
    hits: List[_Hit] = []
    for scan_dir in _SCAN_DIRS:
        for py_file in sorted(scan_dir.rglob("*.py")):
            # Skip test files and __pycache__
            if "test" in py_file.stem or "__pycache__" in str(py_file):
                continue
            hits.extend(_scan_file(py_file, catalogue))
    return hits


def _is_drift(hit: _Hit) -> bool:
    """True if the code value disagrees with the catalogue value."""
    if hit.catalogue_value == 0.0:
        return hit.code_value != 0.0
    rel_diff = abs(hit.code_value - hit.catalogue_value) / abs(hit.catalogue_value)
    return rel_diff > 1e-6


def _fmt_hit(hit: _Hit, relative_root: Optional[pathlib.Path] = None) -> str:
    path_str = str(hit.filepath)
    if relative_root:
        try:
            path_str = str(hit.filepath.relative_to(relative_root))
        except ValueError:
            pass
    return (
        f"  {path_str}:{hit.lineno}  "
        f"{hit.code_name} = {hit.code_value}"
        f"  vs catalogue '{hit.catalogue_key}' = {hit.catalogue_value}"
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_guard_d1_no_drift() -> None:
    """D1: fail if any code literal disagrees with its catalogue counterpart.

    Phase 1 resolution (all three Phase 0 drifts resolved):
      pue_base          — catalogue corrected to 1.03 (code wins; IT-side overhead only).
      band_pct_calibrated — code changed to 4.0; band_enabled: bool added to SiteConfig.
      bess_rated_mw     — exempted (_SCAN_EXEMPTIONS, Reason B): renewable/config.py
                          uses an intentional de-rated operating assumption (10.0 MW);
                          PARAM-07 = 15.0 MW is the vendor nameplate.  Production
                          simulations override via BessUnitSpec.rated_mw (18.0 MW).

    This test must pass (0 drifts) at the Phase 1 gate.
    """
    all_hits = _scan_all()
    drifts = [h for h in all_hits if _is_drift(h)]

    if drifts:
        lines = [
            "\nGuard D1 — code literals disagree with gridsignal_parameters.json:\n"
        ]
        for h in drifts:
            lines.append(_fmt_hit(h, _BACKEND_ROOT))
        msg = "\n".join(lines)
        print(msg, file=sys.stderr)
        assert len(drifts) == 0, msg


def test_guard_d2_backlog_reported() -> None:
    """D2: report all catalogue-matching literals that are still hard-coded.

    This test always passes.  It prints the D2 backlog so the Phase 2
    migration has a complete inventory to work from.  Promote D2 to
    blocking after CFG-6 inventory is complete (Phase 2 gate).
    """
    all_hits = _scan_all()
    matches = [h for h in all_hits if not _is_drift(h)]

    if matches:
        print(
            "\nGuard D2 backlog — catalogue-matching literals still hard-coded:\n"
            "(These agree with the catalogue today but must be migrated in Phase 2.)"
        )
        for h in matches:
            print(_fmt_hit(h, _BACKEND_ROOT))
        print(f"\n  Total D2 literals: {len(matches)}")
    else:
        print("\nGuard D2 backlog: empty (all matching literals migrated).")
