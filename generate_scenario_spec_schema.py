"""Regenerate every published ScenarioSpec JSON Schema artifact.

Usage:
    .pythonlibs/bin/python generate_scenario_spec_schema.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent
SIM_ROOT = (
    WORKSPACE_ROOT
    / "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim"
)
DESTINATIONS = (
    WORKSPACE_ROOT / "scenario_spec_schema.json",
    SIM_ROOT.parent / "frontend/public/scenario_spec_schema.json",
    SIM_ROOT.parent / "frontend/dist/scenario_spec_schema.json",
)


def generate() -> None:
    """Render byte-identical schemas from the public Pydantic ScenarioSpec."""
    sys.path.insert(0, str(SIM_ROOT))
    from api.schemas import ScenarioSpec

    rendered = json.dumps(
        ScenarioSpec.model_json_schema(),
        indent=2,
        ensure_ascii=False,
    ) + "\n"
    for destination in DESTINATIONS:
        destination.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    generate()