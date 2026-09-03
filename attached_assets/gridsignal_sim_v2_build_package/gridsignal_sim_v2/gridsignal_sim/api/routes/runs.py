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
GET    /runs/{run_id}/latest-tick   most recent WebSocket tick payload via REST (FLAG-3)

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
    BalanceGateResponse,
    GenerationBlock,
    RunListResponse,
    RunResultResponse,
    RunStatusResponse,
    StartRunRequest,
    StartRunResponse,
    TimeseriesResponse,
    TimeseriesRowResponse,
    SetThermalStateRequest,
    UnitCommandRequest,
)
from runtime.cluster_gen import generate_cluster_forecast
from runtime.param_sampler import sample_run_parameters
from runtime.run_manager import RunManager, compute_run_cost_from_completed
from runtime.scenario_factory import build_run_context, build_run_context_from_spec
from runtime.solar_sim import generate_solar_forecast
from runtime.stressor_gen import generate_stressor_forecast
from runtime.telemetry_corruption import generate_corruption_schedule

router = APIRouter(prefix="/runs", tags=["runs"])


async def _load_completed_from_db(run_id: str) -> "CompletedRun | None":
    """Durability fallback: reconstruct a CompletedRun from the Scenario table.

    Called when RunManager._completed has no entry for run_id, which happens
    whenever the server restarts after a run completes.  The persist_completed_hook
    (wired in api/app.py lifespan) writes the verdict JSON to the Scenario row
    when _drive() finishes, so it is available here across restarts.

    Returns None when the Scenario row doesn't exist or has no verdict (the run
    never finished or predates the durability hook).

    Tick-by-tick data (tick_dicts) is NOT available via this path — the in-memory
    sink does not persist rows to the DB.  The caller returns 410 for the
    /timeseries endpoint in that case.
    """
    import json as _json
    from runtime.persistence import Scenario as _ScenarioORM
    from runtime.verdict import AssertionResult as _AR, VerdictResult as _VR
    from runtime.run_manager import CompletedRun as _CR
    from sqlalchemy import select as _sa_select
    from api.db import _SessionLocal as _SL
    from datetime import datetime as _dt, timezone as _tz

    try:
        async with _SL() as _session:
            _result = await _session.execute(
                _sa_select(_ScenarioORM).where(_ScenarioORM.run_id == run_id)
            )
            _row = _result.scalar_one_or_none()
    except Exception:
        _log.warning("run %s: DB fallback query failed", run_id, exc_info=True)
        return None

    if _row is None or _row.verdict is None:
        return None

    try:
        _v = _json.loads(_row.verdict)
        _assertions = [
            _AR(check=a["check"], status=a["status"], detail=a["detail"])
            for a in _v.get("assertions", [])
        ]
        _verdict = _VR(
            overall=_v.get("overall", "INCONCLUSIVE"),
            tick_count=_v.get("tick_count", 0),
            dropped_ticks=_v.get("dropped_ticks", 0),
            gap_count=_v.get("gap_count", 0),
            assertions=_assertions,
        )
        _completed_at = _row.completed_at or _dt.now(_tz.utc)
        if _completed_at.tzinfo is None:
            _completed_at = _completed_at.replace(tzinfo=_tz.utc)
        return _CR(
            run_id=run_id,
            scenario_id=_row.scenario_id,
            scenario_name=_row.name or run_id,
            completed_at=_completed_at,
            verdict=_verdict,
            tick_dicts=[],        # Not persisted — timeseries endpoint returns 410
            dropped_ticks=_v.get("dropped_ticks", 0),
            # Task #428: restore run-level EDL total persisted in verdict_json.
            # None when the key is absent (pre-#428 rows) or was null (headless).
            total_edl_dispatch_cost_usd=_v.get("total_edl_dispatch_cost_usd"),
        )
    except Exception:
        _log.warning("run %s: DB fallback verdict parse failed", run_id, exc_info=True)
        return None


def _run_manager(request: Request) -> RunManager:
    """Dependency: retrieve the shared RunManager from FastAPI app state."""
    return request.app.state.run_manager


