"""Focused coverage for the checkpointable Addendum H Phase 2b-2 runner."""

from types import SimpleNamespace

import pytest


def test_tc152_seven_day_reference_offsets_have_weekday_and_weekend_shape() -> None:
    from runtime.phase2b_reference import _cluster_offsets

    offsets = _cluster_offsets(7)
    assert len(offsets) == 36
    assert [hour / 3600.0 for _, hour in offsets[:6]] == [8, 10, 12, 14, 16, 18]
    assert [hour / 3600.0 % 24 for _, hour in offsets[-3:]] == [8, 12, 16]
    assert offsets[29][0] == 30
    assert offsets[30][0] == 31


def test_tc153_daily_breakdown_uses_end_of_day_fuel_snapshots() -> None:
    from scripts.run_phase2b_stage2 import _daily_breakdown

    def tick(
        sim_time: float,
        *,
        load_fuel: float,
        soc: float,
        unserved: float = 0.0,
        curtailed: float = 0.0,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            sim_time_seconds=sim_time,
            p_unserved_mw=unserved,
            p_dispatch_curtailed_mw=curtailed,
            bess_soc_fraction=soc,
            turbine_fuel_telemetry=[
                {
                    "load_fuel_mmbtu": load_fuel,
                    "no_load_fuel_mmbtu": 0.0,
                    "hot_standby_fuel_mmbtu": 0.0,
                    "start_fuel_mmbtu": 0.0,
                }
            ],
        )

    ticks = [
        tick(5.0, load_fuel=1.0, soc=0.90),
        tick(10.0, load_fuel=4.0, soc=0.80, unserved=2.0, curtailed=3.0),
        tick(86405.0, load_fuel=6.0, soc=0.70),
    ]
    starts = [
        {"unit_id": "gt-1", "source": "core", "sim_time_s": 5.0},
        {"unit_id": "gt-1", "source": "core", "sim_time_s": 86405.0},
    ]
    stops = [{"unit_id": "gt-1", "source": "core", "sim_time_s": 10.0}]

    daily = _daily_breakdown(ticks, starts=starts, stops=stops)

    assert daily[0]["fuel_mmbtu"] == pytest.approx(4.0)
    assert daily[0]["unserved_mwh"] == pytest.approx(2.0 * 5.0 / 3600.0)
    assert daily[0]["curtailed_mwh"] == pytest.approx(3.0 * 5.0 / 3600.0)
    assert daily[0]["bess_soc_end"] == pytest.approx(0.80)
    assert daily[0]["start_count"] == 1
    assert daily[0]["stop_count"] == 1
    assert daily[1]["fuel_mmbtu"] == pytest.approx(2.0)
    assert daily[1]["bess_soc_end"] == pytest.approx(0.70)
    assert daily[1]["start_count"] == 1


def test_tc154_forecast_history_retains_only_a_bounded_recent_window() -> None:
    from runtime.turbine_commitment import ForecastDrivenTurbineController

    controller = ForecastDrivenTurbineController(mode="informed")
    measured_history: list[tuple[float, float]] = []
    for sim_time in (0.0, 5.0, 10.0, 15.0):
        measured_history.append((sim_time, 10.0))
        controller.forecast(
            sim_time_s=sim_time,
            events=[],
            measured_history=measured_history,
            power_for_event=lambda _event: 0.0,
        )

    assert len(controller.forecast_history) == 2
    assert controller.forecast_history[-1].sim_time_s == pytest.approx(15.0)