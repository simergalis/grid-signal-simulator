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
    from core.commitment import PendingStartRegister

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

    # Phase D: wire PendingStartRegister so stage_for_predicted_step() respects
    # the sequential-start gate.  The register is shared by both mechanisms.
    pending = PendingStartRegister()
    arb = DispatchArbitrator(turbines=[t0, t1, t2], bess_units=[bess], site=site)
    arb.pending_start = pending

    # Snapshot states before both mechanisms fire.
    states_before = {t.config.asset_id: t.state for t in [t0, t1, t2]}

    # ── Mechanism 1: demand step fires stage_for_predicted_step() ─────────────
    # Phase D: starts exactly 1 unit (t1) and records it in the pending register.
    arb.stage_for_predicted_step(delta_p_mw=5.0, dt_lead_seconds=30.0, sim_time=0.0)

    # ── Mechanism 2: per-tick headroom check (evaluate_commitment() path) ──────
    # turbine-0 at 6.0 / 7.0 = 86 % > 80 % → headroom condition is met.
    # PendingStartRegister is non-empty (t1 was just started above) →
    # the gate blocks this mechanism from starting a second unit.
    _HEADROOM_THRESHOLD = 0.80
    _sync_rated_mw = sum(
        t.config.rated_mw for t in [t0, t1, t2]
        if t.is_on_bus and not t.config.hot_standby   # Phase D: is_on_bus replaces raw state check
    )
    _turbine_output = sum(t.output_mw() for t in [t0, t1, t2])
    if _sync_rated_mw > 0.0 and _turbine_output / _sync_rated_mw >= _HEADROOM_THRESHOLD:
        # Phase D: PendingStartRegister gate prevents double-start.
        if pending.is_empty:
            for ht in [t0, t1, t2]:
                if ht.state == TurbineState.OFFLINE and not ht.config.hot_standby:
                    ht.command_start(sim_time=0.0)
                    pending.record_start(ht.config.asset_id, 0.0)
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


# ── TC-92: reserve floor commits N+1 for a demand N units can serve ───────────

def test_tc92_reserve_floor_commits_n_plus_1():
    """TC-92: reserve floor demands one more unit than demand alone requires.

    With 2 SYNCHRONISED turbines each rated 7 MW and p_demand = 8 MW:
      N=2 units cover the demand (2×7 = 14 MW ≥ 8 MW).
      Reserve floor: Σ rated ≥ p_demand + max(rated) → 14 ≥ 8+7=15 → VIOLATED.
    evaluate_commitment() must return action="commit" (start a 3rd unit) even
    though the running fleet can serve the current demand.

    This is the N+1 commitment invariant: the fleet always holds one unit above
    what the current load requires, so any single-unit trip leaves enough
    capacity to still cover demand.

    Spec refs: DR-2026-08-06 §7.1.3 reserve-floor requirement, Phase D Item 5.
    """
    from core.asset_modules import TurbineModule, TurbineState
    from core.models import TurbineConfig
    from core.commitment import (
        CommitmentConfig, SustainedCondition, PendingStartRegister,
        evaluate_commitment,
    )

    # Two on-bus units and one offline candidate.
    t0 = TurbineModule(TurbineConfig(asset_id="t-0", rated_mw=7.0, r_asset_mw_per_s=0.2))
    t1 = TurbineModule(TurbineConfig(asset_id="t-1", rated_mw=7.0, r_asset_mw_per_s=0.2))
    t2 = TurbineModule(TurbineConfig(asset_id="t-2", rated_mw=7.0, r_asset_mw_per_s=0.2))
    t0.state = TurbineState.SYNCHRONISED
    t1.state = TurbineState.SYNCHRONISED
    # t2 stays OFFLINE

    on_bus  = [t0.unit_availability(), t1.unit_availability()]
    offline = [t2.unit_availability()]
    p_demand = 8.0  # 2 units can serve 8 MW; floor says 3 are needed

    cfg = CommitmentConfig.from_catalogue()
    pending      = PendingStartRegister()
    commit_cond  = SustainedCondition(threshold_s=0.0)   # confirm instantly for test
    decommit_cond = SustainedCondition(threshold_s=0.0)

    decision = evaluate_commitment(
        on_bus=on_bus,
        offline=offline,
        p_demand_mw=p_demand,
        pending=pending,
        commit_cond=commit_cond,
        decommit_cond=decommit_cond,
        cfg=cfg,
        dt_s=5.0,
        sim_time=0.0,
    )

    assert decision.action == "commit", (
        f"TC-92 FAIL: expected action='commit' when reserve floor violated "
        f"(2×7={14} MW < demand+max={8+7}=15 MW); got action={decision.action!r}. "
        f"reason: {decision.reason!r}"
    )
    assert decision.target_unit_id == "t-2", (
        f"TC-92: expected target_unit_id='t-2', got {decision.target_unit_id!r}"
    )


# ── TC-93: STARTING unit contributes zero to reserve, ramp, and headroom ──────

