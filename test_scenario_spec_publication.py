"""Lightweight checks for published ScenarioSpec reference artifacts."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
ARTIFACTS = (
    ROOT / "scenario_spec_reference.md",
    ROOT / "scenario_spec_schema.json",
    ROOT
    / "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2"
    / "frontend/public/scenario_spec_schema.json",
    ROOT
    / "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2"
    / "frontend/dist/scenario_spec_schema.json",
)
ASSERTION_CHECKS = (
    "no_insufficient_reserve_alert",
    "alert_fires",
    "max_p_total_mw",
    "min_final_bess_soc",
    "pue_base_in_declared_range",
    "declining_fuel_cell_reserve_alert_fires",
    "persistent_fuel_cell_deficit",
    "peak_fuel_cell_array_output",
    "no_cold_warming_contingency_capacity",
    "fuel_cell_commanded_and_achieved_reported",
)


def test_published_scenario_spec_artifacts_cover_fuel_cells_and_assertions() -> None:
    for artifact in ARTIFACTS:
        content = artifact.read_text(encoding="utf-8")
        assert "fuel_cell_units" in content, artifact
        assert "fuel_cell_rated_mw" in content, artifact
        assert "fuel_cell_stack_count" in content, artifact
        assert "per stack" in content.lower(), (
            f"{artifact} must identify fuel_cell_rated_mw as a per-stack rating"
        )
        for check_name in ASSERTION_CHECKS:
            assert check_name in content, f"{artifact} is missing {check_name}"