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


def frequency_feedback_configured(site, fuel_cell_module=None) -> bool:
    """Return whether configured frequency feedback can affect run results.

    Grid-tied frequency is fixed at nominal, so its reporting protection flag
    does not imply frequency feedback.  The FC check mirrors the configured
    block ride-through path; this predicate classifies the run and never
    enables, disables, or changes that path.
    """
    if site is None or getattr(site, "island_mode", None) not in (
        True, IslandMode.ISLANDED, "islanded",
    ):
        return False
    if any(getattr(site, name, None) is not None for name in (
        "ufls_stage1_hz",       # enables bounded dispatch droop
        "of_trip_hz",           # enables bounded dispatch droop / OF trip
        "island_collapse_hz",
    )):
        return True
    relay_81u_threshold_hz = getattr(site, "relay_81u_threshold_hz", None)
    nominal_hz = getattr(site, "frequency_nominal_hz", 60.0)
    if relay_81u_threshold_hz is not None and relay_81u_threshold_hz < nominal_hz:
        return True
    if getattr(site, "ufls_stages", None):
        return True
    if (
        getattr(site, "of_warning_hz", None) is not None
        and getattr(site, "of_trip_hz", None) is not None
    ):
        return True
    # BlockFuelCellFleet.evaluate_ride_through is called from the islanded
    # substep loop and can trip blocks using the array's IEEE 1547 category.
    for array in getattr(fuel_cell_module, "arrays", ()) or ():
        category = getattr(getattr(array, "config", None), "ieee_1547_category", None)
        if category in (1, 2, 3) and getattr(array, "blocks", None):
            return True
    return False


def unprotected_island_warning(site) -> dict | None:
    if protection_is_configured(site):
        return None
    return {
        # PROPOSED_HERE: stable warning identity; no validation or trip condition.
        "code": "islanded_frequency_protection_unconfigured",
        "message": "islanded run without frequency protection configured",
    }
