"""DR D3 / IMPL-ISL-3: observation only; never change frequency or protection."""
from core.models import IslandMode

# PROPOSED_HERE: synchronous-machine overspeed trips are typically about 110%
# of rated speed. Symmetric nominal +/-10% is a REPORTING band, not a relay.
FREQUENCY_VALIDITY_BAND_FRACTION = 0.10


def frequency_is_valid(frequency_hz: float, nominal_hz: float) -> bool:
    return bool(abs(frequency_hz - nominal_hz) <= nominal_hz * FREQUENCY_VALIDITY_BAND_FRACTION)


def protection_is_configured(site) -> bool:
    """Inspect resolved threshold values; relay delays alone do not enable a relay."""
    if site.island_mode not in (True, IslandMode.ISLANDED):
        return True
    if any(getattr(site, name, None) is not None for name in (
        "uf_warning_hz", "ufls_stage1_hz", "island_collapse_hz",
        "of_warning_hz", "of_trip_hz", "relay_81u_threshold_hz",
    )):
        return True
    return any(
        (stage.get("threshold_hz") if isinstance(stage, dict)
         else getattr(stage, "threshold_hz", None)) is not None
        for stage in (getattr(site, "ufls_stages", None) or [])
    )


def unprotected_island_warning(site) -> dict | None:
    if protection_is_configured(site):
        return None
    return {
        # PROPOSED_HERE: stable warning identity; no validation or trip condition.
        "code": "islanded_frequency_protection_unconfigured",
        "message": "islanded run without frequency protection configured",
    }
