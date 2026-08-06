"""
tests/test_tc87_tc88_sequential_start.py — Phase A gate tests.

TC-87  At most one non-standby turbine is non-OFFLINE after the first simulation
       tick of the demo-20mw scenario (first-tick snapshot).

TC-88  In any of the first 20 ticks of the demo-20mw scenario, at most one
       non-standby turbine transitions from OFFLINE to any other state in a
       single tick (full-run sequential-start assertion).

Both tests describe the DESIRED post-fix behaviour and FAIL with the current
N_needed+1 simultaneous-start implementation.  They form the Phase A pre-condition
gate for the ramp-algorithm replacement (DR-2026-08-06 D-05, §7.1.3 v2.6 draft).

Failure mode (pre-fix):
  dispatch.py:512-518 — stage_for_predicted_step() computes:
      _n_start = min(max(1, ceil(delta_p/rated)+1), len(_offline))
  For the demo-20mw 3-unit fleet and a ~6.3 MW step this gives _n_start = 2.
  Both turbine-0 and turbine-1 enter RAMPING on the same tick (tick 0), violating
  the sequential-start contract.

Phase A gate:
  Both TC-87 and TC-88 must be confirmed FAILING in the Phase A report.
  No previously passing test may regress (965 passing tests stay passing).
  After Phase B-D both must pass.
"""


# ── TC-87: first-tick snapshot ────────────────────────────────────────────────

def test_tc87_first_tick_starts_at_most_one_unit():
    """TC-87: At most one non-standby turbine is non-OFFLINE after tick 0.

    All turbines begin OFFLINE.  After exactly one tick the dispatch arbitrator
    has had one opportunity to call stage_for_predicted_step().  With the
    sequential-start contract only ONE unit may have left the OFFLINE state.

    FAILS pre-fix: turbine-0 and turbine-1 both enter RAMPING at tick 0
    (N_needed+1 = 2 for the demo-20mw 3-unit fleet and a ~6.3 MW demand step).

    PASSES post-fix: dispatch starts exactly 1 unit per tick; subsequent units
    start in later ticks via the per-tick headroom check.

    Spec refs: DR-2026-08-06 D-05; §7.1.3 sequential-start requirement.
    """
    from api.routes.scenarios import build_seeded_store
    from api.schemas import ScenarioSpec
    from runtime.scenario_factory import build_run_context_from_spec
    from core.models import TurbineState

    store = build_seeded_store()
    rec = store.get("demo-20mw")
    assert rec is not None, "demo-20mw scenario not found in seeded store"

    spec = ScenarioSpec.model_validate_json(rec.spec_json)
    ctx = build_run_context_from_spec("tc87-run", spec.model_dump())

    # Pre-condition: every non-standby turbine starts OFFLINE.
    active = [t for t in ctx.sim_state.turbines if not t.config.hot_standby]
    assert all(t.state == TurbineState.OFFLINE for t in active), (
        "TC-87 pre-condition: all non-standby turbines must start OFFLINE"
    )
    assert len(active) >= 2, (
        "TC-87 pre-condition: need ≥2 non-standby turbines to detect simultaneous starts"
    )

    # Run exactly one tick.
    ctx.step()

    # At most 1 unit should have left OFFLINE.
    non_offline = [t for t in active if t.state != TurbineState.OFFLINE]

    assert len(non_offline) <= 1, (
        f"TC-87 FAIL: {len(non_offline)} units left OFFLINE state on tick 0 "
        f"({[t.config.asset_id + ':' + t.state.value for t in non_offline]}). "
        f"stage_for_predicted_step() started N_needed+1 units simultaneously "
        f"instead of exactly 1. "
        f"Fix: dispatch must start exactly one unit per tick (D-05)."
    )


# ── TC-88: full-run sequential-start assertion ────────────────────────────────

def test_tc88_at_most_one_start_transition_per_tick():
    """TC-88: At most one non-standby turbine transitions OFFLINE→non-OFFLINE
    in any single simulation tick across the first 20 ticks (0–95 s).

    Tracks per-tick state transitions for every non-standby turbine and asserts
    the maximum count of simultaneous OFFLINE→non-OFFLINE transitions is ≤ 1.
    Covers the full startup window where the N_needed+1 defect manifests.

    FAILS pre-fix: tick 0 transitions 2 units (turbine-0 and turbine-1) from
    OFFLINE to RAMPING simultaneously.

    PASSES post-fix: no tick has more than 1 OFFLINE→non-OFFLINE transition;
    the second unit starts in a later tick via the per-tick headroom check.

    Spec refs: DR-2026-08-06 D-05; §7.1.3 sequential-start requirement.
    """
    from api.routes.scenarios import build_seeded_store
    from api.schemas import ScenarioSpec
    from runtime.scenario_factory import build_run_context_from_spec
    from core.models import TurbineState

    store = build_seeded_store()
    rec = store.get("demo-20mw")
    assert rec is not None, "demo-20mw scenario not found in seeded store"

    spec = ScenarioSpec.model_validate_json(rec.spec_json)
    ctx = build_run_context_from_spec("tc88-run", spec.model_dump())

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
        f"TC-88 FAIL: tick {worst_tick} had {max_simultaneous} units "
        f"transition from OFFLINE simultaneously: {worst_detail}. "
        f"stage_for_predicted_step() must start at most one unit per tick (D-05). "
        f"Remaining ticks all ≤1 start — worst offender was tick {worst_tick}."
    )