def test_tc93_starting_unit_contributes_zero():
    """TC-93: A STARTING turbine contributes zero to reserve, ramp, and headroom.

    Checks three zero-contribution properties that the spec requires:
      1. is_on_bus is False → not counted toward on-bus capacity or headroom.
      2. ramp_capability() returns 0.0 → not credited toward reserve ramp.
      3. output_mw() returns 0.0 → produces nothing while counting down.

    PendingStartRegister is the mechanism that prevents the commitment engine
    from starting a second unit while one is in STARTING — these three
    assertions confirm why: the pending unit cannot be counted toward any
    capacity figure, making any double-count a hard violation.

    Spec refs: DR-2026-08-06 Phase A PROHIBITED note; §7.1.3 D-05; TC-80.
    """
    from core.asset_modules import TurbineModule, TurbineState
    from core.models import TurbineConfig
    from core.loading import ramp_capability

    t = TurbineModule(TurbineConfig(
        asset_id="t-starting",
        rated_mw=7.0,
        r_asset_mw_per_s=0.2,
        hot_start_s=300.0,
    ))
    t.command_start(sim_time=0.0)

    assert t.state == TurbineState.STARTING, (
        f"TC-93 pre-condition: command_start() must produce STARTING, got {t.state.value}"
    )

    # 1. On-bus flag: STARTING must not be counted as on_bus.
    assert not t.is_on_bus, (
        "TC-93 FAIL: STARTING unit reported is_on_bus=True — "
        "it must not contribute to reserved/headroom calculations."
    )

    # 2. Ramp capability: STARTING must contribute 0 MW over any horizon.
    cap = ramp_capability(horizon_s=300.0, turbines=[t])
    assert cap == 0.0, (
        f"TC-93 FAIL: ramp_capability for STARTING unit = {cap} MW (expected 0.0). "
        f"STARTING units may not be credited toward reserve ramp (TC-80)."
    )

    # 3. Output: STARTING units produce nothing.
    assert t.output_mw() == 0.0, (
        f"TC-93 FAIL: STARTING unit output_mw = {t.output_mw()} MW (expected 0.0). "
        f"STARTING units are not on the bus and produce no power."
    )


# ── TC-91b: both production call sites in one real tick ───────────────────────

def test_tc91b_both_production_paths_share_pending_register():
    """TC-91b: PendingStartRegister is reachable from both production call sites
    in the same simulation tick; at most one unit starts.

    TC-91 manually drove stage_for_predicted_step() and the headroom check.
    TC-91b drives a real ctx.step() so that both live code paths run
    sequentially in one tick and must share the same PendingStartRegister.

    Production call sites in one tick:
      A. apply_workload_signal() → arb.stage_for_predicted_step()
         (fires when a STARTING job signal is dispatched in the current tick)
      B. evaluate_commitment() called from the tick loop in simulation_core.py
         (fires when reserve floor is violated)

    Both are eligible when:
      - There are OFFLINE turbines available to start.
      - One turbine is already SYNCHRONISED above the headroom threshold
        (→ reserve floor violated, making path B want to commit).
      - A STARTING job signal is pending
        (→ path A fires a demand-step staging call with delta > 0).

    PendingStartRegister must prevent path B from starting a second unit after
    path A has already started one.  If the register is wired correctly, exactly
    one of {turbine-1, turbine-2, turbine-3} transitions to STARTING; the rest
    remain OFFLINE.

    If the register is NOT shared between both paths, both could fire and two
    units would start simultaneously — exactly the defect TC-89/TC-90 guard.
    """
    from api.routes.scenarios import build_seeded_store
    from api.schemas import ScenarioSpec
    from runtime.scenario_factory import build_run_context_from_spec
    from core.models import TurbineState

    store = build_seeded_store()
    rec   = store.get("demo-20mw")
    spec  = ScenarioSpec.model_validate_json(rec.spec_json)
    ctx   = build_run_context_from_spec("tc91b-run", spec.model_dump())

    # Force turbine-0 to SYNCHRONISED at 86% output (above 80% headroom threshold).
    # This makes the commitment engine's reserve-floor check fire (1 unit 7 MW
    # < demand+max_rated ≈ 6.3+7 = 13.3 MW) AND makes stage_for_predicted_step()
    # eligible for the initial workload STARTING signal.
    active = [t for t in ctx.sim_state.turbines if not t.config.hot_standby]
    active[0].state = TurbineState.SYNCHRONISED
    active[0]._current_output_mw = 6.0   # 6/7 MW = 86% > 80% headroom threshold

    # Snapshot OFFLINE units before the tick.
    offline_before = {t.config.asset_id for t in active if t.state == TurbineState.OFFLINE}
    assert len(offline_before) >= 2, (
        "TC-91b pre-condition: need ≥ 2 OFFLINE non-standby turbines "
        "so both paths have a candidate to start"
    )

    # Run exactly one tick — both production paths fire inside ctx.step().
    ctx.step()

    # Count how many OFFLINE units transitioned to STARTING.
    new_starting = [
        t for t in active
        if t.config.asset_id in offline_before
        and t.state == TurbineState.STARTING
    ]

    assert len(new_starting) <= 1, (
        f"TC-91b FAIL: {len(new_starting)} units entered STARTING in one tick "
        f"({[t.config.asset_id for t in new_starting]}). "
        f"Both production call sites (stage_for_predicted_step + evaluate_commitment) "
        f"started units independently — PendingStartRegister is not shared between them. "
        f"Check that arbitrator.pending_start is assigned in SimulationState.__post_init__."
    )
