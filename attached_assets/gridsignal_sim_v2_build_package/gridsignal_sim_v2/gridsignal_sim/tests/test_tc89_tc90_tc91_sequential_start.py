"""
tests/test_tc89_tc90_tc91_sequential_start.py — Sequential-start pre-condition tests.

TC-89  At most one non-standby turbine is non-OFFLINE after the first simulation
       tick of the demo-20mw scenario (first-tick snapshot).

TC-90  In any of the first 20 ticks of the demo-20mw scenario, at most one
       non-standby turbine transitions from OFFLINE to any other state in a
       single tick (full-run sequential-start assertion).

TC-91  With one non-standby turbine already SYNCHRONISED above the headroom
       threshold, at most one OFFLINE turbine transitions to non-OFFLINE per
       tick — covering the two-mechanism double-start case where both
       stage_for_predicted_step AND the headroom check can fire simultaneously.

All three describe DESIRED post-fix behaviour and FAIL with the current
N_needed+1 simultaneous-start implementation.  They form the Phase A pre-condition
gate for the ramp-algorithm replacement (DR-2026-08-06 D-05, §7.1.3 v2.6 draft).

TC-89 / TC-90 failure mode (pre-fix):
  dispatch.py — stage_for_predicted_step() computes:
      _n_start = min(max(1, ceil(delta_p/rated)+1), len(_offline))
  For the demo-20mw 3-unit fleet and a ~6.3 MW step this gives _n_start = 2.
  Both turbine-0 and turbine-1 enter RAMPING on the same tick (tick 0), violating
  the sequential-start contract.

TC-91 failure mode (pre-fix, same root cause):
  When turbine-0 is SYNCHRONISED and delta_p=5 MW is commanded:
      _n_start = min(max(1, ceil(5/7)+1), 2) = 2
  Both turbine-1 and turbine-2 start simultaneously.  After Phase D,
  stage_for_predicted_step starts exactly 1 unit; PendingStartRegister (Phase A)
  then prevents the headroom check from issuing a second start command in the
  same tick.

Phase A gate (per DR-2026-08-06 correction):
  TC-89 and TC-90 must be confirmed FAILING in the Phase A report (they are
  xfailed here so the main suite stays clean).
  TC-91 is also xfailed; report whether it fails today.
  After Phase D all three must pass.

Numbers reserved by spec:
  TC-87 = Phase B "output at interval n equals accumulated integral"
  TC-88 = Phase B "a unit promoted during advance() is not loaded in that interval"
"""
import pytest


# ── TC-89: first-tick snapshot ────────────────────────────────────────────────

@pytest.mark.xfail(
    strict=False,
    reason=(
        "Phase D sequential-start (DR-2026-08-06 D-05); "
        "dispatch still uses N_needed+1 which starts 2 units on tick 0"
    ),
)
def test_tc89_first_tick_starts_at_most_one_unit():
    """TC-89: At most one non-standby turbine is non-OFFLINE after tick 0.

    All turbines begin OFFLINE.  After exactly one tick the dispatch arbitrator
    has had one opportunity to call stage_for_predicted_step().  With the
    sequential-start contract only ONE unit may have left the OFFLINE state.

    FAILS pre-fix: turbine-0 and turbine-1 both enter RAMPING at tick 0
    (N_needed+1 = 2 for the demo-20mw 3-unit fleet and a ~6.3 MW demand step).

    PASSES post-fix (Phase D): dispatch starts exactly 1 unit per tick;
    subsequent units start in later ticks via evaluate_commitment().

    Spec refs: DR-2026-08-06 D-05; §7.1.3 sequential-start requirement.
    Previously numbered TC-87 (reserved for Phase B interval-ordering test).
    """
    from api.routes.scenarios import build_seeded_store
    from api.schemas import ScenarioSpec
    from runtime.scenario_factory import build_run_context_from_spec
    from core.models import TurbineState

    store = build_seeded_store()
    rec = store.get("demo-20mw")
    assert rec is not None, "demo-20mw scenario not found in seeded store"

    spec = ScenarioSpec.model_validate_json(rec.spec_json)
    ctx = build_run_context_from_spec("tc89-run", spec.model_dump())

    # Pre-condition: every non-standby turbine starts OFFLINE.
    active = [t for t in ctx.sim_state.turbines if not t.config.hot_standby]
    assert all(t.state == TurbineState.OFFLINE for t in active), (
        "TC-89 pre-condition: all non-standby turbines must start OFFLINE"
    )
    assert len(active) >= 2, (
        "TC-89 pre-condition: need ≥2 non-standby turbines to detect simultaneous starts"
    )

    # Run exactly one tick.
    ctx.step()

    # At most 1 unit should have left OFFLINE.
    non_offline = [t for t in active if t.state != TurbineState.OFFLINE]

    assert len(non_offline) <= 1, (
        f"TC-89 FAIL: {len(non_offline)} units left OFFLINE state on tick 0 "
        f"({[t.config.asset_id + ':' + t.state.value for t in non_offline]}). "
        f"stage_for_predicted_step() started N_needed+1 units simultaneously "
        f"instead of exactly 1. "
        f"Fix (Phase D): dispatch must start exactly one unit per tick (D-05)."
    )