def _kube_config_from_generator(gen_cfg: dict) -> dict:
    """Translate frontend GeneratorConfig → backend kube_config dict.

    Mirrors the GPU-to-node counts from gpuGeneratorStore.ts::gpuCountForSize():
      small  → rPick([8, 16, 32, 64])  GPUs / 8 GPUs per node → mean ~3.75 nodes
      medium → rPick([128, 256, 512])  GPUs / 8               → mean ~37.3 nodes
      large  → rPick([512, 768, 1024, 2048]) / 8              → mean ~136  nodes

    The returned dict is accepted by scenario_factory.build_run_context_from_spec()
    as spec_data["kube_config"].  The factory expands it into three KubeDemandAgents
    (A/SLURM, B/K8S, C/RAY) and scales mean_interarrival_s per tenant weight.
    """
    _size_mean: dict[str, float] = {"small": 3.75, "medium": 37.3, "large": 136.0}
    _size_min:  dict[str, int]   = {"small": 1,    "medium": 16,   "large": 64}
    job_sizes = gen_cfg.get("jobSizes", {"small": 0.30, "medium": 0.50, "large": 0.20})
    total_w   = sum(job_sizes.values()) or 1.0
    mean_nodes = sum(
        job_sizes.get(s, 0.0) / total_w * _size_mean[s] for s in _size_mean
    )
    min_nodes_job = min(
        (_size_min[s] for s, w in job_sizes.items() if w > 0),
        default=1,
    )
    node_std = mean_nodes * 0.8

    dur_range  = gen_cfg.get("jobDurationRange", [60, 240])
    mean_dur_s = (dur_range[0] + dur_range[1]) / 2.0
    min_dur_s  = float(dur_range[0])

    rate         = max(float(gen_cfg.get("ratePerMinute", 2.0)), 0.1)
    mean_iat_s   = 60.0 / rate  # fleet-level; factory scales per tenant by weight

    max_jobs      = int(gen_cfg.get("maxJobsPerTenant", 12))
    max_nodes_val = max(100, int(max_jobs * mean_nodes * 2))
    min_nodes_val = max(1, min(int(max_nodes_val * 0.02), max_nodes_val - 1))

    contracts   = gen_cfg.get("tenantContracts", {"a": 1.40, "b": 1.00, "c": 0.60})
    headroom_mw = sum(float(v) for v in contracts.values()) * 1.5

    return {
        "hardware_profile_id":   "enterprise_8gpu_air",
        "max_nodes":             max_nodes_val,
        "min_nodes":             min_nodes_val,
        "mean_interarrival_s":   round(mean_iat_s, 2),
        "mean_job_nodes":        round(mean_nodes, 1),
        "job_node_std":          round(node_std, 1),
        "min_job_nodes":         min_nodes_job,
        "mean_job_duration_s":   mean_dur_s,
        "min_job_duration_s":    min_dur_s,
        "reorder_window_s":      10.0,
        "ntp_jitter_s":          2.0,
        "headroom_threshold_mw": round(headroom_mw, 2),
        "rng_seed":              42,
    }


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

        # ── Operator BESS size overrides (RunControlBar) ──────────────────
        # Apply before any generator pipelines so that the corrected sizing
        # propagates to the irradiance / forecast generators that may read
        # solar_rated_mw relative to peak load (PROTO-7).
        if body.bess_rated_mw_override is not None or body.bess_usable_mwh_override is not None:
            _bess_units = spec_data.get("bess_units", [])
            for _u in _bess_units:
                if body.bess_rated_mw_override is not None:
                    _u["rated_mw"] = body.bess_rated_mw_override
                if body.bess_usable_mwh_override is not None:
                    _u["usable_mwh"] = body.bess_usable_mwh_override
            spec_data["bess_units"] = _bess_units
            _log.info(
                "run %s: BESS override applied — rated_mw=%s usable_mwh=%s across %d unit(s)",
                run_id,
                body.bess_rated_mw_override,
                body.bess_usable_mwh_override,
                len(_bess_units),
            )

        # ── GPU Generator → kube scheduler wiring ────────────────────────
        # When the frontend GPU Generator is running the operator can connect it
        # to the backend by including generator_config_override in the POST body.
        # We synthesise a kube_config dict and merge it with any existing
        # kube_config in the spec: scenario hardware / topology fields (profile,
        # node limits, seeds) are preserved; stochastic timing / size fields
        # (interarrival, job nodes, duration, headroom) come from the operator's
        # live generator settings.
        if body.generator_config_override is not None:
            _gen_cfg = body.generator_config_override
            _synthesised_kube = _kube_config_from_generator(_gen_cfg)
            _existing_kube = spec_data.get("kube_config") or {}
            # Hardware / topology fields from the scenario take precedence so
            # existing kube scenarios keep their validated node ceilings and seeds.
            _topology_keys = {
                "hardware_profile_id", "max_nodes", "min_nodes",
                "reorder_window_s", "ntp_jitter_s", "rng_seed",
            }
            spec_data["kube_config"] = {
                **_synthesised_kube,
                **{k: v for k, v in _existing_kube.items() if k in _topology_keys},
            }
            # Persist the generator config so the post-start auto-arm path in
            # RunControlBar picks it up via selectedSpec.generator_config even for
            # scenarios that had no generator preset.
            spec_data.setdefault("generator_config", _gen_cfg)
            _log.info(
                "run %s: generator_config_override applied — "
                "rate=%.1f/min → mean_interarrival_s=%.1f mean_job_nodes=%.1f "
                "max_nodes=%d headroom_mw=%.2f",
                run_id,
                _gen_cfg.get("ratePerMinute", 2.0),
                spec_data["kube_config"]["mean_interarrival_s"],
                spec_data["kube_config"]["mean_job_nodes"],
                spec_data["kube_config"]["max_nodes"],
                spec_data["kube_config"]["headroom_threshold_mw"],
            )

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
        # Always use the process-level SiteLocation singleton (set by PUT /api/location)
        # so an operator who switches to Tokyo sees Tokyo solar without touching
        # the scenario JSON.  Explicit spec_data keys still override individual fields.
        from site_config import (
            get_site_location as _gsl,
            get_site_location_or_default as _gslod,
            SiteLocationNotConfigured as _SLNotConf,
            utc_offset_for_dt as _uoff,
        )
        # For solar-enabled scenarios, require a configured location (not the San Diego default).
        # Non-solar scenarios proceed without a configured location.
        _solar_mw_check = float(spec_data.get("solar_rated_mw", 0.0))
        try:
            _effective_loc = _gsl()
        except _SLNotConf:
            _effective_loc = _gslod()   # San Diego fallback
        # Inject into spec_data so scenario_factory can read it without a global import
        spec_data["_site_location"] = _effective_loc

        _def_lat      = _effective_loc.latitude_deg
        _def_lon      = _effective_loc.longitude_deg
        # DST-aware UTC offset for the current instant (Tier-1 darkness check).
        _now_utc_ref  = datetime.datetime.now(datetime.timezone.utc)
        _def_utc      = _uoff(_effective_loc.tz_name, _now_utc_ref)
        _def_name     = _effective_loc.site_name
        _def_climate  = _effective_loc.climate_hint
        _def_amb_base = _effective_loc.ambient_temp_base_c

        _site_lat     = float(spec_data["site_latitude"]) \
            if spec_data.get("site_latitude") is not None else _def_lat
        _site_lon     = float(spec_data["site_longitude"]) \
            if spec_data.get("site_longitude") is not None else _def_lon
        _site_utc     = float(spec_data["site_utc_offset_h"]) \
            if spec_data.get("site_utc_offset_h") is not None else _def_utc
        _site_name    = str(spec_data["site_name"]) \
            if spec_data.get("site_name") is not None else _def_name
        _climate_hint = str(  spec_data.get("climate_hint",        _def_climate))
        _ambient_base = float(spec_data.get("ambient_temp_base_c", _def_amb_base))
        _soc_floor    = float(spec_data.get("soc_floor_pct",        10.0))
        _soc_ceil     = float(spec_data.get("soc_ceil_pct",         95.0))
        # SD-1: log the resolved site at run start so a timezone/location mismatch
        # is a 30-second diagnosis rather than a headscratcher.
        _log.info(
            "run start: run_id=%s site=(name=%r, lat=%.4f, lon=%.4f, tz=%s, utc%+.2f)",
            run_id, _site_name, _site_lat, _site_lon, _effective_loc.tz_name, _site_utc,
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
            import math as _math
            _now_utc = datetime.datetime.now(datetime.timezone.utc)
            # Tier-1: use ZoneInfo for DST-correct local-hour test.
            try:
                from zoneinfo import ZoneInfo as _ZI
                _local_h = _now_utc.replace(tzinfo=datetime.timezone.utc).astimezone(
                    _ZI(_effective_loc.tz_name)
                ).hour
            except Exception:
                # Fallback to wall-clock offset if zoneinfo unavailable
                _local_h = (_now_utc + datetime.timedelta(hours=_site_utc)).hour

            # Tier-1: obvious darkness — local hour outside 06:00–20:00.
            if not (6 <= _local_h < 20):
                _utc_hour_override = int((12 - _site_utc) % 24)
                _log.info(
                    "run %s: auto-noon solar override (local_h=%d, tz=%s)"
                    " → utc_hour=%d — night, solar would be silently zero",
                    run_id, _local_h, _effective_loc.tz_name, _utc_hour_override,
                )
            else:
                # Tier-2: hour is nominally daytime but solar elevation < 10 °.
                # Use NOAA-longitude-based solar time (not wall-clock offset) for
                # an accurate elevation check — matches the physics in solar_sim.py.
                _doy     = _now_utc.timetuple().tm_yday
                _decl    = 23.45 * _math.sin(_math.radians(360 / 365 * (_doy - 81)))
                _B       = _math.radians(360 / 365 * (_doy - 81))
                _eot_min = (9.87 * _math.sin(2 * _B)
                            - 7.53 * _math.cos(_B)
                            - 1.5  * _math.sin(_B))
                _utc_h   = _now_utc.hour + _now_utc.minute / 60.0
                _solar_h = (_utc_h + _site_lon / 15.0 + _eot_min / 60.0) % 24.0
                _ha      = 15.0 * (_solar_h - 12.0)           # hour angle (°)
                _elev    = _math.degrees(_math.asin(
                    _math.sin(_math.radians(_site_lat)) * _math.sin(_math.radians(_decl))
                    + _math.cos(_math.radians(_site_lat)) * _math.cos(_math.radians(_decl))
                      * _math.cos(_math.radians(_ha))
                ))
                if _elev < 10.0:
                    _utc_hour_override = int((12 - _site_utc) % 24)
                    _log.info(
                        "run %s: auto-noon solar override (local_h=%d,"
                        " elevation=%.1f° < 10°, tz=%s) → utc_hour=%d"
                        " — low sun angle, irradiance would be ~0",
                        run_id, _local_h, _elev, _effective_loc.tz_name, _utc_hour_override,
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
                    # Preferred path: pass the full SiteLocation so physics uses
                    # longitude-based true solar time (immune to DST / tz mistakes).
                    site=_effective_loc,
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
        # Durability fallback: run completed in a previous server process.
        # The verdict was persisted to the Scenario table by the
        # persist_completed_hook wired in api/app.py lifespan.
        completed = await _load_completed_from_db(run_id)
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
    # Phase 0 (DR-2026-08-09-BALANCE): include the balance gate verdict.
    # Preserve the authority label alongside pass/fail so grid-tied residual
    # routing can never be presented as independently measured verification.
    _bg = completed.balance_gate
    _balance_gate_resp = (
        BalanceGateResponse(
            renderable=_bg.renderable,
            reason=_bg.reason,
            worst_defect_mw=_bg.worst_defect_mw,
            worst_tick_index=_bg.worst_index,
            n_violating=_bg.n_violating,
            independent=completed.balance_independent,
            verification_mode=completed.balance_verification_mode,
        )
        if _bg is not None
        else None
    )
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
        balance_gate=_balance_gate_resp,
        total_edl_dispatch_cost_usd=completed.total_edl_dispatch_cost_usd,
    )


@router.get(
    "/{run_id}/timeseries",
    response_model=TimeseriesResponse,
    summary="Get full tick history for a completed run",
    responses={
        404: {"description": "Run not found or not yet started"},
        409: {"description": "Run is still active — timeseries not yet sealed"},
        410: {"description": "Run completed before the current server process; verdict available but tick replay data is gone"},
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
        # Durability fallback: check whether this run's verdict was persisted
        # to the DB (completed before the current server process started).
        # Tick-by-tick data is held in memory only and cannot be replayed after
        # a restart — return 410 Gone with a clear explanation so the results
        # screen can degrade gracefully instead of showing a confusing 404.
        _db_completed = await _load_completed_from_db(run_id)
        if _db_completed is not None:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=(
                    f"Run {run_id!r} completed before the current server process started. "
                    "The verdict is available via GET /runs/{run_id}/result, but "
                    "tick-by-tick replay data is held in memory only and is not "
                    "available after a server restart."
                ),
            )
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
                p_compute_demand_mw=r["p_compute_mw"],
                p_cooling_demand_mw=r["p_cooling_mw"],
                p_demand_mw=r["p_total_mw"],
                net_demand_mw=r["net_demand_mw"],
                turbine_output_mw=r["turbine_output_mw"],
                bess_output_mw=r["bess_output_mw"],
                bess_soc_fraction=r["bess_soc_fraction"],
                confidence_lower_mw=r["confidence_lower_mw"],
                confidence_upper_mw=r["confidence_upper_mw"],
                insufficient_reserve_alert=r["insufficient_reserve_alert"],
                bess_escalation_active=r.get("bess_escalation_active", False),
                bess_escalation_reason=r.get("bess_escalation_reason", ""),
                bess_bridging_available_mw=r.get("bess_bridging_available_mw", 0.0),
                bess_bridging_floor_mw=r.get("bess_bridging_floor_mw", 0.0),
                bess_material_discharge_threshold_mw=r.get("bess_material_discharge_threshold_mw", 0.0),
                bess_discharge_sustained_s=r.get("bess_discharge_sustained_s", 0.0),
                turbine_observed_ramp_mw_per_s=r.get("turbine_observed_ramp_mw_per_s", 0.0),
                turbine_estimated_time_to_close_s=r.get("turbine_estimated_time_to_close_s"),
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
    "/{run_id}/latest-tick",
    summary="Latest broadcast tick payload for an active run (FLAG-3 REST polling)",
    responses={
        200: {"description": "Most recent tick payload — same shape as the WebSocket broadcast"},
        202: {"description": "Run is active but no tick has been broadcast yet; retry shortly"},
        404: {"description": "run_id not found (unknown or predates current server process)"},
        409: {"description": "Run completed but tick history is unavailable after server restart"},
    },
)
async def get_latest_tick(
    run_id: str,
    request: Request,
    manager: RunManager = Depends(_run_manager),
) -> dict:
    """Return the most recently broadcast tick payload for *run_id*.

    This endpoint closes the monitoring gap identified as FLAG-3: the WebSocket
    tick stream carries all critical energy variables (p_generation_mw,
    p_demand_mw, d4_balance_defect_mw, bess_output_mw, soc_pct, fuel_cell_output_mw,
    grid_exchange_mw, bess_bridging_seconds, insufficient_reserve_alert …) but no
    REST endpoint existed for server-side tooling to read them without a WebSocket.

    Response payload is the verbatim dict broadcast over the WebSocket (same keys,
    same types), plus the ``t_emit_ns`` monotonic-clock stamp from the server.
    Suitable for polling: call every 5–10 s (one or two tick intervals) to track
    the latest physics state from monitoring scripts, CI health-checks, or ops
    dashboards.

    Active run  → returns the cached payload from the most recent broadcast.
    Completed run → returns the final tick from CompletedRun.tick_dicts (in-memory).
    Completed + restarted server → 409 Gone (tick history unavailable after restart).
    Unknown run_id → 404.
    """
    from fastapi.responses import JSONResponse

    hub = request.app.state.ws_hub
    ctx = manager.get_context(run_id)

    if ctx is not None:
        # Active run — serve from hub's latest-tick cache.
        payload = hub.get_latest_tick(run_id)
        if payload is None:
            # Run has started but the drive loop hasn't broadcast the first tick yet.
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "detail": (
                        f"Run {run_id!r} is active but no tick has been broadcast yet. "
                        "Retry in 5 seconds."
                    )
                },
            )
        return payload

    # Run is not active — check completed store.
    completed = manager.get_completed(run_id)
    if completed is None:
        # Durability fallback: try the DB (verdict only; tick_dicts not persisted).
        _db_completed = await _load_completed_from_db(run_id)
        if _db_completed is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Run {run_id!r} completed before the current server process started. "
                    "Tick-by-tick data is held in memory only and is not available after "
                    "a server restart.  The verdict is available via "
                    "GET /runs/{run_id}/result."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Run {run_id!r} not found. "
                "It may have been started in a previous server process "
                "or the run_id is incorrect."
            ),
        )

    # Completed run, tick history in memory — return the final tick dict.
    if not completed.tick_dicts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} completed but recorded no ticks.",
        )
    return completed.tick_dicts[-1]


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
    return RunStatusResponse(run_id=run_id, active=not ctx.is_complete(), paused=ctx.paused)


