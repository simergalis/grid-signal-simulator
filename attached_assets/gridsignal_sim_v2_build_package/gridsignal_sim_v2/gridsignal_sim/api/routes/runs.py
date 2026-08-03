"""
api/routes/runs.py — Run lifecycle REST endpoints.

Step 6 / v2.5 §8.1.
Step 8: removes F1 _SCENARIO_PRESETS scaffolding; adds scenario_id path that
        looks up a stored ScenarioSpec and calls build_run_context_from_spec.
Step 9: adds GET /runs/{run_id}/result and GET /runs/{run_id}/timeseries for
        the results / playback screen; propagates scenario_name and scenario_id
        into RunContext when starting via a stored scenario.

POST   /runs                        start a new run
GET    /runs                        list active run IDs
GET    /runs/{run_id}               status of one run
DELETE /runs/{run_id}               cancel a run
GET    /runs/{run_id}/result        verdict + assertion details (completed runs)
GET    /runs/{run_id}/timeseries    full tick history with gap flags (completed runs)

Restart / durability scope (Step 9):
  GET /runs/{run_id}/result and GET /runs/{run_id}/timeseries both read from
  RunManager._completed, an in-process dict populated when _drive() finishes.
  After a server restart that dict is empty, so BOTH endpoints return 404 for any
  run that completed before the restart.  They behave symmetrically — the results
  screen does not half-load (chart draws, verdict 404s); it fails uniformly.
  This is an accepted scope boundary for Step 9.  When durability is required,
  CompletedRun should be serialised to SQLite keyed by run_id (not scenario_id)
  and re-hydrated in the lifespan startup handler; that work is deferred to Step 11.

Invariants:
  - RunManager is retrieved from app.state (set once in the lifespan).
    No endpoint creates its own RunManager instance.
  - ScenarioStore is retrieved from app.state (set once in the lifespan).
    No endpoint creates its own ScenarioStore instance.
  - No SimClock construction or evaluate_tick() calls here.
    All simulation logic lives in RunContext.step() (runtime/run_manager.py).
"""

from __future__ import annotations

import asyncio
import datetime
import functools
import json
import logging
import uuid

_log = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.schemas import (
    AssertionResultResponse,
    GenerationBlock,
    RunListResponse,
    RunResultResponse,
    RunStatusResponse,
    StartRunRequest,
    StartRunResponse,
    TimeseriesResponse,
    TimeseriesRowResponse,
)
from runtime.cluster_gen import generate_cluster_forecast
from runtime.param_sampler import sample_run_parameters
from runtime.run_manager import RunManager, compute_run_cost_from_completed
from runtime.scenario_factory import build_run_context, build_run_context_from_spec
from runtime.solar_sim import generate_solar_forecast
from runtime.stressor_gen import generate_stressor_forecast
from runtime.telemetry_corruption import generate_corruption_schedule

router = APIRouter(prefix="/runs", tags=["runs"])


