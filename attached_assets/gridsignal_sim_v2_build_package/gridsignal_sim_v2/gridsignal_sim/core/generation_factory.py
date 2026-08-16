"""
core/generation_factory.py — Workload floor helpers.

Reads scenario JSON and constructs the compute_floor_mw value from the
``workload_floor_fraction`` field and the declared peak compute load.

Used by runtime/scenario_factory.py to wire compute_floor_mw onto
SimulationState so evaluate_tick() can enforce the minimum load throughout
the run.

Phase 11.4: the floor raises the effective minimum GPU draw for the Forecast
Quality panel, ensuring the actual-vs-forecast gap is visible throughout a
run (not only during ramp-up).

Peak derivation
---------------
The peak compute load is derived from the actual maximum *concurrent* active
node total, not the largest single STARTING event.  Many demo scenarios ramp
by starting multiple jobs — e.g. demo-islanded-ramp adds job-base (800 nodes)
then 26 × 200-node jobs that overlap in time.  Scanning only the largest
STARTING event (800) would drastically underestimate the 6 000-node peak.

Algorithm: replay the event timeline in timestamp order; maintain a
``{job_id: (nodes, hw_id)}`` dictionary of currently-active jobs; update it
on STARTING / JOB_END / CANCELLED / SCALE; recompute the total MW after each
event and keep the running maximum.

PUE
---
Each scenario JSON may declare ``site_config.pue_base``; this is the same
multiplier that asset_modules.GPUModule uses at runtime (``nodes × rated_kw ×
pue_base / 1000``).  Using the scenario's own PUE avoids the mismatch that
would occur if a scenario declares PUE 1.35 while the factory hardcodes 1.03.

Hardware profile kW
-------------------
Each workload event may declare a different hardware_profile_id.  The factory
uses a lightweight copy of the DEFAULT_HARDWARE_LIBRARY catalogue rather than
importing core.models, so core/ stays free of circular dependencies.
"""
from __future__ import annotations

# ── Physical defaults (mirror core/models.py DEFAULT_HARDWARE_LIBRARY) ──────
_DEFAULT_PUE: float = 1.03      # SiteConfig.pue_base default

# Lightweight copy of the DEFAULT_HARDWARE_LIBRARY rated_kw entries.
# Extend this dict when new hardware profiles are added to core/models.py.
_HW_KW: dict[str, float] = {
    "enterprise_8gpu_air": 10.2,
    "nextgen_rack_liquid": 126.0,
}
_FALLBACK_KW: float = 12.0      # GENERIC_FALLBACK_PROFILE rated_kw

# GPU TDP for tenant events (H100 SXM5, MW per GPU)
_GPU_TDP_MW: float = 0.0007


# ── PUE extraction ───────────────────────────────────────────────────────────

def _pue(spec_data: dict) -> float:
    """Read pue_base from the top-level ScenarioSpec field, defaulting to 1.03.

    ScenarioSpec serialises pue_base as a top-level key (not nested under
    site_config); build_run_context_from_spec() reads it the same way:
        site = SiteConfig(pue_base=spec_data.get("pue_base", 1.03), ...)
    Using the same key ensures the floor is computed with the same PUE that
    the runtime actually applies when multiplying node draws.
    """
    return float(spec_data.get("pue_base", _DEFAULT_PUE))


# ── Hardware profile kW ──────────────────────────────────────────────────────

def _hw_kw(hw_id: str) -> float:
    """Return rated kW for a hardware profile, falling back to 12.0."""
    return _HW_KW.get(hw_id, _FALLBACK_KW)


# ── Peak-compute estimation ─────────────────────────────────────────────────

