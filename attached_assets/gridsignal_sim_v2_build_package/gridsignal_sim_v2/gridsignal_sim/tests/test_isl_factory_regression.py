"""IMPL-ISL-8: implicit spinning-count defaults (TC-ISL-12 through 14)."""

import pytest

from api.routes.scenarios import build_seeded_store
from api.schemas import ScenarioSpec
from core.models import TurbineState
from runtime.scenario_factory import build_run_context_from_spec


def _spec():
    record = build_seeded_store().get("demo-20mw")
    spec = ScenarioSpec.model_validate_json(record.spec_json).model_dump(mode="json")
    spec.pop("initial_spinning_count", None)
    return spec


@pytest.mark.parametrize("explicit_none", [False, True], ids=["missing", "none"])
@pytest.mark.parametrize("standby_only", [False, True], ids=["empty", "standby-only"])
def test_tc_isl_12_no_eligible_turbines_builds_with_zero_synchronised(
    explicit_none, standby_only
):
    """TC-ISL-12: missing/None defaults to zero without an eligible turbine."""
    spec = _spec()
    spec["turbine_units"] = (
        [t for t in spec["turbine_units"] if t["hot_standby"]] if standby_only else []
    )
    if explicit_none:
        spec["initial_spinning_count"] = None
    state = build_run_context_from_spec("tc-isl-12", spec).sim_state
    assert not any(t.state == TurbineState.SYNCHRONISED for t in state.turbines)


@pytest.mark.parametrize("explicit_none", [False, True], ids=["missing", "none"])
def test_tc_isl_13_eligible_turbines_default_to_one_synchronised(explicit_none):
    """TC-ISL-13: the implicit default remains one when eligible units exist."""
    spec = _spec()
    if explicit_none:
        spec["initial_spinning_count"] = None
    state = build_run_context_from_spec("tc-isl-13", spec).sim_state
    assert len([t for t in state.turbines if not t.config.hot_standby]) >= 1
    assert sum(t.state == TurbineState.SYNCHRONISED for t in state.turbines) == 1


@pytest.mark.parametrize("empty_fleet", [False, True], ids=["eligible", "empty"])
def test_tc_isl_14_explicit_excess_count_still_raises(empty_fleet):
    """TC-ISL-14: an explicit excess count retains the exact validation error."""
    spec = _spec()
    if empty_fleet:
        spec["turbine_units"] = []
    available = sum(not t["hot_standby"] for t in spec["turbine_units"])
    spec["initial_spinning_count"] = available + 1
    expected = (
        f"initial_spinning_count={available + 1} exceeds "
        f"the {available} non-hot-standby turbine unit(s)"
    )
    with pytest.raises(ValueError) as exc:
        build_run_context_from_spec("tc-isl-14", spec)
    assert str(exc.value) == expected
