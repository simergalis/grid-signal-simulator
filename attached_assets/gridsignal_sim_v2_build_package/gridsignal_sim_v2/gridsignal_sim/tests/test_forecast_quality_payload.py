"""Forecast Quality wire metadata must mirror ConfidenceEngine exactly."""

from core.dispatch import ConfidenceEngine
from core.models import ConfidenceBand, DataQualityTag, TickResult
from runtime.run_manager import InMemoryTimeseriesSink, _tick_result_to_dict


def test_confidence_widening_payload_comes_from_confidence_engine() -> None:
    """The frontend receives the one authoritative widening table per tick."""
    tick = TickResult(
        run_id="forecast-quality-payload",
        tick_index=1,
        sim_time_seconds=5.0,
        p_compute_demand_mw=1.0,
        p_cooling_demand_mw=0.1,
        p_demand_mw=1.1,
        net_demand_mw=1.1,
        turbine_output_mw=1.1,
        bess_output_mw=0.0,
        bess_soc_fraction=0.5,
        confidence=ConfidenceBand(
            point_estimate_mw=1.0,
            plus_minus_fraction=0.13,
            tags=frozenset({DataQualityTag.STALE_PROFILE}),
        ),
    )

    widening = _tick_result_to_dict(tick)["confidence_widening"]

    assert widening["base_fraction"] == ConfidenceEngine.BASE_BAND_FRACTION
    assert widening["per_tag"] == {
        tag.value: fraction
        for tag, fraction in ConfidenceEngine.WIDENING_PER_TAG.items()
    }
    assert widening["per_tag"]["stale_profile"] == 0.12
    assert widening["per_tag"]["workload_signal_stale"] == 0.20
    assert widening["per_tag"]["workload_signal_absent"] == 0.50


def test_fuel_cell_configuration_mode_preserves_null_and_real_block_zeroes() -> None:
    """Aggregate telemetry is unavailable; block fleet zero remains an observation."""
    common = dict(
        run_id="fuel-cell-configuration-mode",
        tick_index=1,
        sim_time_seconds=5.0,
        p_compute_demand_mw=1.0,
        p_cooling_demand_mw=0.0,
        p_demand_mw=1.0,
        net_demand_mw=1.0,
        turbine_output_mw=0.0,
        bess_output_mw=0.0,
        bess_soc_fraction=0.5,
        confidence=ConfidenceBand(point_estimate_mw=1.0, plus_minus_fraction=0.0),
    )
    aggregate = _tick_result_to_dict(TickResult(
        **common, fuel_cell_configuration_mode="aggregate",
    ))
    assert aggregate["fuel_cell_configuration_mode"] == "aggregate"
    for field in (
        "fuel_cell_cold_blocks", "fuel_cell_running_blocks",
        "fuel_cell_available_now_mw", "fuel_cell_requested_commit_rate_blocks_per_s",
        "fuel_cell_provenance", "fuel_cell_ride_through_status",
    ):
        assert aggregate[field] is None

    block_tick = TickResult(
        **common, fuel_cell_configuration_mode="block_addressable",
        fuel_cell_cold_blocks=0, fuel_cell_warming_blocks=0,
        fuel_cell_hot_standby_blocks=0, fuel_cell_running_blocks=0,
        fuel_cell_controlled_cooling_blocks=0, fuel_cell_available_now_mw=0.0,
        fuel_cell_available_fast_mw=0.0,
        fuel_cell_requested_commit_rate_blocks_per_s=0.0,
        fuel_cell_achieved_commit_rate_blocks_per_s=0.0,
        fuel_cell_provenance={}, fuel_cell_ride_through_trips=[],
        fuel_cell_ride_through_status=[],
    )
    block = _tick_result_to_dict(block_tick)
    assert block["fuel_cell_configuration_mode"] == "block_addressable"
    assert block["fuel_cell_running_blocks"] == 0
    assert block["fuel_cell_available_now_mw"] == 0.0
    assert block["fuel_cell_provenance"] == {}
    assert block["fuel_cell_ride_through_status"] == []

    sink = InMemoryTimeseriesSink()
    import asyncio
    asyncio.run(sink.append(TickResult(**common, fuel_cell_configuration_mode="aggregate")))
    assert asyncio.run(sink.get_tick_dicts(common["run_id"]))[0]["fuel_cell_running_blocks"] is None