def _peak_from_workload_events(spec_data: dict) -> float:
    """Estimate peak compute MW from scripted workload events.

    Replays the event timeline in timestamp order and tracks every active job
    concurrently, computing the maximum total draw (MW) over the entire
    timeline.  This is the same calculation the runtime performs, so the floor
    will be correct even for ramp scenarios that accumulate many overlapping
    jobs.

    SCALE cohort semantics mirror the GPUModule runtime:
    - STARTING creates the first cohort for the job with (nodes, hw_id).
    - SCALE-UP (new_total > current_total): a NEW cohort is appended with the
      delta nodes using the SCALE event's hardware_profile_id (which may differ
      from the original job's profile — e.g. upgrading to a higher-kW profile
      for burst capacity).  The existing cohorts keep their original hw_ids.
    - SCALE-DOWN (new_total < current_total): the delta is removed from the
      newest cohorts first (matching the runtime's youngest-first eviction).
    - JOB_END / CANCELLED: all cohorts for that job are removed.

    Falls back to kube_config.max_nodes for scenarios that drive load through
    the KubeDemandAgent rather than scripted events.
    """
    evts = spec_data.get("workload_events", [])
    pue = _pue(spec_data)
    # Default hardware profile for the scenario (used when an event omits it)
    default_hw_id = str(spec_data.get("hardware_profile_id") or "enterprise_8gpu_air")

    # Build a sorted list of relevant events
    timeline: list[tuple[float, str, str, int, str]] = []
    for e in evts:
        et = str(e.get("event_type", "")).lower()
        if et in ("starting", "job_end", "cancelled", "scale"):
            timeline.append((
                float(e.get("timestamp", 0.0)),
                et,
                str(e.get("job_id") or ""),
                int(e.get("node_count", 0)),
                str(e.get("hardware_profile_id") or default_hw_id),
            ))
    timeline.sort(key=lambda x: x[0])

    # Replay the timeline.
    #
    # job_cohorts maps job_id → list of [nodes, hw_id] in insertion order
    # (oldest cohort first, newest last).  SCALE-DOWN removes from the newest.
    # job_desired maps job_id → authoritative total desired node count so SCALE
    # deltas are computed correctly even after multiple consecutive scales.
    job_cohorts: dict[str, list[list]] = {}   # list[list] so we can mutate nodes in-place
    job_desired: dict[str, int] = {}
    max_mw: float = 0.0

    def _total_mw() -> float:
        """Recompute total concurrent MW across all active cohorts."""
        return sum(
            n * _hw_kw(hw) * pue / 1000.0
            for cohorts in job_cohorts.values()
            for n, hw in cohorts
            if n > 0
        )

    for _ts, et, jid, nc, hw_id in timeline:
        if et == "starting":
            job_cohorts[jid] = [[nc, hw_id]]
            job_desired[jid] = nc
        elif et in ("job_end", "cancelled"):
            job_cohorts.pop(jid, None)
            job_desired.pop(jid, None)
        elif et == "scale":
            if jid not in job_cohorts:
                # SCALE without a prior STARTING event.  GPUModule.apply_signal()
                # supports this "already-running injection" path by creating a live
                # base cohort at nc nodes using the SCALE event's hardware profile.
                # Mirror that behaviour here so the peak reflects the full node count.
                job_cohorts[jid] = [[nc, hw_id]]
                job_desired[jid] = nc
            else:
                old_total = job_desired.get(jid, 0)
                delta = nc - old_total
                job_desired[jid] = nc
                if delta > 0:
                    # Scale-UP: new cohort with the SCALE event's hardware profile
                    job_cohorts[jid].append([delta, hw_id])
                elif delta < 0:
                    # Scale-DOWN: remove from newest cohorts first
                    remaining = -delta
                    for cohort in reversed(job_cohorts[jid]):
                        if remaining <= 0:
                            break
                        reduction = min(cohort[0], remaining)
                        cohort[0] -= reduction
                        remaining -= reduction
                    # Prune zero-node cohorts (fully removed)
                    job_cohorts[jid] = [c for c in job_cohorts[jid] if c[0] > 0]
                    if not job_cohorts[jid]:
                        job_cohorts.pop(jid, None)
                        job_desired.pop(jid, None)

        mw = _total_mw()
        if mw > max_mw:
            max_mw = mw

    # KubeAgent path: kube_config.max_nodes caps the cluster; use it as an
    # additional peak candidate when scripted events don't cover the full range.
    kc = spec_data.get("kube_config") or {}
    max_kube_nodes = int(kc.get("max_nodes", 0))
    if max_kube_nodes > 0:
        kube_hw_id = default_hw_id
        kube_peak_mw = max_kube_nodes * _hw_kw(kube_hw_id) * pue / 1000.0
        if kube_peak_mw > max_mw:
            max_mw = kube_peak_mw

    return max_mw