@router.post(
    "/{run_id}/pause",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Pause a running simulation",
    responses={
        404: {"description": "Run not found or already complete"},
        409: {"description": "Run is not currently active"},
    },
)
async def pause_run(
    run_id: str,
    manager: RunManager = Depends(_run_manager),
) -> None:
    """Suspend the tick loop between ticks.

    The simulated clock is frozen at its current value; no ticks are processed
    and no timers advance while the run is paused.  The run can be resumed via
    POST /runs/{id}/resume or ended via DELETE /runs/{id}.

    PAUSE and STOP (DELETE) are distinct operations:
      · PAUSE preserves all in-flight state for resume.
      · STOP (cancel_run) discards all state; a fresh START begins a new run.
    """
    ok = manager.pause_run(run_id)
    if not ok:
        ctx = manager.get_context(run_id)
        if ctx is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run {run_id!r} not found or already complete",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run {run_id!r} is not active",
        )


@router.post(
    "/{run_id}/resume",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Resume a paused simulation",
    responses={
        404: {"description": "Run not found or already complete"},
    },
)
async def resume_run(
    run_id: str,
    manager: RunManager = Depends(_run_manager),
) -> None:
    """Resume a paused simulation from the exact simulated-clock instant it was paused.

    No sim-time is gained or lost: in-flight timers resume with their remaining
    duration intact (TC-PAUSE timer invariant).
    """
    ok = manager.resume_run(run_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} not found or already complete",
        )


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


