"""Acceptance tests for the authoritative per-tick physical balance invariant."""

import json

from core import site_parameters as _sp
from core.models import IslandMode
from core.power_balance import (
    BalanceTerms,
    evaluate_physical_balance,
)
from runtime.persistence import _tick_to_json
from runtime.run_manager import _tick_result_to_dict
from tests.test_forecast_path import _make_state, _run_tick, _starting_signal


def test_simulation_tick_attaches_one_physical_balance_result() -> None:
    tick = _run_tick(_make_state(), sim_time=0.0, dt=5.0)

    assert tick.physical_balance is not None
    assert tick.physical_balance.passed is True
    assert tick.physical_balance.independent is True
    assert tick.physical_balance.verification_mode == "islanded_verified"
    assert tick.physical_balance.tolerance_mw == _sp.value(
        "balance_defect_tolerance_mw"
    )
    assert _tick_result_to_dict(tick)["physical_balance"]["passed"] is True
    assert _tick_result_to_dict(tick)["physical_balance"][
        "verification_mode"
    ] == "islanded_verified"
    assert json.loads(_tick_to_json(tick))["physical_balance"][
        "residual_magnitude_mw"
    ] == 0.0


def test_balanced_tick_passes_the_physical_balance_invariant() -> None:
    result = evaluate_physical_balance(
        BalanceTerms(
            p_generation_mw=12.0,
            p_demand_mw=12.0,
            p_served_mw=12.0,
            island_mode="ISLANDED",
        ),
        tolerance_mw=_sp.value("balance_defect_tolerance_mw"),
    )

    assert result.passed is True
    assert result.independent is True
    assert result.residual_magnitude_mw == 0.0
    assert result.term_breakdown["generation_mw"] == 12.0
    assert result.term_breakdown["served_load_mw"] == 12.0


def test_injected_imbalance_fails_the_physical_balance_invariant() -> None:
    result = evaluate_physical_balance(
        BalanceTerms(
            p_generation_mw=12.0,
            p_demand_mw=12.5,
            p_served_mw=12.5,
            island_mode="ISLANDED",
        ),
        tolerance_mw=_sp.value("balance_defect_tolerance_mw"),
    )

    assert result.passed is False
    assert result.independent is True
    assert result.residual_magnitude_mw == 0.5
    assert result.term_breakdown["generation_mw"] == 12.0
    assert result.term_breakdown["served_load_mw"] == 12.5


def test_grid_tied_balance_is_explicitly_provisional() -> None:
    result = evaluate_physical_balance(
        BalanceTerms(
            p_generation_mw=12.0,
            p_demand_mw=12.0,
            p_served_mw=12.0,
            island_mode="grid_tie",
        ),
        tolerance_mw=_sp.value("balance_defect_tolerance_mw"),
    )

    assert result.passed is True
    assert result.independent is False
    assert result.verification_mode == "grid_tied_provisional"
    assert result.to_dict()["independent"] is False


def test_islanded_generation_deficit_remains_a_real_balance_residual() -> None:
    """Supply deficit must not be converted into unserved load by accounting."""
    state = _make_state(
        bess_soc=0.0,
        bess_mwh=0.01,
        bess_rated_mw=5.0,
        island_mode=IslandMode.ISLANDED,
    )
    state.apply_workload_signal(
        _starting_signal(nodes=10, ramp_s=1.0, timestamp=0.0),
        dt_lead_seconds=0.0,
    )

    for tick_index in range(5):
        tick = _run_tick(state, sim_time=float(tick_index) * 5.0, dt=5.0)

    balance = tick.physical_balance
    assert balance is not None
    assert balance.independent is True
    assert balance.verification_mode == "islanded_verified"
    assert tick.p_generation_mw == 0.0
    assert tick.p_unserved_mw == 0.0
    assert tick.p_served_mw == tick.p_demand_mw
    assert tick.p_imbalance_mw == -tick.p_demand_mw
    assert balance.passed is False
    assert balance.defect_mw == tick.p_imbalance_mw