def _peak_from_tenant_events(spec_data: dict) -> float:
    """Estimate peak compute MW from tenant GPU burst events.

    Replays each event's ``[t_start, t_start + duration_s)`` interval using a
    sweep-line algorithm and returns the maximum simultaneous GPU TDP.  This
    correctly handles non-overlapping schedules (where the naive sum would be a
    major over-estimate) and overlapping ones.

    Tenant draws use raw GPU TDP without PUE scaling (the PUE overhead is
    included in the simulation's cooling term separately).

    Only events with ``gpus > 0`` and finite ``duration_s > 0`` are included.
    """
    evts = spec_data.get("tenant_events", [])
    if not evts:
        return 0.0

    # Build a sweep-line point list: each event contributes a +gpus point at
    # t_start and a -gpus point at t_start + duration_s.
    points: list[tuple[float, int]] = []
    for e in evts:
        gpus = int(e.get("gpus", 0))
        t_start = float(e.get("t_start", 0.0))
        dur = float(e.get("duration_s", 0.0))
        if gpus <= 0 or dur <= 0.0:
            continue
        points.append((t_start, +gpus))
        points.append((t_start + dur, -gpus))

    if not points:
        return 0.0

    # Sort by time; use negative delta as secondary key so ends (-) come before
    # starts (+) at the same timestamp, matching the half-open [t_start, t_end)
    # semantics: a job that ends exactly when another starts does not overlap.
    points.sort(key=lambda x: (x[0], x[1]))

    running: int = 0
    peak_gpus: int = 0
    for _t, delta in points:
        running += delta
        if running > peak_gpus:
            peak_gpus = running

    return peak_gpus * _GPU_TDP_MW


