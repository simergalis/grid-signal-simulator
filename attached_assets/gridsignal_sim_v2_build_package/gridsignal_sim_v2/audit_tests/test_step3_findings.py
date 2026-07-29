"""
Step 3 acceptance tests — the v2.5-era gaps found by the skeleton audit,
encoded as executable checks.

Every test in this file is expected to FAIL against the unmodified skeleton.
Build Plan v2.1 Step 3 requires each fix to demonstrate the OLD behaviour was
wrong, not merely that new tests pass.

Run from gridsignal_sim/:
    PYTHONPATH=.:../audit_tests python -m pytest ../audit_tests/test_step3_findings.py -v

Expected on the unmodified skeleton:  6 failed
Expected after Step 3:                6 passed
"""

from __future__ import annotations

import inspect
import math

import pytest

from core import simulation_core
from core.asset_modules import BessModule, CoolingModule, GPUModule, TurbineModule
from core.dispatch import DispatchArbitrator
from core.models import (
    BessConfig,
    HardwareProfile,
    SiteConfig,
    TurbineConfig,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)

SITE = SiteConfig(site_id="s1", pue_base=1.03, alpha_max=0.20,
                  tau_seconds=20.0, dt_thermal_seconds=90.0)
LIB = {"enterprise_8gpu_air": HardwareProfile("enterprise_8gpu_air", 10.2)}


def _signal(job: str, t: float, nodes: int,
            kind: WorkloadEventType = WorkloadEventType.STARTING) -> WorkloadSignal:
    return WorkloadSignal(
        event_id=f"e-{job}-{t}", job_id=job, event_type=kind, timestamp=t,
        hardware_profile_id="enterprise_8gpu_air", node_count=nodes,
        workload_class=WorkloadClass.TRAINING, site_id="s1",
    )


# ---------------------------------------------------------------------------
# C-1 — P_dispatch_required(t) = P_total(t) - P_renewable(t)   [v2.5 §7.1.1]
# ---------------------------------------------------------------------------

def test_arbitration_sizes_against_dispatch_required_not_p_total():
    """v2.5 §7.1.1: ΔP is a change in P_dispatch_required(t), not P_total(t).
    A compute step-load and a collapse in renewable output are the same event
    class to the Dispatch Arbitrator (TC-33).

    Skeleton defect: evaluate_tick() calls arbitrator.tick(p_total_mw, ...) and
    computes net_demand_mw AFTERWARDS, purely for reporting. Solar reduces a
    displayed figure and has zero effect on staging, the reserve check, or the
    insufficient-reserve alert.
    """
    params = inspect.signature(DispatchArbitrator.tick).parameters
    assert "p_dispatch_required_mw" in params or "net_demand_mw" in params, (
        "DispatchArbitrator.tick() takes p_total_mw; §7.1.1 requires it to size "
        f"against P_dispatch_required. Signature: {list(params)}"
    )

    src = inspect.getsource(simulation_core.evaluate_tick)
    assert "p_total_mw)" not in src.replace(" ", "").replace("\n", "") or \
           "dispatch_required" in src, (
        "evaluate_tick() still passes p_total_mw to arbitration; renewable "
        "output never reaches the dispatch path"
    )


# ---------------------------------------------------------------------------
# C-2 — anchor-adjusted BESS bridging   [v2.5 §7.1.2]
# ---------------------------------------------------------------------------

def test_bess_bridging_excludes_anchor_reserve():
    """v2.5 §7.1.2:
        BESS_bridging_available(t) = min(rated, usable SoC) - P_anchor_reserve

    An anchor must retain headroom in both directions to regulate against
    disturbance. Using the unadjusted figure produces a reserve check that
    passes shortly before a frequency excursion — the specific failure the
    specification exists to prevent (TC-61, TC-63).

    Skeleton defect: zero references to anchor or grid-forming anywhere in
    core/. BessConfig has no anchor field.
    """
    fields = set(BessConfig.__dataclass_fields__)
    assert {"p_anchor_reserve_mw", "grid_forming"} & fields, (
        f"BessConfig has no anchor concept; fields are {sorted(fields)}"
    )

    bess = BessModule(config=BessConfig("b1", rated_mw=8.0, usable_mwh=4.0))
    assert hasattr(bess, "bridging_available_mw"), (
        "BessModule exposes no anchor-adjusted bridging figure; the §7.2 step-4 "
        "reserve check would use rated capacity and SoC alone"
    )


