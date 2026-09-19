"""Focused coverage for the conventional turbine-generation comparison policy."""

from __future__ import annotations

import pytest

from runtime.scenario_factory import build_run_context_from_spec


def _policy_spec(mode: str = "baseline") -> dict:
    return {
        "name": "conventional-generation-policy",
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
        "turbine_commitment_mode": mode,
        "generation_baseload_mw": 80.0,
        "generation_peak_following": True,
        "initial_spinning_count": 2,
        "turbine_units": [
            {
                "asset_id": "gt-1",
                "rated_mw": 25.0,
                "initial_state": "spinning",
            },
            {
                "asset_id": "gt-2",
                "rated_mw": 25.0,
                "initial_state": "spinning",
            },
            {
                "asset_id": "gt-3",
                "rated_mw": 25.0,
                "hot_standby": True,
                "thermal_state": "hot",
            },
            {
                "asset_id": "gt-4",
                "rated_mw": 25.0,
                "hot_standby": True,
                "thermal_state": "hot",
            },
        ],
        "bess_units": [
            {
                "asset_id": "bess-1",
                "rated_mw": 30.0,
                "usable_mwh": 60.0,
            }
        ],
    }


def test_baseline_holds_80_mw_then_follows_and_returns_after_peak() -> None:
    ctx = build_run_context_from_spec(
        "conventional-baseload-policy",
        _policy_spec(),
    )

    # The two hot-standby units start sequentially.  At 650 s the four-unit
    # fleet has reached the requested 80 MW floor.
    for _ in range(130):
        result = ctx.step()
    assert result.turbine_output_mw == pytest.approx(80.0, abs=1e-6)
    assert result.gt_setpoint_mw == pytest.approx(80.0, abs=1e-6)

    # A 95 MW site peak must increase turbine generation rather than letting
    # the BESS silently provide the entire increment.
    ctx.sim_state.compute_floor_mw = 95.0
    peak_results = [ctx.step() for _ in range(8)]
    assert peak_results[0].turbine_output_mw > 80.0
    assert peak_results[-1].turbine_output_mw == pytest.approx(95.0, abs=1e-6)
    assert peak_results[-1].gt_setpoint_mw == pytest.approx(95.0, abs=1e-6)

    # Once the peak ends, the thermal target returns to the conventional floor
    # and the existing turbine ramp limits are respected on the way down.
    ctx.sim_state.compute_floor_mw = 0.0
    recovery_results = [ctx.step() for _ in range(8)]
    assert recovery_results[-1].turbine_output_mw == pytest.approx(80.0, abs=1e-6)
    assert recovery_results[-1].gt_setpoint_mw == pytest.approx(80.0, abs=1e-6)
    assert all(
        earlier.turbine_output_mw >= later.turbine_output_mw
        for earlier, later in zip(recovery_results, recovery_results[1:])
    )


def test_generation_baseload_policy_is_not_applied_to_informed_mode() -> None:
    ctx = build_run_context_from_spec(
        "informed-unconstrained-by-conventional-policy",
        _policy_spec(mode="informed"),
    )

    for _ in range(130):
        result = ctx.step()

    # Informed mode remains the optimization policy even if the same scenario
    # carries the optional comparison field.
    assert result.turbine_output_mw == pytest.approx(17.5, abs=1e-6)
    assert result.gt_setpoint_mw == pytest.approx(0.0, abs=1e-6)