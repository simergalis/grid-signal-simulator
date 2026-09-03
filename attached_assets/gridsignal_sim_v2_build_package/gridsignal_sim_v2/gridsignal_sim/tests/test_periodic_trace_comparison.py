from copy import deepcopy

from runtime.periodic_trace_comparison import compare_import_report


def imported_report(values, *, confidence=None):
    accepted = []
    for index, (predicted, actual) in enumerate(values):
        row = {
            "timestamp": f"2026-08-01T12:{index:02d}:00",
            "predicted_mw": predicted,
            "mw_measured": actual,
        }
        if confidence is not None:
            row["confidence_band_percent"] = confidence[index]
        accepted.append(row)
    return {
        "import_id": "import-abc123",
        "site_id": "sj-1",
        "window": {
            "start": accepted[0]["timestamp"],
            "end": accepted[-1]["timestamp"],
        },
        "total_rows": len(accepted) + 2,
        "accepted_rows": len(accepted),
        "quarantined_rows": 2,
        "quarantined_by_reason": {"example invalid row": 2},
        "conflict_count": 1,
        "accepted": accepted,
    }


def test_same_import_and_settings_produce_identical_comparison():
    report = imported_report([(1.0, 1.1), (4.0, 3.8), (2.0, 2.1)])
    first = compare_import_report(report)
    second = compare_import_report(report)
    assert first == second
    assert first["comparison_id"] == second["comparison_id"]


def test_without_pas_firm_capacity_is_true_series_maximum():
    report = imported_report([(1.0, 1.1), (10.0, 9.5), (4.0, 4.2), (8.0, 8.1)])
    comparison = compare_import_report(report, pas_percentile=90)
    assert comparison["baseline"]["firm_capacity_mw"] == 10.0
    assert comparison["baseline"]["exceeded_firm_capacity_timestamps"] == 0
    assert comparison["pas"]["firm_capacity_mw"] < 10.0


def test_comparison_is_read_only_and_has_no_live_control_side_effects():
    report = imported_report([(1.0, 1.1), (4.0, 3.8)])
    original = deepcopy(report)
    comparison = compare_import_report(report)
    assert report == original
    assert not any(
        key in comparison
        for key in ("dispatch_action", "control_event", "approval_workflow_entry")
    )


def test_existing_per_segment_confidence_is_used_for_pas_reserve():
    report = imported_report(
        [(1.0, 1.1), (4.0, 3.8)],
        confidence=[10.0, 20.0],
    )
    comparison = compare_import_report(report, pas_confidence_scale=1.5)
    assert comparison["pas"]["confidence_placeholder_used"] is False
    assert comparison["pas"]["confidence_source"] == "existing per-segment confidence"
    assert comparison["pas"]["average_reserve_percent"] == 22.5
    assert [item["reserve_percent"] for item in comparison["pas"]["reserve_series"]] == [15.0, 30.0]


def test_current_phase_one_imports_explicitly_flag_confidence_placeholder():
    comparison = compare_import_report(imported_report([(1.0, 1.1), (4.0, 3.8)]))
    assert comparison["pas"]["confidence_placeholder_used"] is True
    assert comparison["pas"]["confidence_source"] == "flat placeholder (not validated)"
    assert "not validated" in comparison["pas"]["confidence_note"]