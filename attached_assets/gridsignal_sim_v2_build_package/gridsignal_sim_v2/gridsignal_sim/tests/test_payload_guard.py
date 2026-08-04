"""
Phase 0 acceptance criterion 2 — payload field guard.

TC-GUARD-1  Every top-level key produced by _tick_result_to_dict() must have a
            matching property in the TypeScript TickPayload interface
            (frontend/src/types.ts).  Any backend key without a typed TS field
            fails this test.

A green TypeScript compile is NOT sufficient evidence — tsc does not reject
payloads that arrive at runtime with extra keys.  This test IS the guard.

RED / GREEN DEMONSTRATION (the required proof):
  1. Add a throwaway key to the return dict in _tick_result_to_dict(), e.g.:
         "_guard_demo_orphan": "red",
  2. Run:  pytest tests/test_payload_guard.py -v    → FAILS (GUARD RED).
  3. Remove the throwaway key.
  4. Run:  pytest tests/test_payload_guard.py -v    → PASSES (GUARD GREEN).

This file uses SOURCE-LEVEL parsing only — no evaluate_tick, no running the
simulation engine.  It is safe to run in isolation as a lint step.
"""
import re
import pathlib
import pytest


# ── Paths relative to this test file ─────────────────────────────────────────

_TESTS_DIR = pathlib.Path(__file__).parent
_ROOT       = _TESTS_DIR.parent                            # gridsignal_sim/
_RUN_MGR    = _ROOT / "runtime" / "run_manager.py"
_TYPES_TS   = _ROOT.parent / "frontend" / "src" / "types.ts"


# ── Source-level parsers ──────────────────────────────────────────────────────

def _python_keys_from_source(src_path: pathlib.Path) -> frozenset:
    """Return the set of string keys in the return dict of _tick_result_to_dict().

    Finds the function definition, locates its ``return {`` statement, then
    extracts all ``"key_name":`` patterns from inside the outermost braces.
    Sub-dict keys (e.g. inside the kube_metrics conditional dict) also match
    the regex, but they appear only inside nested ``{...}`` that get stripped
    first — so the frozenset contains only top-level outer keys.

    Strategy: locate the outer dict boundary, strip all nested ``{...}``
    blocks iteratively from the CONTENT between the outer braces (not
    including the outer braces themselves), then regex-extract string keys.
    """
    text = src_path.read_text(encoding="utf-8")
    fn_start  = text.index("def _tick_result_to_dict(")
    ret_start = text.index("return {", fn_start)

    # Walk the brace tree to find the closing } of the return dict.
    depth, end = 0, ret_start
    for i, ch in enumerate(text[ret_start:], ret_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    # Extract CONTENT between outer braces so the outer pair is never stripped.
    outer_open = text.index("{", ret_start)
    content = text[outer_open + 1 : end - 1]

    # Iteratively strip nested {…} blocks until none remain.
    prev = None
    flat = content
    while prev != flat:
        prev = flat
        flat = re.sub(r"\{[^{}]*\}", "{}", flat)

    # Extract string keys at the (now-flat) top level.
    keys = re.findall(r'"([a-z_][a-z0-9_]*)"\s*:', flat)
    return frozenset(keys)


def _ts_fields_from_source(ts_path: pathlib.Path) -> frozenset:
    """Return property names declared in the TickPayload interface in types.ts.

    Finds the ``export interface TickPayload {`` block, extracts the CONTENT
    between the outer braces, strips nested type expressions (``{...}``), then
    extracts ``identifier:`` and ``identifier?:`` property declarations.

    Key fix: we work on the CONTENT (not the whole block including outer braces)
    so the iterative ``{...}`` substitution never collapses the interface itself.
    """
    text = ts_path.read_text(encoding="utf-8")
    iface_start = text.index("export interface TickPayload {")

    depth, end = 0, iface_start
    for i, ch in enumerate(text[iface_start:], iface_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    # Extract CONTENT between the outer braces only.
    outer_open = text.index("{", iface_start)
    content = text[outer_open + 1 : end - 1]

    # Strip nested {…} blocks (e.g. sub-type shapes like per_agent: {...}).
    prev = None
    flat = content
    while prev != flat:
        prev = flat
        flat = re.sub(r"\{[^{}]*\}", "{}", flat)

    names: set[str] = set()
    for line in flat.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\??\s*:", line)
        if m:
            names.add(m.group(1))
    return frozenset(names)


# ── Guard tests ───────────────────────────────────────────────────────────────

def test_tc_guard_1_all_python_keys_have_ts_field():
    """TC-GUARD-1: every key in _tick_result_to_dict() output has a matching
    typed field in TickPayload.

    Fails with an explicit diff when any backend key is untyped, naming exactly
    which fields to add to frontend/src/types.ts.

    RED/GREEN proof:
      1. Add a throwaway key to _tick_result_to_dict() → this test FAILS.
      2. Remove the throwaway key               → this test PASSES.
    """
    python_keys = _python_keys_from_source(_RUN_MGR)
    ts_fields   = _ts_fields_from_source(_TYPES_TS)

    untyped = sorted(python_keys - ts_fields)

    assert not untyped, (
        f"\n\nGUARD RED \u2014 {len(untyped)} backend key(s) have no TypeScript TickPayload field:\n"
        + "\n".join(f"  \u2212 {k}" for k in untyped)
        + "\n\nAdd each missing field to `export interface TickPayload` in:\n"
        f"  {_TYPES_TS.relative_to(_ROOT.parent)}\n"
    )


def test_tc_guard_2_parsers_return_nonempty_sets():
    """Smoke test: both parsers must return at least 20 keys each, confirming
    the regex did not silently produce an empty set due to encoding or format
    changes in the source files."""
    python_keys = _python_keys_from_source(_RUN_MGR)
    ts_fields   = _ts_fields_from_source(_TYPES_TS)
    assert len(python_keys) >= 20, (
        f"Python parser returned only {len(python_keys)} keys from {_RUN_MGR.name}"
    )
    assert len(ts_fields) >= 20, (
        f"TS parser returned only {len(ts_fields)} fields from {_TYPES_TS.name}"
    )