# ── TC-90: full-run sequential-start assertion ────────────────────────────────

@pytest.mark.xfail(
    strict=False,
    reason=(
        "Phase D sequential-start (DR-2026-08-06 D-05); "
        "N_needed+1 causes 2 simultaneous OFFLINE→non-OFFLINE transitions on tick 0"
    ),
)
def test_tc90_at_most_one_start_transition_per_tick():
    """TC-90: At most one non-standby turbine transitions OFFLINE→non-OFFLINE
    in any single simulation tick across the first 20 ticks (0–95 s).

    Tracks per-tick state transitions for every non-standby turbine and asserts
    the maximum count of simultaneous OFFLINE→non-OFFLINE transitions is ≤ 1.
    Covers the full startup window where the N_needed+1 defect manifests.

    FAILS pre-fix: tick 0 transitions 2 units (turbine-0 and turbine-1) from
    OFFLINE to RAMPING simultaneously.

    PASSES post-fix (Phase D): no tick has more than 1 OFFLINE→non-OFFLINE
    transition; subsequent units start via evaluate_commitment().

    Spec refs: DR-2026-08-06 D-05; §7.1.3 sequential-start requirement.
    Previously numbered TC-88 (reserved for Phase B interval-ordering test).
    """
    from api.routes.scenarios import build_seeded_store
    from api.schemas import ScenarioSpec
    from runtime.scenario_factory import build_run_context_from_spec
    from core.models import TurbineState

    store = build_seeded_store()
    rec = store.get("demo-20mw")
    assert rec is not None, "demo-20mw scenario not found in seeded store"

    spec = ScenarioSpec.model_validate_json(rec.spec_json)
    ctx = build_run_context_from_spec("tc90-run", spec.model_dump())

    # Track the worst tick (most simultaneous starts).
    max_simultaneous: int = 0
    worst_tick: int = -1
    worst_detail: list[str] = []

    _N_TICKS = 20  # covers 100 s of sim time (5 s tick interval × 20)

    for tick_i in range(_N_TICKS):
        # Snapshot states BEFORE this tick.
        states_before: dict[str, str] = {
            t.config.asset_id: t.state.value
            for t in ctx.sim_state.turbines
            if not t.config.hot_standby
        }

        ctx.step()

        # Snapshot states AFTER this tick.
        states_after: dict[str, str] = {
            t.config.asset_id: t.state.value
            for t in ctx.sim_state.turbines
            if not t.config.hot_standby
        }

        # Units that transitioned OFFLINE → non-OFFLINE this tick.
        transitions = [
            aid
            for aid, state_after in states_after.items()
            if states_before.get(aid) == TurbineState.OFFLINE.value
            and state_after != TurbineState.OFFLINE.value
        ]

        if len(transitions) > max_simultaneous:
            max_simultaneous = len(transitions)
            worst_tick = tick_i
            worst_detail = [
                f"{aid}: {states_before[aid]}→{states_after[aid]}"
                for aid in transitions
            ]

    assert max_simultaneous <= 1, (
        f"TC-90 FAIL: tick {worst_tick} had {max_simultaneous} units "
        f"transition from OFFLINE simultaneously: {worst_detail}. "
        f"stage_for_predicted_step() must start at most one unit per tick (D-05). "
        f"Fix (Phase D): sequential starts via evaluate_commitment()."
    )


# ── TC-91: one unit already SYNCHRONISED ─────────────────────────────────────