def test_anchor_reserve_defaults_conservatively_nonzero():
    """v2.5 §7.1.2 / TC-63: P_anchor_reserve defaults to a conservative fraction
    of rated capacity, never to zero — because defaulting to zero silently
    reproduces the unadjusted arithmetic this constraint exists to correct."""
    fields = BessConfig.__dataclass_fields__
    assert "p_anchor_reserve_mw" in fields, "no anchor reserve field to default"
    default = fields["p_anchor_reserve_mw"].default
    assert default not in (0, 0.0, None), (
        f"P_anchor_reserve defaults to {default!r}; TC-63 requires a "
        "conservative non-zero default"
    )


# ---------------------------------------------------------------------------
# B-4 — Delta_t_lead is not simulated   [v2.5 §6.1, §2 item 1]
# ---------------------------------------------------------------------------

def test_dt_lead_is_modelled_as_a_ramp():
    """v2.5 §6.1 / §2 item 1: a job transitions to `starting` when the scheduler
    allocates nodes; GPUs reach full TDP Delta_t_lead (30-60 s) later, via
    container init, weight load, and collective warmup. That interval is the
    entire premise of the product.

    Skeleton defect: apply_signal() sets the full node count immediately and
    advance() is an explicit no-op, so compute draw steps 0 -> full TDP within a
    single tick. Delta_t_lead exists only as a scalar in the reserve arithmetic,
    never as a ramp.
    """
    gpu = GPUModule(asset_id="g1", site=SITE, hardware_library=LIB)
    gpu.apply_signal(_signal("j1", 0.0, nodes=100))

    full_tdp = 100 * 10.2 * SITE.pue_base / 1000.0
    at_start = gpu.output_mw()

    assert at_start < full_tdp * 0.5, (
        f"draw is {at_start:.4f} MW immediately at STARTING vs full TDP "
        f"{full_tdp:.4f} MW — the job reaches full draw in one tick, so there is "
        "no lead-time window during which staging happens ahead of load"
    )

    t = 0.0
    for _ in range(12):                             # 60 s at a 5 s tick
        gpu.advance(t, 5.0)
        t += 5.0
    assert math.isclose(gpu.output_mw(), full_tdp, rel_tol=1e-3), (
        f"after 60 s the ramp should have reached full TDP; got {gpu.output_mw():.4f}"
    )


# ---------------------------------------------------------------------------
# B-6/EQ-5 — alpha(t) must superpose per step-load   [v2.5 §8, §4.2, §11.1]
# ---------------------------------------------------------------------------

