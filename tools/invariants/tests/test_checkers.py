"""TC-110 .. TC-117 plus loader/preflight coverage."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from nar001 import checkers, load, stats
from nar001.checkers import (check_i1, check_i2a, check_i2b, check_i3, check_i4,
                             check_i5, check_i6, run_all)
from nar001.contracts import EVALUATED, NOT_EVALUABLE
from nar001.report import analyse, write_report

from fixtures import chain, ctx, deep_set, deep_without, tick, write_jsonl


def one(records, invariant):
    hits = [r for r in records if r.invariant == invariant]
    assert hits, f"no record for {invariant}"
    return hits[0]


# ---------------------------------------------------------------- TC-110 (I1)
def test_tc110_i1_detects_known_imbalance():
    # Landing-page shape: 40.36 MW served against 30.90 MW supplied, islanded.
    p = tick(p_demand_mw=40.36, p_total_mw=40.36, p_generation_mw=30.90,
             grid_exchange_mw=0.0)
    r = one(check_i1(ctx(p)), "I1")
    assert r.status == EVALUATED
    assert r.value == pytest.approx(-9.46, abs=1e-9)


def test_tc110_i1_balanced_is_zero():
    r = one(check_i1(ctx()), "I1")
    assert r.value == pytest.approx(0.0)


def test_tc110_i1_includes_grid_term():
    p = tick(p_demand_mw=12.0, p_total_mw=12.0, p_generation_mw=10.0,
             grid_exchange_mw=2.0)
    assert one(check_i1(ctx(p)), "I1").value == pytest.approx(0.0)


def test_tc110_i1d_reports_both_sign_conventions():
    p = tick(p_demand_mw=40.36, p_total_mw=40.36, p_generation_mw=30.90,
             d4_balance_defect_mw=-9.46)
    r = one(check_i1(ctx(p)), "I1d")
    assert r.value == pytest.approx(0.0)                                  # as emitted
    assert r.detail["delta_if_declared_negated"] == pytest.approx(-18.92)  # negated


def test_tc110_i1_not_evaluable_when_field_absent():
    r = one(check_i1(ctx(deep_without(tick(), "p_generation_mw"))), "I1")
    assert r.status == NOT_EVALUABLE and "absent" in r.reason


# ---------------------------------------------------------------- TC-111 (I2)
def test_tc111_i2a_fires_and_is_silent():
    assert one(check_i2a(ctx()), "I2a").value == pytest.approx(0.0)
    p = tick(p_generation_mw=12.0)          # supply sums to 10.0
    assert one(check_i2a(ctx(p)), "I2a").value == pytest.approx(-2.0)


def test_tc111_i2b_not_evaluable_when_kube_null():
    r = one(check_i2b(ctx()), "I2b")
    assert r.status == NOT_EVALUABLE
    assert r.value is None                  # never zero
    assert "null" in r.reason


def test_tc111_i2b_evaluates_when_kube_present():
    p = tick(kube_metrics={"admitted_nodes": 800, "kw_per_node": 10.0,
                           "active_jobs": 4},
             p_compute_demand_mw=8.0, p_compute_mw=8.0)
    r = one(check_i2b(ctx(p)), "I2b")
    assert r.status == EVALUATED
    assert r.value == pytest.approx(0.0)    # 800 * 10 kW = 8.0 MW

    p2 = deep_set(p, "p_compute_demand_mw", 9.5)
    p2 = deep_set(p2, "p_compute_mw", 9.5)
    assert one(check_i2b(ctx(p2)), "I2b").value == pytest.approx(1.5)


# ---------------------------------------------------------------- TC-112 (I3)
def test_tc112_i3_null_is_not_evaluable_not_zero():
    p = deep_set(tick(), "p_served_mw", None)
    r = one(check_i3(ctx(p)), "I3_site")
    assert r.status == NOT_EVALUABLE
    assert r.value is None                  # the whole point: not 0.0
    assert "null" in r.reason


def test_tc112_i3_absent_block_field_is_not_evaluable():
    p = deep_without(tick(), "p_cooling_unserved_mw")
    r = one(check_i3(ctx(p)), "I3_cooling")
    assert r.status == NOT_EVALUABLE and r.value is None


def test_tc112_i3_site_is_tautological_on_shed():
    # served = demand - shed, unserved = shed: residual stays zero at any shed level.
    for shed in (0.0, 3.0, 9.99):
        p = tick(p_served_mw=10.0 - shed, p_unserved_mw=shed)
        assert one(check_i3(ctx(p)), "I3_site").value == pytest.approx(0.0)


def test_tc112_i3_block_catches_bad_split():
    p = tick(p_compute_served_mw=7.0)       # 7.0 + 0.0 != 8.0
    assert one(check_i3(ctx(p)), "I3_compute").value == pytest.approx(-1.0)


# ---------------------------------------------------------------- TC-113 (I4)
def test_tc113_i4_turbine_at_rated_has_no_exceedance():
    p = deep_set(tick(), "turbine_units",
                 [{"unit_id": "t0", "state": "synchronised", "output_mw": 7.0,
                   "rated_mw": 7.0, "hot_standby": False}])
    r = one(check_i4(ctx(p)), "I4_turbine")
    assert r.value == pytest.approx(0.0)
    assert r.detail["exceedance_mw"] == pytest.approx(0.0)


def test_tc113_i4_turbine_above_rated():
    p = deep_set(tick(), "turbine_units",
                 [{"unit_id": "t0", "state": "synchronised", "output_mw": 14.0,
                   "rated_mw": 7.0}])
    r = one(check_i4(ctx(p)), "I4_turbine")
    assert r.value == pytest.approx(7.0)
    assert r.detail["exceedance_mw"] == pytest.approx(7.0)


def test_tc113_i4_bess_both_directions():
    r = one(check_i4(ctx(tick(bess_output_mw=16.0, bess_rated_mw=15.0))), "I4_bess")
    assert r.value == pytest.approx(1.0) and r.detail["direction"] == "discharge"
    r2 = one(check_i4(ctx(tick(bess_output_mw=-16.0, bess_rated_mw=15.0))), "I4_bess")
    assert r2.value == pytest.approx(1.0) and r2.detail["direction"] == "charge"


def test_tc113_i4_cooling_over_rating():
    # The 8.84 MW served against a 2.03 MW rating seen on the console.
    p = tick(p_cooling_demand_mw=8.84, p_cooling_mw=8.84, rated_cooling_mw=2.03)
    r = one(check_i4(ctx(p)), "I4_cooling")
    assert r.value == pytest.approx(6.81)


def test_tc113_i4_emits_one_record_per_unit():
    recs = [r for r in check_i4(ctx()) if r.invariant == "I4_turbine"]
    assert len(recs) == 2
    assert {r.subject for r in recs} == {"turbine_units[0]", "turbine_units[1]"}


# ---------------------------------------------------------------- TC-114 (I5)
def test_tc114_i5_first_tick_has_no_predecessor():
    r = one(check_i5(ctx()), "I5")
    assert r.status == NOT_EVALUABLE and "predecessor" in r.reason


def test_tc114_i5_consistent_discharge_is_zero():
    # 7.2 MW for 5 s = 0.01 MWh; 0.01 / 8.0 MWh = 0.00125 SoC.
    a = tick(sim_time_seconds=100.0, bess_soc_fraction=0.50, bess_output_mw=7.2)
    b = tick(sim_time_seconds=105.0, bess_soc_fraction=0.50 - 0.00125,
             bess_output_mw=7.2)
    c0, c1 = chain([a, b])
    r = one(check_i5(c1), "I5")
    assert r.status == EVALUATED
    assert r.value == pytest.approx(0.0, abs=1e-12)
    assert r.terms["dt_s"] == pytest.approx(5.0)


def test_tc114_i5_soc_moves_without_power():
    # SoC drops with output pinned at zero -- the 95% -> 44% pattern.
    a = tick(sim_time_seconds=100.0, bess_soc_fraction=0.95, bess_output_mw=0.0)
    b = tick(sim_time_seconds=105.0, bess_soc_fraction=0.44, bess_output_mw=0.0)
    _, c1 = chain([a, b])
    r = one(check_i5(c1), "I5")
    assert r.value == pytest.approx((0.95 - 0.44) * 8.0)


def test_tc114_i5_derives_dt_and_rejects_nonpositive():
    a = tick(sim_time_seconds=200.0)
    b = tick(sim_time_seconds=200.0)
    _, c1 = chain([a, b])
    assert one(check_i5(c1), "I5").status == NOT_EVALUABLE


def test_tc114_i5_reads_usable_mwh_per_run():
    for usable in (2.0, 8.0):
        a = tick(sim_time_seconds=0.0, bess_soc_fraction=0.5, bess_output_mw=0.0,
                 bess_usable_mwh=usable)
        b = tick(sim_time_seconds=5.0, bess_soc_fraction=0.4, bess_output_mw=0.0,
                 bess_usable_mwh=usable)
        _, c1 = chain([a, b])
        assert one(check_i5(c1), "I5").value == pytest.approx(0.1 * usable)


# ---------------------------------------------------------------- TC-115 (I6)
def test_tc115_i6_reconstructs_floor_violated_and_agrees():
    # committed 7.0 < floor 17.0 -> violated -> reserve_satisfied False -> agree.
    r = one(check_i6(ctx()), "I6_committed")
    assert r.value == pytest.approx(0.0)
    assert r.detail["reconstructed_floor_violated"] is True
    assert r.detail["reported_reserve_satisfied"] is False
    assert r.detail["agree"] is True


def test_tc115_i6_detects_disagreement():
    p = deep_set(tick(), "commitment_block.reserve_satisfied", True)
    r = one(check_i6(ctx(p)), "I6_committed")
    assert r.detail["agree"] is False


def test_tc115_i6_excludes_offbus_and_hot_standby():
    p = deep_set(tick(), "turbine_units", [
        {"state": "synchronised", "output_mw": 5.0, "rated_mw": 7.0, "hot_standby": False},
        {"state": "synchronised", "output_mw": 0.0, "rated_mw": 7.0, "hot_standby": True},
        {"state": "starting", "output_mw": 0.0, "rated_mw": 7.0, "hot_standby": False},
    ])
    r = one(check_i6(ctx(p)), "I6_committed")
    assert r.detail["on_bus_count"] == 1
    assert r.terms["recomputed_committed_mw"] == pytest.approx(7.0)


def test_tc115_i6_flags_hold_with_unsatisfied_reserve():
    r = one(check_i6(ctx()), "I6_committed")
    assert r.detail["commitment_action"] == "hold"
    assert r.detail["hold_with_unsatisfied_reserve"] is True


def test_tc115_i6_floor_carries_both_demand_bases():
    r = one(check_i6(ctx()), "I6_floor")
    assert r.detail["residual_using_p_demand_mw"] == pytest.approx(0.0)   # 10 + 7 - 17
    assert r.detail["residual_using_net_demand_mw"] == pytest.approx(-3.0)  # 7 + 7 - 17


def test_tc115_i6_notes_hot_standby_absence():
    p = deep_set(tick(), "turbine_units",
                 [{"state": "synchronised", "output_mw": 5.0, "rated_mw": 7.0}])
    r = one(check_i6(ctx(p)), "I6_committed")
    assert r.detail["hot_standby_present_on_wire"] is False


# ---------------------------------------------------------------- TC-116
def test_tc116_harness_is_deterministic(tmp_path):
    payloads = [tick(sim_time_seconds=float(t), bess_soc_fraction=0.9 - t * 0.001)
                for t in range(0, 60, 5)]
    p = tmp_path / "run-det.jsonl"
    write_jsonl(p, payloads)

    outs = []
    for _ in range(2):
        rec = load.load_recording(p)
        records, _ = analyse(rec)
        outs.append(json.dumps([r.to_dict() for r in records], sort_keys=True,
                               default=str))
    assert outs[0] == outs[1]


def test_tc116_no_rng_or_clock_in_analysis_modules():
    for mod in (checkers, stats):
        src = inspect.getsource(mod)
        for banned in ("import random", "random.", "time.time", "datetime.now",
                       "uuid", "os.environ"):
            assert banned not in src, f"{mod.__name__} references {banned}"


# ---------------------------------------------------------------- TC-117
def test_tc117_no_verdicts_or_tolerances_in_record_schema():
    r = one(run_all(ctx()), "I1")
    keys = set(r.to_dict())
    assert not keys & {"passed", "pass", "ok", "verdict", "result", "severity",
                       "tolerance", "threshold"}
    assert keys >= {"invariant", "status", "value", "unit", "terms", "reason"}


def test_tc117_no_tolerance_constants_in_checkers():
    src = inspect.getsource(checkers)
    for banned in ("TOLERANCE", "THRESHOLD", "EPSILON", "ATOL", "RTOL",
                   "PASS", "FAIL"):
        assert banned not in src, f"checkers references {banned}"


def test_tc117_status_vocabulary_is_closed():
    assert {r.status for r in run_all(ctx())} <= {EVALUATED, NOT_EVALUABLE}


# ---------------------------------------------------------------- loader
def test_loader_separates_ticks_events_and_sentinel(tmp_path):
    p = tmp_path / "run-x.jsonl"
    write_jsonl(p, [tick(sim_time_seconds=10.0), tick(sim_time_seconds=15.0)],
                events=[{"seq": 99, "event": "reconnect"}])
    rec = load.load_recording(p)
    assert len(rec.ticks) == 2
    assert len(rec.control) == 1          # run_complete sentinel
    assert [e["event"] for e in rec.events] == ["reconnect"]
    assert rec.malformed_lines == 0


def test_loader_counts_malformed_without_raising(tmp_path):
    p = tmp_path / "run-y.jsonl"
    write_jsonl(p, [tick()])
    with p.open("a") as fh:
        fh.write("{not json\n")
        fh.write(json.dumps({"seq": 5}) + "\n")
    rec = load.load_recording(p)
    assert rec.malformed_lines == 2 and len(rec.ticks) == 1


def test_preflight_reports_null_and_alias_use(tmp_path):
    p = tmp_path / "run-z.jsonl"
    write_jsonl(p, [tick(), tick(sim_time_seconds=105.0)])
    pf = load.preflight(load.load_recording(p))
    assert pf["fields"]["kube_metrics"]["states"] == {"null": 2}
    assert pf["fields"]["p_demand_mw"]["ok_fraction"] == 1.0
    assert pf["fields"]["kw_per_node"]["ok_fraction"] == 0.0


def test_constant_fields_partitions_correctly(tmp_path):
    p = tmp_path / "run-c.jsonl"
    write_jsonl(p, [tick(sim_time_seconds=10.0, bess_output_mw=1.0),
                    tick(sim_time_seconds=15.0, bess_output_mw=2.0)])
    cf = load.constant_fields(load.load_recording(p))
    assert "bess_usable_mwh" in cf["constant"]
    assert "turbine_units[0].rated_mw" in cf["constant"]
    assert "bess_output_mw" in cf["varying"]
    assert "sim_time_seconds" in cf["varying"]


def test_report_writes_and_names_untested_invariants(tmp_path):
    p = tmp_path / "run-r.jsonl"
    write_jsonl(p, [tick(sim_time_seconds=float(t)) for t in range(0, 30, 5)])
    md = tmp_path / "out.md"
    jl = tmp_path / "out.jsonl"
    text = write_report([load.load_recording(p)], md, jl)
    assert md.exists() and jl.exists()
    assert "I2b" in text and "Units assumed" in text
    assert "TAUTOLOGY" in text
    lines = [json.loads(l) for l in jl.read_text().splitlines()]
    assert all("value" in l and "status" in l for l in lines)


# ------------------------------------------------- regressions found by running
def test_one_sided_extreme_is_signed_not_absolute():
    """I4's largest magnitude is the most idle asset; the finding is the largest
    signed value. Guards the defect the first real report run exposed."""
    from nar001.stats import distribution
    recs = []
    for i, (out, rated) in enumerate([(0.0, 15.0), (16.0, 15.0)]):
        recs.extend(r for r in check_i4(ctx(tick(bess_output_mw=out,
                                                 bess_rated_mw=rated), seq=i))
                    if r.invariant == "I4_bess")
    d = distribution(recs)
    assert d["worst_abs"]["value"] == pytest.approx(-15.0)   # idle asset
    assert d["worst_high"]["value"] == pytest.approx(1.0)    # the actual finding


def test_shape_is_computed_per_subject():
    """Pooling five turbines into one series produced ~1600 spurious reversals."""
    from nar001.stats import shape_by_subject
    recs = []
    for i in range(10):
        recs.extend(r for r in run_all(ctx(tick(sim_time_seconds=10.0 + 5 * i), seq=i))
                    if r.invariant == "I4_turbine")
    shapes = shape_by_subject(recs)
    assert set(shapes) == {"turbine_units[0]", "turbine_units[1]"}
    assert all(s["n_sign_reversals"] == 0 for s in shapes.values())


def test_sign_convention_tie_is_reported_indeterminate(tmp_path):
    """d4 identically zero fits both conventions; claiming one would be false."""
    p = tmp_path / "run-tie.jsonl"
    write_jsonl(p, [tick(sim_time_seconds=float(t), d4_balance_defect_mw=0.0)
                    for t in range(0, 40, 5)])
    text = write_report([load.load_recording(p)], tmp_path / "m.md",
                        tmp_path / "r.jsonl")
    assert "indeterminate" in text
    assert "identically zero" in text