@pytest.mark.xfail(
    strict=False,
    reason=(
        "Phase D + PendingStartRegister (DR-2026-08-06 D-05 §7.1.3); "
        "N_needed+1 currently starts 2 units simultaneously even with one "
        "unit already SYNCHRONISED; after Phase D, PendingStartRegister "
        "prevents the headroom check from issuing a second start command"
    ),
)
def test_tc91_at_most_one_start_when_one_unit_already_synchronised():
    """TC-91: With one unit already SYNCHRONISED above the headroom threshold,
    at most one OFFLINE turbine transitions to non-OFFLINE per tick.

    TC-89 and TC-90 start from an all-offline fleet: the headroom guard
    (_sync_rated_mw > 0) fails on tick 0, so only stage_for_predicted_step()
    fires. TC-91 covers the normal running case where _sync_rated_mw > 0 and
    BOTH mechanisms can fire in the same tick:

      1. stage_for_predicted_step() fires for a new demand step.
      2. The per-tick headroom check fires because the SYNCHRONISED unit is
         above the 80% utilisation threshold.

    With N_needed+1 and 2 offline units the failure here is the same root cause
    (stage_for_predicted_step starts 2 units at once). After Phase D, dispatch
    issues exactly 1 start; PendingStartRegister (Phase A structure, wired in
    Phase D) then prevents the headroom check from issuing a second command_start()
    in the same tick.

    Setup
    -----
    turbine-0 : forced to SYNCHRONISED at 6.0 MW (86 % of 7 MW rated)
    turbine-1 : OFFLINE
    turbine-2 : OFFLINE
    demand step: 5.0 MW (triggers stage_for_predicted_step)
    headroom: 6.0 / 7.0 = 86 % > 80 % → headroom check also fires

    FAILS pre-fix: N_needed+1 starts both turbine-1 and turbine-2 from
    stage_for_predicted_step alone (_n_start = min(max(1, ceil(5/7)+1), 2) = 2).

    PASSES post-fix (Phase D + PendingStartRegister wired).

    Spec refs: DR-2026-08-06 D-05, §7.1.3; PendingStartRegister §7.1.3 Phase A.
    """
    import math
    from core.asset_modules import TurbineModule, BessModule
    from core.models import TurbineConfig, TurbineState, BessConfig, SiteConfig, IslandMode
    from core.dispatch import DispatchArbitrator

    site = SiteConfig(
        frequency_nominal_hz=50.0,
        power_factor=0.85,
        site_id="tc91-site",
        pue_base=1.03,
        uncalibrated=False,
        island_mode=IslandMode.ISLANDED,
    )

    # 3-unit fleet: turbine-0 forced to SYNCHRONISED at 6.0 MW (86%),
    # turbines 1 and 2 start OFFLINE.
    t0 = TurbineModule(TurbineConfig(asset_id="t-0", rated_mw=7.0, r_asset_mw_per_s=0.3))
    t1 = TurbineModule(TurbineConfig(asset_id="t-1", rated_mw=7.0, r_asset_mw_per_s=0.3))
    t2 = TurbineModule(TurbineConfig(asset_id="t-2", rated_mw=7.0, r_asset_mw_per_s=0.3))
    bess = BessModule(BessConfig(asset_id="b-0", rated_mw=10.0, usable_mwh=5.0, grid_forming=False))

    # Force turbine-0 to SYNCHRONISED at 6.0 MW.
    # Direct state assignment is acceptable in unit tests that verify
    # cross-mechanism interaction at a specific fleet state.
    t0.state = TurbineState.SYNCHRONISED
    t0._current_output_mw = 6.0

    arb = DispatchArbitrator(turbines=[t0, t1, t2], bess_units=[bess], site=site)

    # Snapshot states before both mechanisms fire.
    states_before = {t.config.asset_id: t.state for t in [t0, t1, t2]}

    # ── Mechanism 1: demand step fires stage_for_predicted_step() ─────────────
    # delta = 5.0 MW; N_needed+1 with 2 offline units:
    #   _n_start = min(max(1, ceil(5/7)+1), 2) = min(max(1,2), 2) = 2
    # Both t1 and t2 start simultaneously → TC-91 FAILS pre-fix.
    arb.stage_for_predicted_step(delta_p_mw=5.0, dt_lead_seconds=30.0, sim_time=0.0)

    # ── Mechanism 2: per-tick headroom check (simulation_core.py §7.1.3) ──────
    # turbine-0 at 6.0 / 7.0 = 86 % > 80 % → headroom check fires.
    # After Phase D, stage_for_predicted_step starts exactly 1 unit;
    # PendingStartRegister prevents this check from starting a second.
    _HEADROOM_THRESHOLD = 0.80
    _sync_rated_mw = sum(
        t.config.rated_mw for t in [t0, t1, t2]
        if t.state == TurbineState.SYNCHRONISED and not t.config.hot_standby
    )
    _turbine_output = sum(t.output_mw() for t in [t0, t1, t2])
    if _sync_rated_mw > 0.0 and _turbine_output / _sync_rated_mw >= _HEADROOM_THRESHOLD:
        for ht in [t0, t1, t2]:
            if ht.state == TurbineState.OFFLINE and not ht.config.hot_standby:
                ht.stage_target(_turbine_output, 0.0)
                break

    # Count OFFLINE → non-OFFLINE transitions across both mechanisms.
    states_after = {t.config.asset_id: t.state for t in [t0, t1, t2]}
    transitions = [
        aid for aid in states_after
        if states_before[aid] == TurbineState.OFFLINE
        and states_after[aid] != TurbineState.OFFLINE
    ]

    assert len(transitions) <= 1, (
        f"TC-91 FAIL: {len(transitions)} units started in one tick: "
        f"{[f'{aid}: {states_before[aid].value}→{states_after[aid].value}' for aid in transitions]}. "
        f"PendingStartRegister (Phase A, wired in Phase D) must prevent "
        f"double-starts when one unit is already SYNCHRONISED."
    )
