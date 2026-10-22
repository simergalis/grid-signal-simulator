"""TC-ISL-08a–d: D3 observation only (07 is already staging-start logging)."""
import copy
import json
from unittest.mock import patch

import pytest

from api.schemas import ScenarioSpec
from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.frequency_reporting import frequency_is_valid, protection_is_configured
from runtime.persistence import _tick_to_json
from runtime.run_manager import _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec


def context(**overrides):
    # PROPOSED_HERE: small zero-load inverter-only fixture isolates reporting;
    # these are test inputs, not defaults or changes to production scenarios.
    raw = dict(name="tc-isl-08", island_mode=True, turbine_units=[],
               solar_rated_mw=0.0, pue_base=1.0,
               bess_units=[dict(asset_id="bess", rated_mw=10.0, usable_mwh=20.0,
                                initial_soc_fraction=1.0, grid_forming=True)])
    raw.update(overrides)
    spec = ScenarioSpec.model_validate(raw)
    return build_run_context_from_spec("tc-isl-08", spec.model_dump(mode="json"))


def step(ctx):
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        return ctx.step()
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def test_tc_isl_08a_unprotected_island_flags_and_wire_persistence():
    tick = step(context())
    assert tick.protection_configured is False
    assert tick.frequency_valid is True
    for encoded in [_tick_result_to_dict(tick), json.loads(_tick_to_json(tick))]:
        assert encoded["protection_configured"] is False
        assert encoded["frequency_valid"] is True
    print({"TC-ISL-08a": dict(protection_configured=False, frequency_valid=True)})


@pytest.mark.parametrize("nominal,frequency,valid", [
    (60.0, 54.0, True), (60.0, 66.0, True), (60.0, 53.9, False),
    (60.0, 90.0, False), (50.0, 45.0, True), (50.0, 55.0, True),
    (50.0, 55.1, False),
])
def test_tc_isl_08b_band_does_not_modify_frequency(nominal, frequency, valid):
    # PROPOSED_HERE: explicit boundary/outside-band reporting samples.
    assert frequency_is_valid(frequency, nominal) is valid
    print({"TC-ISL-08b": [nominal, frequency, valid]})


def test_tc_isl_08b_tick_frequency_unchanged_when_flag_changes():
    ctx = context()
    ctx.sim_state._frequency_hz = 90.0  # PROPOSED_HERE: invalid, unclamped test initial state.
    other = copy.deepcopy(ctx)
    actual = step(ctx)
    with patch("core.simulation_core.frequency_is_valid", return_value=True):
        reference = step(other)
    assert actual.frequency_valid is False
    assert reference.frequency_valid is True
    assert actual.frequency_hz == reference.frequency_hz
    assert actual.frequency_hz > 66.0
    print({"TC-ISL-08b unchanged achieved Hz": actual.frequency_hz})


# PROPOSED_HERE: synthetic protection fixtures, not production threshold defaults.
@pytest.mark.parametrize("extra", [
    {"island_mode": False}, {"uf_warning_hz": 59.5},
    {"relay_81u_threshold_hz": 57.5},
    {"ufls_stages": [{"threshold_hz": 58.0, "delay_s": 1.0, "block_fraction": .1}]},
])
def test_tc_isl_08c_grid_tied_or_protected(extra):
    ctx = context(**extra)
    assert protection_is_configured(ctx.sim_state.site)
    assert step(ctx).protection_configured is True
    print({"TC-ISL-08c": extra, "protection_configured": True})


def test_tc_isl_08d_null_protection_warns_and_still_validates(caplog):
    ctx = context()
    # DR R5.2: validation still succeeds; runtime owns the non-rejecting warning.
    from api.schemas import StartRunResponse
    assert "DR D3 build warning" in caplog.text
    warning = next(w for w in ctx.metadata["build_warnings"]
                   if w["code"] == "islanded_frequency_protection_unconfigured")
    assert warning["message"] == "islanded run without frequency protection configured"
    assert ctx.sim_state.site.uf_warning_hz is None
    assert ctx.sim_state.site.of_trip_hz is None
    assert StartRunResponse(
        run_id=ctx.run_id, build_warnings=ctx.metadata["build_warnings"],
    ).build_warnings == ctx.metadata["build_warnings"]
    print({"TC-ISL-08d": warning, "build": "succeeded"})