def _run_manager(request: Request) -> RunManager:
    """Dependency: retrieve the shared RunManager from FastAPI app state."""
    return request.app.state.run_manager


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=StartRunResponse,
    summary="Start a new simulation run",
)
async def start_run(
    body: StartRunRequest,
    request: Request,
    manager: RunManager = Depends(_run_manager),
) -> StartRunResponse:
    """Create and immediately start a new RunContext.

    Returns the assigned run_id.  The run advances autonomously via an
    asyncio task; subscribe to /ws/{run_id} for live tick data.

    Two accepted paths (Step 8 — scenario_preset removed):

    (a) scenario_id: looks up the stored ScenarioSpec and builds the
        RunContext via build_run_context_from_spec.  All fleet/workload
        parameters come from the stored spec.

    (b) job_id + node_count: direct programmatic path — calls the flat
        build_run_context kwarg interface.  Used by tests and load scripts.
    """
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    _soc_floor, _soc_ceil = 10.0, 95.0   # defaults; overridden from spec_data below

    if body.scenario_id is not None:
        scenario_store = request.app.state.scenario_store
        record = scenario_store.get(body.scenario_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario {body.scenario_id!r} not found. "
                       f"Use GET /scenarios to list available scenarios.",
            )
        scenario_store.link_run(body.scenario_id, run_id)
        spec_data = json.loads(record.spec_json)

        # ── Pre-run generation pipeline ───────────────────────────────────
        # All generators run concurrently as parallel asyncio tasks and MUST
        # complete before t=0.  No generator runs during the tick loop.
        # This preserves the reproducibility property: the tick loop replays
        # a materialised timeline, never calls a network service.

        _loop         = asyncio.get_event_loop()
        # body.end_sim_time overrides the scenario spec when the operator
        # explicitly picks a duration in the UI; None means "use the spec".
        _sim_duration = (
            float(body.end_sim_time)
            if body.end_sim_time is not None
            else float(spec_data.get("end_sim_time", 300.0))
        )
        _solar_mw     = float(spec_data.get("solar_rated_mw", 0.0))
        _steps_raw    = spec_data.get("irradiance_steps", [[0.0, 1.0]])
        _is_default_irr = (
            _solar_mw > 0.0
            and len(_steps_raw) == 1
            and abs(float(_steps_raw[0][0])) < 1e-9
            and abs(float(_steps_raw[0][1]) - 1.0) < 1e-9
        )

        # Read generator configs from the stored spec (all optional)
        _cluster_cfg    = spec_data.get("cluster_gen_config")
        _stressor_cfg   = spec_data.get("stressor_gen_config")
        _param_cfg      = spec_data.get("param_sampling_config")
        _corruption_cfg = spec_data.get("telemetry_corruption_config")

        # Operator-adjustable site / advisory params.
        # Default values come from the stored site location (PUT /api/location)
        # so an operator who switches to Tokyo sees Tokyo solar without touching
        # the scenario JSON.  Explicit spec_data keys still override.
        _stored_loc     = getattr(request.app.state, "site_location", None)
        _def_lat        = _stored_loc.lat              if _stored_loc else 32.72
        _def_lon        = _stored_loc.lon              if _stored_loc else -117.16
        # Use DST-aware offset so solar peak times are correct year-round.
        if _stored_loc:
            from api.routes.location import current_utc_offset_h as _live_offset
            _def_utc = _live_offset(_stored_loc)
        else:
            _def_utc = -8.0
        _def_name       = _stored_loc.name             if _stored_loc else "San Diego, CA"
        _def_climate    = _stored_loc.climate_hint     if _stored_loc else ""
        _def_amb_base   = _stored_loc.ambient_temp_base_c if _stored_loc else 14.0

        _site_lat       = float(spec_data.get("site_latitude",      _def_lat))
        _site_lon       = float(spec_data.get("site_longitude",     _def_lon))
        _site_utc       = float(spec_data.get("site_utc_offset_h",  _def_utc))
        _site_name      = str(  spec_data.get("site_name",          _def_name))
        _climate_hint   = str(  spec_data.get("climate_hint",       _def_climate))
        _ambient_base   = float(spec_data.get("ambient_temp_base_c",_def_amb_base))
        _soc_floor      = float(spec_data.get("soc_floor_pct",       10.0))
        _soc_ceil       = float(spec_data.get("soc_ceil_pct",        95.0))
        # SD-1: log the resolved site at run start so a timezone/location mismatch
        # is a 30-second diagnosis rather than a headscratcher.
        _log.info(
            "run start: run_id=%s site=(name=%r, lat=%.2f, utc%+.1f)",
            run_id, _site_name, _site_lat, _site_utc,
        )

        # Build a utc_now override for the solar forecast.
        #
        # Priority 1 — explicit scenario field (demo-solar-peak uses 20):
        #   solar_origin_utc_hour in spec_data → use exactly that UTC hour.
        #
        # Priority 2 — auto-noon fallback for all other solar scenarios:
        #   When the site is currently in darkness (local hour < 6 or >= 20),
        #   anchor to local solar noon so Mistral / physics fallback see midday
        #   rather than returning fraction=0 for the entire run.  Scenarios that
        #   genuinely need nighttime solar must set irradiance_steps explicitly
        #   (which bypasses generate_solar_forecast entirely via _is_default_irr).
        _utc_hour_override = spec_data.get("solar_origin_utc_hour")
        if _utc_hour_override is None and _is_default_irr:
            _now_utc = datetime.datetime.now(datetime.timezone.utc)
            _local_h = (_now_utc + datetime.timedelta(hours=_site_utc)).hour
            if not (6 <= _local_h < 20):
                # UTC hour that maps to local noon: (12 − utc_offset) mod 24.
                _utc_hour_override = int((12 - _site_utc) % 24)
                _log.info(
                    "run %s: auto-noon solar override "
                    "(local_h=%d, site UTC%+.1f) → utc_hour=%d "
                    "so solar is not silently zero at night",
                    run_id, _local_h, _site_utc, _utc_hour_override,
                )

        if _utc_hour_override is not None:
            _base = datetime.datetime.now(datetime.timezone.utc)
            _utc_now_solar: datetime.datetime | None = _base.replace(
                hour=int(_utc_hour_override),
                minute=0,
                second=0,
                microsecond=0,
                tzinfo=None,
            )
        else:
            _utc_now_solar = None

        # Build coroutines for each active generator
        async def _run_solar():
            if not _is_default_irr:
                return None
            return await _loop.run_in_executor(
                None,
                functools.partial(
                    generate_solar_forecast,
                    _sim_duration,
                    _solar_mw,
                    utc_now=_utc_now_solar,
                    site_latitude=_site_lat,
                    site_longitude=_site_lon,
                    site_utc_offset_h=_site_utc,
                    site_name=_site_name,
                    climate_hint=_climate_hint,
                    ambient_temp_base_c=_ambient_base,
                ),
            )

        async def _run_cluster():
            if _cluster_cfg is None:
                return None
            return await _loop.run_in_executor(
                None,
                functools.partial(
                    generate_cluster_forecast,
                    _sim_duration,
                    description=_cluster_cfg.get("description", "plausible weekday cluster"),
                    hardware_profile_id=_cluster_cfg.get("hardware_profile_id", "enterprise_8gpu_air"),
                    max_nodes=int(_cluster_cfg.get("max_nodes", 1900)),
                    min_nodes=int(_cluster_cfg.get("min_nodes", 200)),
                    mean_interarrival_s=float(_cluster_cfg.get("mean_interarrival_s", 60.0)),
                    mean_job_nodes=int(_cluster_cfg.get("mean_job_nodes", 200)),
                    job_node_std=float(_cluster_cfg.get("job_node_std", 80.0)),
                    min_job_nodes=int(_cluster_cfg.get("min_job_nodes", 50)),
                    mean_job_duration_s=float(_cluster_cfg.get("mean_job_duration_s", 300.0)),
                    min_job_duration_s=float(_cluster_cfg.get("min_job_duration_s", 30.0)),
                    rng_seed=_cluster_cfg.get("rng_seed"),
                    use_llm=bool(_cluster_cfg.get("use_llm", True)),
                ),
            )

        async def _run_stressor():
            if _stressor_cfg is None:
                return None
            return await _loop.run_in_executor(
                None,
                functools.partial(
                    generate_stressor_forecast,
                    _sim_duration,
                    description=_stressor_cfg.get("description", "compound stressor scenario"),
                    max_solar_mw=_solar_mw,
                    rng_seed=_stressor_cfg.get("rng_seed"),
                    n_rng_events=int(_stressor_cfg.get("n_rng_events", 3)),
                    use_llm=bool(_stressor_cfg.get("use_llm", True)),
                ),
            )

        async def _run_param_sampler():
            if _param_cfg is None:
                return None
            return await _loop.run_in_executor(
                None,
                functools.partial(
                    sample_run_parameters,
                    list(_param_cfg.get("keys", ["dt_thermal", "alpha_max", "tau"])),
                    seed=_param_cfg.get("seed"),
                    sample_plant_split=bool(_param_cfg.get("sample_plant_split", True)),
                ),
            )

        # Run all generators concurrently — they are independent of each other
        _forecast, _cluster_fc, _stressor_fc, _sampled = await asyncio.gather(
            _run_solar(),
            _run_cluster(),
            _run_stressor(),
            _run_param_sampler(),
        )

        # ── Materialise: solar irradiance + ambient ───────────────────────
        if _forecast is not None:
            spec_data["irradiance_steps"] = [[t, f] for t, f in _forecast.samples]
            if _forecast.ambient_steps:
                spec_data["ambient_steps"] = [
                    [t, db, wb] for t, db, wb in _forecast.ambient_steps
                ]

        # ── Materialise: cluster arrival events ───────────────────────────
        if _cluster_fc is not None and _cluster_fc.events:
            existing_events = list(spec_data.get("workload_events", []))
            # Merge: LLM-generated cluster events supplement (not replace) scripted ones
            existing_events.extend(_cluster_fc.events)
            existing_events.sort(key=lambda e: float(e.get("timestamp", 0)))
            spec_data["workload_events"] = existing_events

        # ── Materialise: stressor (SOLAR_STEP) events ─────────────────────
        if _stressor_fc is not None and _stressor_fc.events:
            existing_events = list(spec_data.get("workload_events", []))
            existing_events.extend(_stressor_fc.events)
            existing_events.sort(key=lambda e: float(e.get("timestamp", 0)))
            spec_data["workload_events"] = existing_events

        # ── Materialise: sampled physics parameters ────────────────────────
        if _sampled is not None and _sampled.values:
            # Only inject keys that are valid ScenarioSpec fields (skip _sampled_ prefixed ones)
            _allowed_spec_keys = {
                "dt_thermal_seconds", "plant_dt_thermal_seconds",
                "alpha_max", "plant_alpha_max",
                "tau_seconds", "plant_tau_seconds",
                "pue_base", "dt_lead_seconds",
            }
            for k, v in _sampled.values.items():
                if k in _allowed_spec_keys and v is not None:
                    spec_data[k] = v

        # ── Materialise: telemetry corruption schedule ─────────────────────
        # The schedule is generated and attached to the spec so run_manager can
        # retrieve it from RunContext after the spec is built.
        _corruption_sched = None
        if _corruption_cfg is not None:
            _n_ticks = max(1, int(_sim_duration / 5))  # TICK_INTERVAL_SIM_SECONDS = 5
            _corruption_sched = generate_corruption_schedule(
                _n_ticks,
                seed=_corruption_cfg.get("seed"),
                noise_sigma=float(_corruption_cfg.get("noise_sigma", 0.0)),
                dropout_prob=float(_corruption_cfg.get("dropout_prob", 0.0)),
                max_stale=int(_corruption_cfg.get("max_stale", 0)),
            )

        # ── Build generation block ─────────────────────────────────────────
        _generators_used = []
        if _forecast is not None:
            _generators_used.append("solar")
        if _cluster_fc is not None:
            _generators_used.append("cluster")
        if _stressor_fc is not None:
            _generators_used.append("stressor")
        if _sampled is not None:
            _generators_used.append("param_sampler")
        if _corruption_sched is not None:
            _generators_used.append("telemetry_corruption")

        _gen_block = GenerationBlock(
            seed=_param_cfg.get("seed") if _param_cfg else None,
            generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            generators_used=_generators_used,
            solar_source=_forecast.source if _forecast else "none",
            cluster_source=_cluster_fc.source if _cluster_fc else "none",
            stressor_source=_stressor_fc.source if _stressor_fc else "none",
            param_sampler_note=_sampled.to_generation_note() if _sampled else "",
            corruption_note=_corruption_sched.summary() if _corruption_sched else "",
        )
        spec_data["generation_block"] = _gen_block.model_dump()

        # Propagate the resolved duration back into spec_data so that
        # build_run_context_from_spec honours the operator's UI choice rather
        # than the scenario's stored default (which is typically 300 s).
        spec_data["end_sim_time"] = _sim_duration

        ctx = build_run_context_from_spec(
            run_id,
            spec_data,
            playback_speed=body.playback_speed,
        )
        # Step 9: propagate stable IDs so the results screen can display them.
        ctx.scenario_id = body.scenario_id
        ctx.scenario_name = record.name
        # Solar weather metadata — surfaced in the Solar PV panel via tick payload.
        if _forecast is not None:
            ctx.solar_weather    = _forecast.weather
            ctx.solar_conditions = _forecast.conditions
        # Telemetry corruption schedule — available on RunContext for the tick loop.
        if _corruption_sched is not None:
            ctx.telemetry_corruption = _corruption_sched
    else:
        # Direct programmatic path — scenario_id absent, job_id+node_count present
        # (enforced by StartRunRequest.model_validator).
        ctx = build_run_context(
            run_id,
            job_id=body.job_id,
            node_count=body.node_count,
            hardware_profile_id=body.hardware_profile_id,
            end_sim_time=body.end_sim_time if body.end_sim_time is not None else 300.0,
            playback_speed=body.playback_speed,
        )

    await manager.start_run(ctx)
    return StartRunResponse(run_id=run_id, soc_floor_pct=_soc_floor, soc_ceil_pct=_soc_ceil)


