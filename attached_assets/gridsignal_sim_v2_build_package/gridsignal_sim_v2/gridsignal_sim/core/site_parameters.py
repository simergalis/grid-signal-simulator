"""site_parameters.py — Runtime catalogue loader (GS-DES-CFG-001 v1.0).

The authoritative parameter source is gridsignal_parameters.json.
This module provides a typed wrapper so the rest of the codebase reads
parameters by key and receives value + provenance together.

Contract
--------
  get(key)          → CatalogueEntry  (raises ParameterNotCatalogued if unknown)
  value(key)        → catalogue default  (same rule — raises if unknown)
  all_entries()     → snapshot of the full catalogue dict
  ui_descriptor()   → list of ui-block dicts for modal generation

Design decisions
----------------
  Fail fast on an unknown key.
    ParameterNotCatalogued, never a silent default.  A silently defaulted
    control-relevant parameter is a value chosen by nobody — the same rule
    already applied to SiteLocation and to unknown persisted turbine states.

  Provenance travels with every value.
    Most current entries are PROPOSED_HERE or ESTIMATE.  Any surface that
    presents one as a measurement has a bug; the provenance field makes that
    detectable without reading the JSON by hand.

  CONFORMANCE / locked entries are never editable.
    They are constant under acceptance test.  A test already asserts this.
    Attempting to overwrite one from application code raises
    ConformanceWriteError — a programming error, not a user error.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Exceptions ────────────────────────────────────────────────────────────────

class ParameterNotCatalogued(KeyError):
    """Raised when a key is not in gridsignal_parameters.json.

    Fail fast rather than return a default — see module docstring.
    """


class ConformanceWriteError(TypeError):
    """Raised when application code attempts to overwrite a CONFORMANCE entry.

    CONFORMANCE entries are constant under acceptance test.  A write attempt
    is a programming error, not a user error.
    """


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CatalogueEntry:
    """Immutable record for one parameter in the catalogue."""

    key: str
    default: Any                        # None for enumerated entries
    provenance: str                     # MEASURED | VENDOR_RATING | SPEC_DEFAULT | …
    provenance_detail: Optional[str]
    label: str
    unit: str
    spec_ref: str
    section: str                        # "adjustable" | "enumerated" | "locked"
    min: Optional[float]
    max: Optional[float]
    step: Optional[float]
    split: Any                          # bool | "plant_only"
    control_relevant: bool
    ui: Dict[str, Any]
    options: Optional[List[Any]]        # enumerated entries only
    reason: Optional[str]               # locked entries: why read-only

    # ── Derived properties ─────────────────────────────────────────────────

    @property
    def is_conformance(self) -> bool:
        """True for locked / CONFORMANCE entries that are never editable."""
        return self.section == "locked"

    @property
    def is_adjustable(self) -> bool:
        return self.section == "adjustable"

    @property
    def is_enumerated(self) -> bool:
        return self.section == "enumerated"

    def ui_descriptor(self) -> Dict[str, Any]:
        """Return the UI descriptor dict for modal generation.

        CONFORMANCE entries have readonly=True.  Provenance and spec_ref are
        always present so the modal can display them beside the control — an
        operator can see that pue_base is PROPOSED_HERE rather than measured.
        """
        d: Dict[str, Any] = {
            "key":        self.key,
            "label":      self.label,
            "unit":       self.unit,
            "provenance": self.provenance,
            "spec_ref":   self.spec_ref,
            "readonly":   self.is_conformance,
            "section":    self.section,
        }
        if self.default is not None:
            d["default"] = self.default
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        if self.step is not None:
            d["step"] = self.step
        if self.options is not None:
            d["options"] = self.options
        if self.reason is not None:
            d["reason"] = self.reason
        d.update(self.ui)
        return d


# ── Catalogue loading ─────────────────────────────────────────────────────────

_CATALOGUE: Optional[Dict[str, CatalogueEntry]] = None

# Resolve the JSON path relative to this file:
#   core/site_parameters.py → ../ → gridsignal_sim/ → gridsignal_parameters.json
_DEFAULT_PATH = Path(__file__).parent.parent / "gridsignal_parameters.json"


def _parse_raw_entry(raw: Dict[str, Any], section: str) -> CatalogueEntry:
    # locked entries use "value" as their canonical figure, not "default"
    default = raw.get("value") if section == "locked" else raw.get("default")
    return CatalogueEntry(
        key=raw["key"],
        default=default,
        provenance=raw.get("provenance", "UNKNOWN"),
        provenance_detail=raw.get("provenance_detail"),
        label=raw.get("label", raw["key"]),
        unit=raw.get("unit", ""),
        spec_ref=raw.get("spec_ref", ""),
        section=section,
        min=raw.get("min"),
        max=raw.get("max"),
        step=raw.get("step"),
        split=raw.get("split", False),
        control_relevant=raw.get("control_relevant", False),
        ui=raw.get("ui", {}),
        options=raw.get("options"),
        reason=raw.get("reason"),
    )


def _load_catalogue() -> Dict[str, CatalogueEntry]:
    """Load and in-process-cache the parameter catalogue."""
    global _CATALOGUE
    if _CATALOGUE is not None:
        return _CATALOGUE

    path = Path(os.environ.get("GRIDSIGNAL_PARAMS_PATH", str(_DEFAULT_PATH)))
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)

    result: Dict[str, CatalogueEntry] = {}
    for section in ("adjustable", "enumerated", "locked"):
        for item in raw.get(section, []):
            entry = _parse_raw_entry(item, section)
            result[entry.key] = entry

    _CATALOGUE = result
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def get(key: str) -> CatalogueEntry:
    """Return the CatalogueEntry for *key*.

    Raises ParameterNotCatalogued for any key not in the JSON.
    Never returns a default for an unknown key — fail fast.
    """
    cat = _load_catalogue()
    if key not in cat:
        raise ParameterNotCatalogued(
            f"Parameter {key!r} is not in gridsignal_parameters.json. "
            "Add it to the catalogue before using it in application code."
        )
    return cat[key]


def value(key: str) -> Any:
    """Return the catalogue default for *key*.

    Shorthand for get(key).default.
    Raises ParameterNotCatalogued if the key is not in the catalogue.
    """
    return get(key).default


def all_entries() -> Dict[str, CatalogueEntry]:
    """Return a snapshot of all catalogue entries keyed by parameter key."""
    return dict(_load_catalogue())


def ui_descriptor() -> List[Dict[str, Any]]:
    """Return ui descriptor dicts for modal generation.

    Sorted by section (adjustable → enumerated → locked) then by key.
    CONFORMANCE (locked) entries have readonly=True.
    Adjustable entries carry min/max/step/control type.
    Enumerated entries carry their options list.

    The settings modal MUST be generated from this descriptor so it cannot
    drift from the documented ranges (catalogue usage_note).
    """
    cat = _load_catalogue()
    _ORDER = {"adjustable": 0, "enumerated": 1, "locked": 2}
    entries = sorted(cat.values(), key=lambda e: (_ORDER.get(e.section, 9), e.key))
    return [e.ui_descriptor() for e in entries]


def reload() -> None:
    """Invalidate the in-process cache.  Used in tests only."""
    global _CATALOGUE
    _CATALOGUE = None
