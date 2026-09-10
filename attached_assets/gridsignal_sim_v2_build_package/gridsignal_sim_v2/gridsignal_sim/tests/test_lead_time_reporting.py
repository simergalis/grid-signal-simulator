"""Read-only lead-time reporting validation.

These tests cover the reporting layer independently from simulator decisions.
Synthetic tests construct persisted observation records directly; the final
test obtains observations from the already-validated Addendum H pipeline.
"""
from __future__ import annotations

import contextlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.lead_time_observations import LeadTimeObservation as CoreObservation
from runtime.lead_time_reporting import (
    CONSERVATIVE_STDDEV_MULTIPLIER,
    MIN_TRUSTED_SAMPLE_SIZE,
    report_lead_time_distribution,
    summarize_lead_time_observations,
)
from core.models import WorkloadClass
from core.sim_clock import SimClock
from core.simulation_core import evaluate_tick
from runtime.persistence import Base, LeadTimeObservation
from runtime.scenario_factory import build_run_context_from_spec


def _synthetic_observation(
    index: int,
    lead_time_seconds: float,
    *,
    hardware_profile_id: str = "synthetic-profile",
    workload_class: str = "training",
) -> LeadTimeObservation:
    return LeadTimeObservation(
        run_id=f"synthetic-run-{index}",
        site_id="synthetic-site",
        job_id=f"synthetic-job-{index}",
        hardware_profile_id=hardware_profile_id,
        workload_type=workload_class,
        start_sim_time_seconds=0.0,
        high_draw_sim_time_seconds=lead_time_seconds,
        lead_time_seconds=lead_time_seconds,
        threshold_fraction=0.95,
        created_at=datetime.now(timezone.utc),
    )


def test_below_threshold_surfaces_stats_but_marks_them_insufficient():
    observations = [
        _synthetic_observation(index, float(10 + index))
        for index in range(MIN_TRUSTED_SAMPLE_SIZE - 1)
    ]

    report = summarize_lead_time_observations(
        observations,
        hardware_profile_id="synthetic-profile",
        workload_class=WorkloadClass.TRAINING,
        module_default_ramp_seconds=120.0,
    )

    assert report.observation_count == MIN_TRUSTED_SAMPLE_SIZE - 1
    assert report.mean_lead_time_seconds == pytest.approx(24.0)
    assert report.min_lead_time_seconds == pytest.approx(10.0)
    assert report.max_lead_time_seconds == pytest.approx(38.0)
    assert report.statistics_trustworthy is False
    assert report.confidence_status == "insufficient-sample"
    assert report.module_default_ramp_seconds == pytest.approx(120.0)


def test_threshold_sample_matches_known_distribution_and_conservative_bias():
    # Deliberately chosen 30-row population: fifteen 8-second observations and
    # fifteen 12-second observations, giving mean=10 and population stddev=2.
    observations = [
        _synthetic_observation(index, 8.0 if index % 2 == 0 else 12.0)
        for index in range(MIN_TRUSTED_SAMPLE_SIZE)
    ]

    report = summarize_lead_time_observations(
        observations,
        hardware_profile_id="synthetic-profile",
        workload_class="training",
        module_default_ramp_seconds=120.0,
    )

    assert report.observation_count == MIN_TRUSTED_SAMPLE_SIZE
    assert report.mean_lead_time_seconds == pytest.approx(10.0)
    assert report.stddev_lead_time_seconds == pytest.approx(2.0)
    assert report.min_lead_time_seconds == pytest.approx(8.0)
    assert report.max_lead_time_seconds == pytest.approx(12.0)
    assert report.statistics_trustworthy is True
    assert report.confidence_status == "high-confidence"
    assert report.conservative_lead_time_seconds == pytest.approx(
        10.0 - CONSERVATIVE_STDDEV_MULTIPLIER * 2.0
    )
    assert report.conservative_lead_time_seconds < report.mean_lead_time_seconds


_SCENARIO_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "scenarios"
    / "addendum-h-lead-time-profile-validation.json"
)


@contextlib.contextmanager
def _plane_guard_active():
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _run_validated_addendum_h_once(run_number: int) -> tuple[CoreObservation, ...]:
    spec = json.loads(_SCENARIO_PATH.read_text())
    ctx = build_run_context_from_spec(
        f"lead-time-reporting-real-{run_number}",
        spec,
        playback_speed=0.0,
    )
    for signal in ctx.events:
        ctx.sim_state.apply_workload_signal(signal, ctx.dt_lead_seconds)

    observations: list[CoreObservation] = []
    sim_time = 0.0
    for tick_seq in range(1000):
        with _plane_guard_active():
            evaluate_tick(
                ctx.sim_state,
                SimClock(
                    sim_time=sim_time,
                    dt_seconds=0.1,
                    wall_stamp_utc=0.0,
                    rate=1.0,
                    tick_seq=tick_seq,
                ),
            )
        observations.extend(ctx.sim_state.lead_time_observations.drain_completed())
        if len(observations) == 2:
            return tuple(observations)
        sim_time += 0.1
    raise AssertionError("validated Addendum H scenario did not complete")


async def _create_reporting_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, session_factory


@pytest.mark.asyncio
async def test_real_addendum_h_observations_query_to_known_20_second_distribution():
    real_observations = [
        observation
        for run_number in range(MIN_TRUSTED_SAMPLE_SIZE)
        for observation in _run_validated_addendum_h_once(run_number)
        if observation.hardware_profile_id == "addendum_h_test_ramp_20s"
    ]
    assert len(real_observations) == MIN_TRUSTED_SAMPLE_SIZE
    assert all(
        not isinstance(observation, LeadTimeObservation)
        for observation in real_observations
    )

    engine, session_factory = await _create_reporting_session()
    try:
        async with session_factory() as session:
            async with session.begin():
                session.add_all(
                    LeadTimeObservation(
                        run_id=observation.run_id,
                        site_id=observation.site_id,
                        job_id=observation.job_id,
                        hardware_profile_id=observation.hardware_profile_id,
                        workload_type=observation.workload_type,
                        start_sim_time_seconds=observation.start_sim_time_seconds,
                        high_draw_sim_time_seconds=observation.high_draw_sim_time_seconds,
                        lead_time_seconds=observation.lead_time_seconds,
                        threshold_fraction=observation.threshold_fraction,
                        created_at=datetime.now(timezone.utc),
                    )
                    for observation in real_observations
                )

            report = await report_lead_time_distribution(
                session,
                hardware_profile_id="addendum_h_test_ramp_20s",
                workload_class=WorkloadClass.TRAINING,
                module_default_ramp_seconds=120.0,
            )

        assert report.observation_count == MIN_TRUSTED_SAMPLE_SIZE
        assert report.statistics_trustworthy is True
        assert report.mean_lead_time_seconds == pytest.approx(14.0, abs=1e-9)
        assert report.min_lead_time_seconds == pytest.approx(14.0, abs=1e-9)
        assert report.max_lead_time_seconds == pytest.approx(14.0, abs=1e-9)
        assert report.conservative_lead_time_seconds == pytest.approx(
            14.0, abs=1e-9
        )
        assert report.module_default_ramp_seconds == pytest.approx(120.0)
    finally:
        await engine.dispose()