@router.get(
    "",
    response_model=RunListResponse,
    summary="List active run IDs",
)
async def list_runs(
    manager: RunManager = Depends(_run_manager),
) -> RunListResponse:
    """Return the IDs of all runs currently held by the RunManager."""
    return RunListResponse(run_ids=manager.active_run_ids())


@router.get(
    "/{run_id}/result",
    response_model=RunResultResponse,
    summary="Get verdict and assertion results for a completed run",
    responses={
        404: {"description": "Run not found or not yet started"},
        409: {"description": "Run is still active — results not yet available"},
    },
)
async def get_run_result(
    run_id: str,
    manager: RunManager = Depends(_run_manager),
) -> RunResultResponse:
    """Return the verdict and per-assertion results for a completed run.

    409 if the run is still active (verdict not yet computed).
    404 if the run_id has never been seen (or was from a previous process).

    The verdict is computed by runtime/verdict.py after the run loop exits
    and is stored in RunManager._completed.  It is also persisted to the
    Scenario ORM row via sink.finalize() for long-term durability.
    """
    # Check active first — must return 409 not 404 for in-flight runs.
    if manager.get_context(run_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run {run_id!r} is still active; results are not yet available",
        )
    completed = manager.get_completed(run_id)
    if completed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Run {run_id!r} not found. "
                "It may have been started in a previous server process "
                "or the run_id is incorrect."
            ),
        )
    v = completed.verdict
    return RunResultResponse(
        run_id=run_id,
        scenario_id=completed.scenario_id,
        scenario_name=completed.scenario_name,
        completed_at=completed.completed_at.isoformat(),
        overall=v.overall,
        tick_count=v.tick_count,
        dropped_ticks=v.dropped_ticks,
        gap_count=v.gap_count,
        assertions=[
            AssertionResultResponse(check=a.check, status=a.status, detail=a.detail)
            for a in v.assertions
        ],
    )


