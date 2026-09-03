"""Addendum I Phase 1: proportional handback and unconditional SoC floor."""

from __future__ import annotations

import pytest

from core.asset_modules import BessModule, DieselModule, TurbineModule
from core.dispatch import DispatchArbitrator, MARGIN_MULTIPLIER
from core.models import (
    BessConfig,
    DieselConfig,
    SiteConfig,
    TurbineConfig,
    TurbineState,
)


def _site() -> SiteConfig:
    return SiteConfig(
        site_id="addendum-i-phase1",
        frequency_nominal_hz=50.0,
        power_factor=0.85,
    )


def _ramp_arbitrator() -> tuple[DispatchArbitrator, BessModule, TurbineModule]:
    turbine = TurbineModule(
        TurbineConfig(
            asset_id="t-i1",
            rated_mw=20.0,
            r_asset_mw_per_s=0.7,
            p_min_stable_frac=0.0,
        ),
        state=TurbineState.SYNCHRONISED,
    )
    bess = BessModule(
        BessConfig(
            asset_id="bess-i1",
            rated_mw=20.0,
            usable_mwh=20.0,
            initial_soc_fraction=1.0,
            bess_response_tau_s=0.0,
        )
    )
    return DispatchArbitrator([turbine], [bess], _site()), bess, turbine


def _ramp_trace(target: float | None) -> list[tuple[float, float, float]]:
    arbitrator, bess, turbine = _ramp_arbitrator()
    trace = []
    for tick in range(16):
        turbine.begin_interval()
        turbine.set_output(min(10.0, tick * 0.7))
        turbine_output = turbine.output_mw()
        actual_shortfall = max(0.0, 10.0 - turbine_output)
        _, bess_output, _, _ = arbitrator.tick(
            10.0,
            1.0,
            bess_dispatch_target_mw=target,
        )
        trace.append(
            (
                turbine_output,
                actual_shortfall,
                bess_output,
            )
        )
    return trace


def test_tc_i1_targeted_handback_tracks_actual_shortfall() -> None:
    trace = _ramp_trace(10.0)
    expected_shortfall = [
        10.0,
        9.3,
        8.6,
        7.9,
        7.2,
        6.5,
        5.8,
        5.1,
        4.4,
        3.7,
        3.0,
        2.3,
        1.6,
        0.9,
        0.2,
        0.0,
    ]
    assert [row[1] for row in trace] == pytest.approx(expected_shortfall)
    assert [row[2] for row in trace] == pytest.approx(expected_shortfall)
    assert all(bess_output <= actual for _, actual, bess_output in trace)


def test_tc_i1b_no_target_path_is_unchanged() -> None:
    trace = _ramp_trace(None)
    expected_shortfall = [
        10.0,
        9.3,
        8.6,
        7.9,
        7.2,
        6.5,
        5.8,
        5.1,
        4.4,
        3.7,
        3.0,
        2.3,
        1.6,
        0.9,
        0.2,
        0.0,
    ]
    assert [row[2] for row in trace] == pytest.approx(expected_shortfall)


def _diesel(
    asset_id: str,
    start_offset_s: float | None,
    delta_t_start_s: float,
    residual_ramp_s: float,
) -> DieselModule:
    return DieselModule(
        DieselConfig(
            asset_id=asset_id,
            rated_mw=5.0,
            role="primary",
            start_offset_s=start_offset_s,
            delta_t_start_s=delta_t_start_s,
            residual_ramp_s=residual_ramp_s,
        )
    )


def test_tc_i2_single_diesel_floor_formula() -> None:
    bess = BessModule(
        BessConfig(asset_id="bess-i2", rated_mw=4.0, usable_mwh=4.0)
    )
    diesel = _diesel("diesel-i2", None, 20.0, 8.0)
    arbitrator = DispatchArbitrator([], [bess], _site(), diesel_units=[diesel])

    expected_sync_s = 0.0 + 20.0 + 8.0
    expected_floor_mwh = 2.5 * 4.0 * (expected_sync_s / 3600.0)

    assert arbitrator.diesel_worst_case_sync_s() == pytest.approx(28.0)
    assert arbitrator.soc_floor_mwh(bess) == pytest.approx(expected_floor_mwh)
    assert MARGIN_MULTIPLIER == 2.5


def test_tc_i3_staggered_diesel_floor_uses_last_unit_values() -> None:
    bess = BessModule(
        BessConfig(asset_id="bess-i3", rated_mw=10.0, usable_mwh=10.0)
    )
    fleet = [
        _diesel("diesel-i3-a", 0.0, 20.0, 8.0),
        _diesel("diesel-i3-b", 45.0, 40.0, 12.0),
    ]
    arbitrator = DispatchArbitrator([], [bess], _site(), diesel_units=fleet)

    expected_sync_s = 45.0 + 40.0 + 12.0
    expected_floor_mwh = 2.5 * 10.0 * (expected_sync_s / 3600.0)

    assert arbitrator.diesel_worst_case_sync_s() == pytest.approx(97.0)
    assert arbitrator.soc_floor_mwh(bess) == pytest.approx(expected_floor_mwh)


def test_tc_i4_discharge_is_capped_at_floor() -> None:
    bess = BessModule(
        BessConfig(
            asset_id="bess-i4",
            rated_mw=2.0,
            usable_mwh=1.0,
            initial_soc_fraction=1.0,
            bess_response_tau_s=0.0,
        )
    )
    floor_mwh = 0.25

    output_mw = bess.cover_shortfall(
        allocated_mw=2.0,
        fleet_covered=False,
        dt_seconds=3600.0,
        power_ceiling_mw=2.0,
        soc_floor_mwh=floor_mwh,
    )

    assert output_mw == pytest.approx(0.75)
    assert bess.soc_mwh == pytest.approx(floor_mwh)


def test_soc_floor_zero_preserves_existing_cover_shortfall_behavior() -> None:
    bess = BessModule(
        BessConfig(
            asset_id="bess-i-zero",
            rated_mw=2.0,
            usable_mwh=2.0,
            initial_soc_fraction=1.0,
            bess_response_tau_s=0.0,
        )
    )

    output_without_floor = bess.cover_shortfall(
        allocated_mw=1.5,
        fleet_covered=False,
        dt_seconds=3600.0,
        power_ceiling_mw=2.0,
    )

    assert output_without_floor == pytest.approx(1.5)
    assert bess.soc_mwh == pytest.approx(0.5)