"""test_scenario_author.py — Unit tests for scripts/scenario_author.py.

Phase 5 (GS-IMPL-PSP-002 §9): "Wire scenario_author.py to the real
ScenarioSpec schema."

These tests cover:
  - _normalise_profile(): string-key → int-key conversion.
  - _validate_against_schema(): OperatorResponseProfile construction +
    dataclasses.asdict() round-trip.
  - generate_operator_response_profile() validation path (Mistral mocked).
  - CLI-level round-trip: JSON output loadable as OperatorResponseProfile.

No Mistral API calls are made.  Tests that exercise generate_operator_response_profile()
inject a fake `mistralai` module via sys.modules so the validation and
serialisation paths are exercised without the package installed or an API key.

Why sys.modules injection (not patch("mistralai.Mistral"))?
-----------------------------------------------------------
`mistralai` is not installed in this environment — it is an offline-only
dependency.  `patch("mistralai.Mistral")` resolves the target at patch-time,
which fails with ModuleNotFoundError before any mocking occurs.
Injecting a MagicMock into sys.modules lets the lazy `from mistralai import Mistral`
inside generate_operator_response_profile() see the mock without requiring the
real package.

Import note
-----------
scripts/ is allowed to import from runtime/ (§3.5 rules — banned direction
is runtime/ importing scripts/, not the other way around).  The import in
scenario_author.py is therefore intentional and tested here.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from contextlib import contextmanager
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest


# ── Helper: import scripts.scenario_author ───────────────────────────────────

def _sa():
    """Return the scripts.scenario_author module (lazy import once)."""
    import scripts.scenario_author as _mod
    return _mod


# ── _normalise_profile() ──────────────────────────────────────────────────────

class TestNormaliseProfile:
    """_normalise_profile converts Mistral string-rank-keys to int keys."""

    def test_string_keys_converted_to_int(self) -> None:
        sa = _sa()
        raw = {
            "response_latency_s": {"1": 45.0, "2": 90.0},
            "approve": {"1": True, "2": False},
        }
        result = sa._normalise_profile(raw)
        assert result == {
            "response_latency_s": {1: 45.0, 2: 90.0},
            "approve": {1: True, 2: False},
        }

    def test_empty_raw_returns_empty_dict(self) -> None:
        sa = _sa()
        assert sa._normalise_profile({}) == {}

    def test_only_latency_field(self) -> None:
        sa = _sa()
        raw = {"response_latency_s": {"3": 60.0}}
        result = sa._normalise_profile(raw)
        assert result == {"response_latency_s": {3: 60.0}}

    def test_only_approve_field(self) -> None:
        sa = _sa()
        raw = {"approve": {"1": False}}
        result = sa._normalise_profile(raw)
        assert result == {"approve": {1: False}}

    def test_unknown_fields_not_included(self) -> None:
        """Fields outside response_latency_s / approve are silently dropped."""
        sa = _sa()
        raw = {"response_latency_s": {"1": 30.0}, "extra_key": "should_be_dropped"}
        result = sa._normalise_profile(raw)
        assert "extra_key" not in result


# ── _validate_against_schema() ────────────────────────────────────────────────

class TestValidateAgainstSchema:
    """_validate_against_schema() validates via OperatorResponseProfile + asdict()."""

    def test_valid_profile_dict_passes(self) -> None:
        sa = _sa()
        profile_dict: Dict[str, Any] = {
            "response_latency_s": {1: 45.0, 2: 90.0},
            "approve": {1: True, 2: False},
        }
        result = sa._validate_against_schema(profile_dict)
        # Must return a dict (serialisable)
        assert isinstance(result, dict)

    def test_empty_dict_passes(self) -> None:
        """Empty profile dict → OperatorResponseProfile with defaults is valid."""
        sa = _sa()
        result = sa._validate_against_schema({})
        assert isinstance(result, dict)

    def test_output_includes_defaults(self) -> None:
        """Output dict includes default_latency_s and default_approve from schema."""
        sa = _sa()
        result = sa._validate_against_schema({})
        assert "default_latency_s" in result, (
            "_validate_against_schema() must use dataclasses.asdict() which "
            "includes all fields (including defaults)."
        )
        assert "default_approve" in result

    def test_output_roundtrips_as_operator_response_profile(self) -> None:
        """Output dict can be loaded back as OperatorResponseProfile(**dict)."""
        from runtime.pms_test_double import OperatorResponseProfile
        sa = _sa()
        profile_dict = {
            "response_latency_s": {1: 45.0},
            "approve": {1: True},
        }
        result = sa._validate_against_schema(profile_dict)
        # The canonical consumer pattern from scenario_author.py docstring:
        #   profile = OperatorResponseProfile(**json.load(open("...")))
        # Simulate JSON round-trip (JSON turns int dict keys to strings).
        json_round_tripped = json.loads(json.dumps(result))
        # OperatorResponseProfile expects int keys — _normalise_profile handles this.
        # After JSON round-trip, keys are strings again; re-normalise to int.
        for field_name in ("response_latency_s", "approve"):
            if field_name in json_round_tripped and isinstance(
                json_round_tripped[field_name], dict
            ):
                json_round_tripped[field_name] = {
                    int(k): v for k, v in json_round_tripped[field_name].items()
                }
        reloaded = OperatorResponseProfile(**json_round_tripped)
        assert reloaded.latency_for(1) == 45.0
        assert reloaded.approves(1) is True

    def test_invalid_extra_kwargs_raise_type_error(self) -> None:
        """Unexpected keyword args raise TypeError at OperatorResponseProfile() call."""
        sa = _sa()
        with pytest.raises(TypeError):
            sa._validate_against_schema({"nonexistent_field": "bad_value"})

    def test_output_is_json_serialisable(self) -> None:
        """_validate_against_schema() output can be json.dump()ed without error."""
        sa = _sa()
        result = sa._validate_against_schema({
            "response_latency_s": {1: 30.0},
            "approve": {1: False},
        })
        # Must not raise
        json_str = json.dumps(result)
        assert isinstance(json_str, str)


# ── Helpers for mocking the offline-only mistralai package ───────────────────

@contextmanager
def _fake_mistral(llm_json_content: str):
    """Context manager: inject a fake mistralai module into sys.modules.

    `mistralai` is not installed in this environment (offline-only dependency).
    `patch("mistralai.Mistral")` fails at target-resolution time with
    ModuleNotFoundError before any mocking occurs.  Injecting a MagicMock
    directly into sys.modules lets the lazy `from mistralai import Mistral`
    inside generate_operator_response_profile() pick up the mock.

    Usage::

        with _fake_mistral('{"approve": {"1": true}}') as mock_client:
            result = sa.generate_operator_response_profile(...)
    """
    choice = MagicMock()
    choice.message.content = llm_json_content
    response = MagicMock()
    response.choices = [choice]

    mock_client = MagicMock()
    mock_client.chat.complete.return_value = response

    fake_mod = MagicMock()
    fake_mod.Mistral.return_value = mock_client

    prev = sys.modules.get("mistralai")
    sys.modules["mistralai"] = fake_mod
    try:
        yield mock_client
    finally:
        if prev is None:
            sys.modules.pop("mistralai", None)
        else:
            sys.modules["mistralai"] = prev


# ── generate_operator_response_profile() — validation path ───────────────────

class TestGenerateProfileValidationPath:
    """generate_operator_response_profile() calls _validate_against_schema().

    Mistral is mocked via sys.modules injection so these tests run without
    the package installed or an API key.  The mock returns a plausible
    JSON-string profile; the test verifies that the validation + serialisation
    path runs correctly end-to-end.
    """

    def test_validation_runs_on_valid_llm_output(self) -> None:
        """Validation path executes without error for schema-valid Mistral output."""
        import os
        sa = _sa()
        llm_json = json.dumps({
            "response_latency_s": {"1": 45.0, "2": 90.0},
            "approve": {"1": True, "2": False},
        })
        prev_key = os.environ.get("MISTRAL_API_KEY")
        os.environ["MISTRAL_API_KEY"] = "test-key"
        try:
            with _fake_mistral(llm_json):
                result = sa.generate_operator_response_profile(
                    persona="test persona",
                    requests=["approve rank 1"],
                )
        finally:
            if prev_key is None:
                os.environ.pop("MISTRAL_API_KEY", None)
            else:
                os.environ["MISTRAL_API_KEY"] = prev_key

        assert isinstance(result, dict)
        # Output must include schema defaults (from dataclasses.asdict)
        assert "default_latency_s" in result
        assert "default_approve" in result

    def test_unknown_llm_fields_dropped_by_whitelist_filter(self) -> None:
        """Unknown fields in Mistral output are silently dropped by _normalise_profile().

        _normalise_profile() is a strict whitelist: only `response_latency_s`
        and `approve` are passed through.  Unknown keys (Mistral hallucinations)
        never reach _validate_against_schema(), so they produce a valid
        OperatorResponseProfile with defaults rather than raising.

        This is the correct guard: _normalise_profile() is the hallucination
        filter; _validate_against_schema() then validates that the *filtered*
        dict is schema-conformant.  Rejecting unknown fields at the LLM output
        level would break any future Mistral version that returns verbose metadata
        alongside the profile JSON.
        """
        import os
        sa = _sa()
        # Mistral returned a verbose response with a key outside the schema
        llm_json = json.dumps({"unknown_llm_field": "extra_context"})
        prev_key = os.environ.get("MISTRAL_API_KEY")
        os.environ["MISTRAL_API_KEY"] = "test-key"
        try:
            with _fake_mistral(llm_json):
                result = sa.generate_operator_response_profile(
                    persona="test persona",
                    requests=["approve rank 1"],
                )
        finally:
            if prev_key is None:
                os.environ.pop("MISTRAL_API_KEY", None)
            else:
                os.environ["MISTRAL_API_KEY"] = prev_key

        # Unknown field was dropped; output is a valid default profile
        assert isinstance(result, dict)
        assert "unknown_llm_field" not in result
        # Schema defaults present because _validate_against_schema uses dataclasses.asdict()
        assert "default_latency_s" in result
        assert "default_approve" in result

    def test_result_loadable_as_operator_response_profile(self) -> None:
        """Output dict is loadable as OperatorResponseProfile (after JSON round-trip)."""
        import os
        from runtime.pms_test_double import OperatorResponseProfile
        sa = _sa()
        llm_json = json.dumps({
            "response_latency_s": {"1": 30.0},
            "approve": {"1": True},
        })
        prev_key = os.environ.get("MISTRAL_API_KEY")
        os.environ["MISTRAL_API_KEY"] = "test-key"
        try:
            with _fake_mistral(llm_json):
                result = sa.generate_operator_response_profile(
                    persona="test persona",
                    requests=["approve rank 1"],
                )
        finally:
            if prev_key is None:
                os.environ.pop("MISTRAL_API_KEY", None)
            else:
                os.environ["MISTRAL_API_KEY"] = prev_key

        # JSON round-trip (int dict keys become strings in JSON)
        loaded = json.loads(json.dumps(result))
        for field_name in ("response_latency_s", "approve"):
            if field_name in loaded and isinstance(loaded[field_name], dict):
                loaded[field_name] = {int(k): v for k, v in loaded[field_name].items()}

        profile = OperatorResponseProfile(**loaded)
        assert profile.latency_for(1) == 30.0
        assert profile.approves(1) is True


# ── Boundary: scenario_author must not be imported by core/ or runtime/ ──────

class TestScenarioAuthorImportBoundary:
    """scripts/ must not be imported by core/ or runtime/ (§1 / §6.2 / TC-C11)."""

    def test_core_does_not_import_scenario_author(self) -> None:
        """No file in core/ imports from scripts.scenario_author."""
        import ast
        import pathlib
        core_dir = pathlib.Path(__file__).parent.parent / "core"
        violations = []
        for py_file in sorted(core_dir.glob("*.py")):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if "scenario_author" in module or module.startswith("scripts"):
                        violations.append(f"{py_file.name}: from {module} import ...")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if "scenario_author" in alias.name or alias.name.startswith("scripts"):
                            violations.append(f"{py_file.name}: import {alias.name}")
        assert not violations, f"core/ must not import from scripts/: {violations}"

    def test_runtime_does_not_import_scenario_author(self) -> None:
        """No file in runtime/ imports from scripts.scenario_author."""
        import ast
        import pathlib
        runtime_dir = pathlib.Path(__file__).parent.parent / "runtime"
        violations = []
        for py_file in sorted(runtime_dir.glob("*.py")):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if "scenario_author" in module or module.startswith("scripts"):
                        violations.append(f"{py_file.name}: from {module} import ...")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if "scenario_author" in alias.name or alias.name.startswith("scripts"):
                            violations.append(f"{py_file.name}: import {alias.name}")
        assert not violations, f"runtime/ must not import from scripts/: {violations}"
