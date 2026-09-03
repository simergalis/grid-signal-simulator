"""Forecast Quality wire metadata must mirror ConfidenceEngine exactly."""

from core.dispatch import ConfidenceEngine
from core.models import ConfidenceBand, DataQualityTag, TickResult
from runtime.run_manager import _tick_result_to_dict


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