def test_second_step_load_produces_its_own_cooling_rise():
    """v2.5 §11.1 says concurrent jobs sum by superposition in P_compute — the
    Sigma term is per-job-instance. §4.2/§8 then apply a single scalar alpha(t)
    with a single t0 to the whole lagged term. Those are incompatible once jobs
    overlap (audit §8.2, proposed amendment PA-5).

    Skeleton behaviour: step_onset_time is set on the first non-zero compute
    sample and never reset, so the two-stage rise is correct for the FIRST
    step-load of a run and flat for every one after.

    The naive fix — resetting t0 — is worse: a single alpha with a reset t0
    multiplies the whole lagged term, so P_cooling collapses to zero for
    dt_thermal seconds and the chillers serving an already-running job switch
    off. This test asserts BOTH properties: a second rise happens, AND the first
    job's cooling never dips.
    """
    cooling = CoolingModule(asset_id="c1", site=SITE)

    t = 0.0
    while t < 400.0:                                # job A: 5 MW, settle
        cooling.record_compute_sample(t, 5.0)
        cooling.advance(t, 5.0)
        t += 5.0
    settled_a = cooling.output_mw()
    assert settled_a > 0.9, "job A cooling should have settled near alpha_max x 5 MW"

    trace: list[float] = []
    deltas: list[float] = []
    prev = settled_a
    while t < 800.0:                                # job B adds 10 MW at t=400
        cooling.record_compute_sample(t, 15.0)
        cooling.advance(t, 5.0)
        trace.append(cooling.output_mw())
        deltas.append(cooling.output_mw() - prev)
        prev = cooling.output_mw()
        t += 5.0

    # (a) A naive t0 reset would collapse job A's cooling. It must not.
    assert min(trace) >= settled_a * 0.95, (
        f"P_cooling dipped to {min(trace):.3f} MW after job B started, from a "
        f"settled {settled_a:.3f} MW — job A's cooling must not fall because a "
        "different job began (this is what a naive t0 reset does)"
    )

    # (b) Skeleton defect: with alpha already pinned at alpha_max, the second
    #     step arrives as a DISCONTINUITY when the lagged compute term jumps —
    #     +2.000 MW in one tick, against a superposed 0.442 MW. §8 is explicit
    #     that "a discontinuous step is itself physically unrealistic and would
    #     falsely alias as a second instantaneous event to the dispatch
    #     controller." tau exists precisely to prevent this.
    step_mw = SITE.alpha_max * 10.0                 # alpha_max x job B's increment
    superposed_max_tick = step_mw * (1 - math.exp(-5.0 / SITE.tau_seconds))
    assert max(deltas) < superposed_max_tick * 2.0, (
        f"P_cooling jumped {max(deltas):.3f} MW in one tick; a first-order rise "
        f"at tau={SITE.tau_seconds:.0f}s admits at most ~{superposed_max_tick:.3f} MW. "
        "The second step-load's cooling response is a discontinuous step, not a "
        "rise — exactly the aliasing §8's tau exists to prevent"
    )

    # (c) The second step must still reach the right steady state.
    assert math.isclose(trace[-1], SITE.alpha_max * 15.0, rel_tol=1e-3), (
        f"P_cooling settled at {trace[-1]:.3f} MW, expected "
        f"{SITE.alpha_max * 15.0:.3f} MW — superposition must preserve the §12 identity"
    )


# ---------------------------------------------------------------------------
# C-3 — counting unit and profile vintage   [v2.5 §5.2, §5.3]
# ---------------------------------------------------------------------------

def test_hardware_profile_carries_counting_unit_and_vintage():
    """v2.5 §5.2: every profile declares the unit node_count is expressed in.
    A site reporting dies against a profile assuming packages produces a forecast
    off by exactly 2x, with no symptom other than persistent forecast error
    (TC-53).

    v2.5 §5.3: every profile carries a vintage. Forecasting a current-generation
    cabinet against a two-generation-old profile under-predicts by 60-90 kW per
    cabinet, so ten racks silently exceed the §4.4 prediction threshold (TC-54).
    """
    fields = set(HardwareProfile.__dataclass_fields__)
    missing = {"counting_unit", "vintage_generation", "vintage_established"} - fields
    assert not missing, (
        f"HardwareProfile is missing {sorted(missing)}; fields are {sorted(fields)}"
    )


# ---------------------------------------------------------------------------
# C-4 — per-job draw attribution   [v2.5 §6.2, §11.1]
# ---------------------------------------------------------------------------

def test_checkpoint_classifier_sees_per_job_draw():
    """The classifier must see ONE job's draw trace, or a checkpoint dip in a
    small job is invisible against the site total.

    Skeleton defect: simulation_core.py sets `job_draw_mw = p_compute_mw`, the
    SITE-WIDE sum across all GPU modules — not the module's aggregate, as the
    inline comment claims.
    """
    src = inspect.getsource(simulation_core.evaluate_tick)
    assert "job_draw_mw = p_compute_mw" not in src, (
        "checkpoint classification uses site-wide p_compute_mw as a stand-in "
        "for per-job draw; a 20% dip in a 1 MW job is a 0.4% dip in a 50 MW site "
        "and will never cross the §6.2 15% threshold"
    )