@router.get(
    "/{run_id}/timeseries",
    response_model=TimeseriesResponse,
    summary="Get full tick history for a completed run",
    responses={
        404: {"description": "Run not found or not yet started"},
        409: {"description": "Run is still active — timeseries not yet sealed"},
    },
)
async def get_run_timeseries(
    run_id: str,
    manager: RunManager = Depends(_run_manager),
) -> TimeseriesResponse:
    """Return the full ordered tick history for a completed run.

    Each row includes a gap_before flag: True when tick_index jumps by more
    than 1 from the previous row, indicating dropped ticks between them.
    sim_time_seconds is read from the stored value (F5 convention: interval-end
    timestamp) and is never re-derived.

    409 if the run is still active.
    404 if the run_id is unknown.
    """
    if manager.get_context(run_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run {run_id!r} is still active; timeseries is not yet sealed",
        )
    completed = manager.get_completed(run_id)
    if completed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} not found",
        )

    rows_out: list[TimeseriesRowResponse] = []
    tick_dicts = completed.tick_dicts
    for i, r in enumerate(tick_dicts):
        gap_before = i > 0 and r["tick_index"] > tick_dicts[i - 1]["tick_index"] + 1
        rows_out.append(
            TimeseriesRowResponse(
                tick_index=r["tick_index"],
                sim_time_seconds=r["sim_time_seconds"],
                p_compute_mw=r["p_compute_mw"],
                p_cooling_mw=r["p_cooling_mw"],
                p_total_mw=r["p_total_mw"],
                net_demand_mw=r["net_demand_mw"],
                turbine_output_mw=r["turbine_output_mw"],
                bess_output_mw=r["bess_output_mw"],
                bess_soc_fraction=r["bess_soc_fraction"],
                confidence_lower_mw=r["confidence_lower_mw"],
                confidence_upper_mw=r["confidence_upper_mw"],
                insufficient_reserve_alert=r["insufficient_reserve_alert"],
                p_renewable_mw=r["p_renewable_mw"],
                bess_bridging_seconds=r["bess_bridging_seconds"],
                dt_lead_next_s=r["dt_lead_next_s"],
                bridging_basis=r["bridging_basis"],
                gap_before=gap_before,
            )
        )

    return TimeseriesResponse(
        run_id=run_id,
        gap_count=completed.verdict.gap_count,
        rows=rows_out,
    )