def peak_compute_mw(spec_data: dict) -> float:
    """True peak combined compute draw (MW) across all load sources.

    evaluate_tick() adds workload-event load and tenant-event load together each
    tick.  The true peak is NOT simply the sum of each source's individual maximum
    — their peaks may occur at different times.

    Algorithm
    ---------
    1.  Collect all change-points from every source on a unified timeline:
          • workload_events — per-event cohort transitions
          • tenant_events   — interval endpoints [t_start, t_start + duration_s)
          • kube_config.max_nodes — treated as a synthetic STARTING at t=0 so
            kube capacity participates in the same timeline as tenant events
            (evaluate_tick() adds both, so they must be combined here too)
    2.  Group change-points by timestamp and apply the entire group atomically
        before sampling the combined draw once.  This prevents transient peaks
        from same-timestamp handoffs (e.g. a JOB_END and a STARTING at t=T
        are applied together; the combined draw is sampled once after both).
    3.  Return the maximum combined draw seen across all change-point groups.

    Within each timestamp group the apply order is:
      a. Tenant ends (negative delta)  — preserving [t_start, t_end) semantics
      b. Workload transitions (any)    — order within the group is input order
      c. Tenant starts (positive delta)
    """
    pue = _pue(spec_data)
    default_hw_id = str(spec_data.get("hardware_profile_id") or "enterprise_8gpu_air")

    # ── Build unified change-point list ──────────────────────────────────────
    # Each entry is (timestamp, priority, event_payload)
    # priority 0 = tenant end, 1 = workload event, 2 = tenant start
    # (applied within each timestamp group in that order)
    events: list[tuple[float, int, tuple]] = []

    for e in spec_data.get("workload_events", []):
        et = str(e.get("event_type", "")).lower()
        if et in ("starting", "job_end", "cancelled", "scale"):
            events.append((
                float(e.get("timestamp", 0.0)),
                1,  # workload
                ("W", et,
                 str(e.get("job_id") or ""),
                 int(e.get("node_count", 0)),
                 str(e.get("hardware_profile_id") or default_hw_id)),
            ))

    for e in spec_data.get("tenant_events", []):
        gpus = int(e.get("gpus", 0))
        t_start = float(e.get("t_start", 0.0))
        dur = float(e.get("duration_s", 0.0))
        if gpus > 0 and dur > 0:
            # Tenant interval [t_start, t_start + dur):
            # Priority 2 (start): applied after workload events and tenant ends at same ts.
            # Priority 0 (end):   applied first at t_start + dur, before any new starts
            #                     at the same timestamp — preserving half-open semantics.
            events.append((t_start,       2, ("T", +gpus)))
            events.append((t_start + dur, 0, ("T", -gpus)))

    # kube_config.max_nodes: a static capacity that evaluate_tick() adds to
    # tenant events.  Model it as a synthetic STARTING at t=0 so it participates
    # in the same unified timeline, allowing kube + tenant peaks to accumulate.
    kc = spec_data.get("kube_config") or {}
    max_kube_nodes = int(kc.get("max_nodes", 0))
    if max_kube_nodes > 0:
        events.append((
            0.0, 1,
            ("W", "starting", "__kube__", max_kube_nodes, default_hw_id),
        ))

    if not events:
        return 0.0

    events.sort(key=lambda x: (x[0], x[1]))

    # ── Apply atomically per timestamp group, sample once per group ──────────
    job_cohorts: dict[str, list[list]] = {}
    job_desired: dict[str, int] = {}
    active_gpus: int = 0
    max_mw: float = 0.0

    def _combined_mw() -> float:
        wl = sum(
            n * _hw_kw(hw) * pue / 1000.0
            for cohorts in job_cohorts.values()
            for n, hw in cohorts
            if n > 0
        )
        return wl + active_gpus * _GPU_TDP_MW

    def _apply(payload: tuple) -> None:
        nonlocal active_gpus
        kind = payload[0]
        if kind == "W":
            _, et, jid, nc, hw_id = payload
            if et == "starting":
                job_cohorts[jid] = [[nc, hw_id]]
                job_desired[jid] = nc
            elif et in ("job_end", "cancelled"):
                job_cohorts.pop(jid, None)
                job_desired.pop(jid, None)
            elif et == "scale":
                if jid not in job_cohorts:
                    # SCALE without prior STARTING — mirrors GPUModule already-running path.
                    job_cohorts[jid] = [[nc, hw_id]]
                    job_desired[jid] = nc
                else:
                    old_total = job_desired.get(jid, 0)
                    delta = nc - old_total
                    job_desired[jid] = nc
                    if delta > 0:
                        job_cohorts[jid].append([delta, hw_id])
                    elif delta < 0:
                        remaining = -delta
                        for cohort in reversed(job_cohorts[jid]):
                            if remaining <= 0:
                                break
                            reduction = min(cohort[0], remaining)
                            cohort[0] -= reduction
                            remaining -= reduction
                        job_cohorts[jid] = [c for c in job_cohorts[jid] if c[0] > 0]
                        if not job_cohorts[jid]:
                            job_cohorts.pop(jid, None)
                            job_desired.pop(jid, None)
        elif kind == "T":
            active_gpus += payload[1]

    # Group by timestamp (already sorted; iterate groups via groupby logic)
    i = 0
    n = len(events)
    while i < n:
        ts = events[i][0]
        # Apply all events at this timestamp
        j = i
        while j < n and events[j][0] == ts:
            _apply(events[j][2])
            j += 1
        # Sample once after the full group is applied
        mw = _combined_mw()
        if mw > max_mw:
            max_mw = mw
        i = j

    return max_mw


def compute_floor_mw(spec_data: dict) -> float:
    """Compute the absolute floor (MW) from workload_floor_fraction × peak.

    Returns 0.0 when ``workload_floor_fraction`` is absent or None, so the
    floor is never applied to scenarios that do not set the field (backward-
    compatible with all pre-existing scenarios and tests).

    Args:
        spec_data: Scenario spec dictionary (JSON-decoded ScenarioSpec).

    Returns:
        Minimum compute_load_mw to enforce throughout the run (MW).
    """
    fraction = spec_data.get("workload_floor_fraction")
    if fraction is None:
        return 0.0
    fraction = float(fraction)
    if fraction <= 0.0:
        return 0.0
    peak = peak_compute_mw(spec_data)
    if peak <= 0.0:
        return 0.0
    return fraction * peak
