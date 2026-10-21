"""Runtime-owned conversion metadata for the reference-forecast API."""
from __future__ import annotations

from typing import Any

from core.site_parameters import value as catalogue_value
from runtime.scenario_factory import DEFAULT_HARDWARE_LIBRARY


REFERENCE_PROFILE_IDS = {
    "kubernetes": "enterprise_8gpu_air",
    "slurm": "enterprise_8gpu_air",
    "ray": "nextgen_rack_liquid",
}


def reference_forecast_conversion_context() -> tuple[dict[str, Any], float]:
    """Return runtime-resolved profiles and catalogue-backed PUE."""
    profiles = {
        domain: DEFAULT_HARDWARE_LIBRARY[profile_id]
        for domain, profile_id in REFERENCE_PROFILE_IDS.items()
    }
    return profiles, float(catalogue_value("pue_base"))