@router.get(
    "/{run_id}",
    response_model=RunStatusResponse,
    summary="Get run status",
    responses={404: {"description": "Run not found"}},
)
async def get_run_status(
    run_id: str,
    manager: RunManager = Depends(_run_manager),
) -> RunStatusResponse:
    """Return active status for the given run_id.

    Returns 404 if the run does not exist or has already completed and
    been cleaned up by the RunManager.
    """
    ctx = manager.get_context(run_id)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} not found",
        )
    return RunStatusResponse(run_id=run_id, active=not ctx.is_complete())


@router.get(
    "/{run_id}/energy-summary",
    summary="Aggregate energy totals for the Scenario Planner (§18.5 FR-4.4)",
    responses={
        404: {"description": "Run not found"},
        409: {"description": "Run is still active — timeseries not yet sealed"},
    },
)
async def get_energy_summary(
    run_id: str,
    manager: RunManager = Depends(_run_manager),
) -> dict:
    """Compute aggregate energy totals from the completed tick timeseries.

    Used by ScenarioPlannerPage to replace stub run history with real per-run
    energy accounting (§18.5 FR-4.4 / §21.2 cost model).

    Derivation (dt = 5.0 s = TICK_INTERVAL_SIM_SECONDS):
        generation_mwh     = Σ turbine_output_mw × dt / 3600
        grid_import_mwh    = Σ max(0, net_demand − turbine − bess) × dt / 3600
        storage_charge_mwh = Σ bess_output_mw × dt / (3600 × RT_EFF)
                             (discharge / round_trip_efficiency = cost-model proxy
                              for energy put INTO the BESS; actual charge is not
                              tracked in TickResult)
    """
    if manager.get_context(run_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run {run_id!r} is still active; energy summary is not yet available.",
        )
    completed = manager.get_completed(run_id)
    if completed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} not found.",
        )

    DT_H = 5.0 / 3600.0          # one tick = 5 sim-seconds → hours
    RT_EFF = 0.88                  # §21.2 round-trip efficiency

    generation_mwh     = 0.0
    grid_import_mwh    = 0.0
    discharge_mwh      = 0.0

    for r in completed.tick_dicts:
        t = r.get("turbine_output_mw", 0.0)
        b = r.get("bess_output_mw",    0.0)
        n = r.get("net_demand_mw",     0.0)
        generation_mwh  += t * DT_H
        grid_import_mwh += max(0.0, n - t - b) * DT_H
        discharge_mwh   += b * DT_H

    storage_charge_mwh = discharge_mwh / RT_EFF if RT_EFF > 0 else discharge_mwh
    duration_hours     = len(completed.tick_dicts) * DT_H

    # ── §21.2 cost model (AB2) ────────────────────────────────────────────
    # compute_run_cost_from_completed lives in runtime/ so that api/ never
    # imports from core/ (plane separation rule).
    cost_breakdown, cost_cfg = compute_run_cost_from_completed(
        completed,
        generation_mwh     = generation_mwh,
        grid_import_mwh    = grid_import_mwh,
        storage_charge_mwh = storage_charge_mwh,
        duration_hours     = duration_hours,
    )

    return {
        "run_id":               run_id,
        "label":                completed.scenario_name or run_id,
        "duration_hours":       round(duration_hours,       4),
        "grid_import_mwh":      round(grid_import_mwh,      4),
        "generation_mwh":       round(generation_mwh,       4),
        "storage_charge_mwh":   round(storage_charge_mwh,   4),
        # §21.2 cost breakdown — CostModelEngine (Python, tested) is now the
        # authoritative implementation; ScenarioPlannerPage._computeCost is the
        # frontend rendering layer and should call this endpoint instead of
        # duplicating the formula.
        "cost_breakdown":    cost_breakdown,
        "cost_model_config": cost_cfg,
    }


@router.delete(
    "/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a run",
    responses={404: {"description": "Run not found"}},
)
async def cancel_run(
    run_id: str,
    manager: RunManager = Depends(_run_manager),
) -> None:
    """Cancel the given run and wait for its drive task to finish.

    Returns 204 on success, 404 if the run does not exist.
    """
    ctx = manager.get_context(run_id)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} not found",
        )
    await manager.cancel_run(run_id)
