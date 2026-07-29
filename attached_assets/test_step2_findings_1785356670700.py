"""
Step 2 acceptance test — the hardware-profile gap found by the skeleton audit.

Build Plan v2.2 assigns counting_unit and vintage to Step 2 (persistence and data
model), not Step 3. This test lived in test_step3_findings.py in the v2.1 package
and is split out here so each file maps cleanly to one step.

Expected on the unmodified skeleton:  1 failed
Expected after Step 2:                1 passed

Run from gridsignal_sim/:
    PYTHONPATH=. python -m pytest ../audit_tests/test_step2_findings.py -v
"""

from __future__ import annotations

from core.models import HardwareProfile


# ---------------------------------------------------------------------------
# C-3 — counting unit and profile vintage   [v2.5 §5.2, §5.3]
# ---------------------------------------------------------------------------

def test_hardware_profile_carries_counting_unit_and_vintage():
    """v2.5 §5.2: every profile declares the unit node_count is expressed in.
    A site reporting dies against a profile assuming packages produces a forecast
    off by exactly 2x, with no symptom other than persistent forecast error
    (TC-53).

    v2.5 §5.3: every profile carries a vintage. Forecasting a current-generation
    cabinet against a two-generation-old profile under-predicts by 60-90 kW per
    cabinet, so ten racks silently exceed the §4.4 prediction threshold (TC-54).
    """
    fields = set(HardwareProfile.__dataclass_fields__)
    missing = {"counting_unit", "vintage_generation", "vintage_established"} - fields
    assert not missing, (
        f"HardwareProfile is missing {sorted(missing)}; fields are {sorted(fields)}"
    )
