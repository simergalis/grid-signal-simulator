"""End-to-end smoke script tests.

The property that matters: a stage producing nothing must fail loudly. A silent
empty list looks like success and is how an integration mismatch survives to the
next stage.
"""
from __future__ import annotations

import json

import pytest

from nar001 import smoke
from nar001.framefact import CAP_KEY, SPREAD_KEY

from fixtures import tick
from test_trend import TREND_CAT

FULL_CAT = {**TREND_CAT, CAP_KEY: 8, SPREAD_KEY: 1e-9}


def write(path, payloads, events=None):
    with open(path, "w") as fh:
        for i, p in enumerate(payloads):
            fh.write(json.dumps({"seq": i, "received_wall_utc": "x",
                                 "payload": p}) + "\n")
        for e in events or []:
            fh.write(json.dumps(e) + "\n")


def moving(n=60):
    out = []
    v = 10.0
    for i in range(n):
        if i % 5 == 0:
            v += 1.5
        out.append(tick(sim_time_seconds=float(i * 5), p_demand_mw=v, p_total_mw=v,
                        p_compute_demand_mw=v - 2, p_compute_mw=v - 2,
                        p_generation_mw=v, p_served_mw=v,
                        p_compute_served_mw=v - 2,
                        bess_soc_fraction=0.9 - i * 0.001))
    return out


def cat_file(tmp_path, **over):
    p = tmp_path / "bands.json"
    p.write_text(json.dumps({**FULL_CAT, **over}))
    return str(p)


def test_stages_1_to_4_run_without_a_catalogue(tmp_path, capsys):
    write(tmp_path / "run-a.jsonl", moving())
    assert smoke.main([str(tmp_path / "run-a.jsonl")]) == 0
    out = capsys.readouterr().out
    for stage in ("STAGE 1", "STAGE 2", "STAGE 3", "STAGE 4"):
        assert stage in out
    assert "STOPPING after stage 4" in out
    assert "must be read off the curves above, not chosen" in out


def test_all_seven_stages_run_with_a_catalogue(tmp_path, capsys):
    write(tmp_path / "run-b.jsonl", moving())
    rc = smoke.main([str(tmp_path / "run-b.jsonl"),
                     "--catalogue", cat_file(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    for stage in range(1, 8):
        assert f"STAGE {stage}" in out
    assert "HEADLINE" in out and "BODY" in out
    assert "All seven stages produced output." in out


def test_empty_recording_fails_at_stage_one(tmp_path, capsys):
    (tmp_path / "run-c.jsonl").write_text("")
    assert smoke.main([str(tmp_path / "run-c.jsonl")]) == 1
    assert "no tick payloads" in capsys.readouterr().err


def test_unrecognised_payload_shape_fails_at_stage_two(tmp_path, capsys):
    write(tmp_path / "run-d.jsonl",
          [{"sim_time_seconds": float(i * 5), "totally": "different"}
           for i in range(10)])
    assert smoke.main([str(tmp_path / "run-d.jsonl")]) == 1
    err = capsys.readouterr().err
    assert "payload shape differs" in err
    assert "ALIASES" in err


def test_bands_too_wide_fails_at_stage_five_rather_than_reporting_silence(
        tmp_path, capsys):
    """The failure mode this script exists to catch: every stage 'succeeds' and
    the feed is simply empty."""
    write(tmp_path / "run-e.jsonl", moving())
    wide = {k: 1e9 for k in ("deadband_power_mw", "deadband_power_small_mw",
                             "deadband_soc_fraction", "deadband_frequency_hz",
                             "deadband_temp_c", "deadband_dt_lead_s",
                             "deadband_step_phase", "rate_band_mw_per_s")}
    rc = smoke.main([str(tmp_path / "run-e.jsonl"),
                     "--catalogue", cat_file(tmp_path, **wide)])
    assert rc == 1
    assert "bands in the catalogue are almost certainly too wide" in \
        capsys.readouterr().err


def test_missing_catalogue_keys_fail_before_any_detection(tmp_path, capsys):
    write(tmp_path / "run-f.jsonl", moving())
    p = tmp_path / "partial.json"
    p.write_text(json.dumps({"deadband_power_mw": 0.5, CAP_KEY: 8,
                             SPREAD_KEY: 1e-9,
                             "trend_windows_s": [60.0], "trend_reversal_n": 3}))
    assert smoke.main([str(tmp_path / "run-f.jsonl"), "--catalogue", str(p)]) == 2
    assert "missing required parameters" in capsys.readouterr().err


def test_dropped_recording_is_flagged(tmp_path, capsys):
    write(tmp_path / "run-g.jsonl", moving())
    (tmp_path / "run-g.manifest.json").write_text(
        json.dumps({"run_id": "run-g", "stop_reason": "dropped",
                    "missed_leading_ticks": True}))
    smoke.main([str(tmp_path / "run-g.jsonl")])
    out = capsys.readouterr().out
    assert "truncated" in out


def test_skipped_invariants_are_named_untested_not_passing(tmp_path, capsys):
    write(tmp_path / "run-h.jsonl", moving())
    smoke.main([str(tmp_path / "run-h.jsonl")])
    out = capsys.readouterr().out
    assert "SKIPPED" in out and "untested, not passing" in out


def test_static_recording_fails_calibration_rather_than_reporting_nothing(
        tmp_path, capsys):
    write(tmp_path / "run-i.jsonl",
          [tick(sim_time_seconds=float(i * 5)) for i in range(20)])
    assert smoke.main([str(tmp_path / "run-i.jsonl")]) == 1
    assert "no signal produced a calibration curve" in capsys.readouterr().err