@router.post(
    "/{run_id}/units/{unit_id}/command",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Issue an operator unit command (trip or start)",
    responses={
        404: {"description": "Run or unit not found"},
        409: {"description": "Command not valid for current unit state"},
    },
)
async def unit_command(
    run_id: str,
    unit_id: str,
    body: UnitCommandRequest,
    manager: RunManager = Depends(_run_manager),
) -> dict:
    """Issue a manual trip or start command for a specific turbine unit.

    trip  — force an on-bus unit to OFFLINE immediately; for an OFFLINE
            hot-standby unit, release standby and begin synchronization.
    start — enter start sequence from OFFLINE; ramps to SYNCHRONISED naturally
            over subsequent ticks.  Only valid from OFFLINE state.

    Returns 202 { queued: true } on success.
    Returns 404 if the run is not active or unit_id is not in the fleet.
    Returns 409 if the action is not valid for the unit's current state.
    """
    # Validate + enqueue via RunManager.  All core/ type checks happen inside
    # RunManager (runtime/ → core/ is allowed); api/ never imports from core/.
    result_code, detail = manager.validate_and_enqueue_unit_command(
        run_id, unit_id, body.action
    )

    if result_code == manager.UNIT_CMD_RUN_404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if result_code == manager.UNIT_CMD_UNIT_404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if result_code == manager.UNIT_CMD_BAD_STATE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    _log.info(
        "operator command queued: run=%s unit=%s action=%s",
        run_id, unit_id, body.action,
    )
    return {"queued": True, "unit_id": unit_id, "action": body.action}


@router.post(
    "/{run_id}/units/{unit_id}/thermal-state",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Set thermal standby classification of an offline turbine unit",
    responses={
        404: {"description": "Run or unit not found"},
        409: {"description": "Unit is not offline or is a hot-standby unit"},
    },
)
async def set_thermal_state(
    run_id:  str,
    unit_id: str,
    body:    SetThermalStateRequest,
    manager: RunManager = Depends(_run_manager),
) -> dict:
    """Override the thermal standby classification (cold / warm / hot) of an
    OFFLINE turbine unit.

    The new tier is used immediately by the next command_start() call to
    select the correct start-sequence duration.  The change is reflected
    in the thermal_state field on TurbineUnitSpec in the very next tick
    broadcast.

    Returns 202 { thermal_state: "<tier>" } on success.
    Returns 404 if the run is not active or the unit is not in the fleet.
    Returns 409 if the unit is not OFFLINE, or if it is a hot-standby unit
    (hot_standby=True) that is managed automatically by the dispatch
    arbitrator.
    """
    result_code, detail = manager.set_unit_thermal_state(
        run_id, unit_id, body.thermal_state
    )

    if result_code == manager.UNIT_CMD_RUN_404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if result_code == manager.UNIT_CMD_UNIT_404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if result_code == manager.UNIT_CMD_BAD_STATE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    return {"unit_id": unit_id, "thermal_state": body.thermal_state}


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
