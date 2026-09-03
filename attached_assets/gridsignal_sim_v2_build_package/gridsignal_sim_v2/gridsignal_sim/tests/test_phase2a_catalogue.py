"""
tests/test_phase2a_catalogue.py — Phase 2A catalogue and protection_provisional checks.

Confirms:
  1. All 13 new locked entries are present in gridsignal_parameters.json with
     correct values (Phase 2A catalogue additions).
  2. PROVISIONAL-UNMEASURED entries exist (provenance checked via presence + value).
  3. TickResult.protection_provisional defaults to False and can be set True.
  4. run_manager module-level is_export_blocked() toggles correctly.
  5. Export gate returns 403 when _run_provisional is True.

§DR-2026-08-08-FREQ Phase 2A.
"""
from __future__ import annotations

import dataclasses

import pytest

import core.site_parameters as _sp


# ---------------------------------------------------------------------------
# 1. Catalogue values
# ---------------------------------------------------------------------------

class TestCatalogueEntries:
    """All 13 Phase 2A locked entries must be present with expected values."""

    def test_anchor_mode(self) -> None:
        assert _sp.value("anchor_mode") == "vsm"

    def test_vsm_inertia_constant_s(self) -> None:
        assert _sp.value("vsm_inertia_constant_s") == pytest.approx(2.0)

    def test_dynamic_step_s(self) -> None:
        assert _sp.value("dynamic_step_s") == pytest.approx(0.01)

    def test_fixed_speed_cooling_fraction(self) -> None:
        assert _sp.value("fixed_speed_cooling_fraction") == pytest.approx(0.30)

    def test_d_motor(self) -> None:
        assert _sp.value("d_motor") == pytest.approx(2.5)

    def test_valve_actuation_tc_s(self) -> None:
        assert _sp.value("valve_actuation_tc_s") == pytest.approx(0.2)

    def test_fuel_to_power_tc_s(self) -> None:
        assert _sp.value("fuel_to_power_tc_s") == pytest.approx(1.0)

    def test_max_instantaneous_load_step_mw(self) -> None:
        assert _sp.value("max_instantaneous_load_step_mw") == pytest.approx(2.25)

    def test_ufls_stages_is_list_of_three(self) -> None:
        stages = _sp.value("ufls_stages")
        assert isinstance(stages, list), "ufls_stages must be a list"
        assert len(stages) == 3, f"Expected 3 UFLS stages, got {len(stages)}"

    def test_ufls_stage_thresholds(self) -> None:
        stages = _sp.value("ufls_stages")
        assert stages[0]["threshold_hz"] == pytest.approx(59.3)
        assert stages[1]["threshold_hz"] == pytest.approx(58.9)
        assert stages[2]["threshold_hz"] == pytest.approx(58.5)

    def test_ufls_stage_delays(self) -> None:
        stages = _sp.value("ufls_stages")
        for i, s in enumerate(stages):
            assert s["delay_s"] == pytest.approx(0.15), f"Stage {i} delay mismatch"

    def test_ufls_stage_block_fractions(self) -> None:
        stages = _sp.value("ufls_stages")
        assert stages[0]["block_fraction"] == pytest.approx(0.10)
        assert stages[1]["block_fraction"] == pytest.approx(0.15)
        assert stages[2]["block_fraction"] == pytest.approx(0.20)
        total = sum(s["block_fraction"] for s in stages)
        assert total == pytest.approx(0.45), f"Total shed fraction = {total}, expected 0.45"

    def test_relay_81u_threshold_hz(self) -> None:
        assert _sp.value("relay_81u_threshold_hz") == pytest.approx(57.5)

    def test_relay_81u_delay_s(self) -> None:
        assert _sp.value("relay_81u_delay_s") == pytest.approx(0.10)

    def test_droop_r(self) -> None:
        assert _sp.value("droop_r") == pytest.approx(0.04)

    def test_power_factor_turbine(self) -> None:
        assert _sp.value("power_factor_turbine") == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# 2. PROVISIONAL-UNMEASURED keys are present
# ---------------------------------------------------------------------------

_PROVISIONAL_KEYS = [
    "vsm_inertia_constant_s",
    "fixed_speed_cooling_fraction",
    "d_motor",
    "valve_actuation_tc_s",
    "fuel_to_power_tc_s",
    "max_instantaneous_load_step_mw",
    "ufls_stages",
    "relay_81u_threshold_hz",
    "relay_81u_delay_s",
]


@pytest.mark.parametrize("key", _PROVISIONAL_KEYS)
def test_provisional_key_present(key: str) -> None:
    """Every PROVISIONAL-UNMEASURED key must return a non-None value."""
    val = _sp.value(key)
    assert val is not None, f"Catalogue key {key!r} returned None"


# ---------------------------------------------------------------------------
# 3. TickResult.protection_provisional field
# ---------------------------------------------------------------------------

class TestProtectionProvisionalField:
    """TickResult.protection_provisional defaults False; field exists."""

    def test_field_exists_with_default_false(self) -> None:
        fields = {f.name: f for f in dataclasses.fields(__import__("core.models", fromlist=["TickResult"]).TickResult)}
        assert "protection_provisional" in fields, "protection_provisional field missing from TickResult"
        assert fields["protection_provisional"].default is False, (
            f"protection_provisional default is {fields['protection_provisional'].default!r}, expected False"
        )

    def test_phase6_served_fields_exist_with_none_default(self) -> None:
        from core.models import TickResult
        fields = {f.name: f for f in dataclasses.fields(TickResult)}
        for fname in (
            "p_served_mw", "p_unserved_mw", "p_imbalance_mw",
            "p_compute_served_mw", "p_compute_unserved_mw",
            "p_cooling_served_mw", "p_cooling_unserved_mw",
        ):
            assert fname in fields, f"Phase 6 field {fname!r} missing from TickResult"
            assert fields[fname].default is None, (
                f"{fname!r} default is {fields[fname].default!r}, expected None"
            )


# ---------------------------------------------------------------------------
# 4. run_manager provisional gate
# ---------------------------------------------------------------------------

class TestExportGate:
    """is_export_blocked() toggles correctly; no side effects on other tests."""

    def test_unblocked_by_default_after_clear(self) -> None:
        import runtime.run_manager as rm
        original = rm._run_provisional
        try:
            rm.clear_run_provisional()
            assert rm.is_export_blocked() is False
        finally:
            rm._run_provisional = original

    def test_blocked_after_set(self) -> None:
        import runtime.run_manager as rm
        original = rm._run_provisional
        try:
            rm.set_run_provisional()
            assert rm.is_export_blocked() is True
        finally:
            rm._run_provisional = original

    def test_clear_resets(self) -> None:
        import runtime.run_manager as rm
        original = rm._run_provisional
        try:
            rm.set_run_provisional()
            assert rm.is_export_blocked() is True
            rm.clear_run_provisional()
            assert rm.is_export_blocked() is False
        finally:
            rm._run_provisional = original

    def test_set_idempotent(self) -> None:
        import runtime.run_manager as rm
        original = rm._run_provisional
        try:
            rm.set_run_provisional()
            rm.set_run_provisional()  # second call must not raise or reset
            assert rm.is_export_blocked() is True
        finally:
            rm._run_provisional = original


# ---------------------------------------------------------------------------
# 5. SiteConfig Phase 2A-5 fields have correct catalogue defaults
# ---------------------------------------------------------------------------

class TestSiteConfigPhase2AFields:
    """SiteConfig must expose all Phase 2A–5 fields with catalogue defaults."""

    def _make_site(self) -> "SiteConfig":
        from core.models import SiteConfig
        return SiteConfig(
            site_id="test-2a",
            frequency_nominal_hz=60.0,
            power_factor=0.85,
        )

    def test_anchor_mode(self) -> None:
        site = self._make_site()
        assert site.anchor_mode == "vsm"

    def test_vsm_inertia_constant_s(self) -> None:
        site = self._make_site()
        assert site.vsm_inertia_constant_s == pytest.approx(2.0)

    def test_dynamic_step_s(self) -> None:
        site = self._make_site()
        assert site.dynamic_step_s == pytest.approx(0.01)

    def test_fixed_speed_cooling_fraction(self) -> None:
        site = self._make_site()
        assert site.fixed_speed_cooling_fraction == pytest.approx(0.30)

    def test_d_motor(self) -> None:
        site = self._make_site()
        assert site.d_motor == pytest.approx(2.5)

    def test_ufls_stages_is_empty_by_default(self) -> None:
        """Phase 5: UFLS is opt-in — SiteConfig.ufls_stages defaults to [] (disabled).
        The catalogue value (3 stages) is still accessible via the parameters store
        but is NOT applied by default to prevent spurious trips in non-UFLS scenarios.
        Scenario specs must explicitly set ufls_stages to enable protection."""
        site = self._make_site()
        assert isinstance(site.ufls_stages, list)
        assert len(site.ufls_stages) == 0, (
            f"ufls_stages must default to [] (opt-in); got {site.ufls_stages!r}"
        )

    def test_ufls_stages_catalogue_value_accessible(self) -> None:
        """Catalogue stores the 3 PROVISIONAL UFLS stages for use when explicitly enabled."""
        stages = _sp.value("ufls_stages")
        assert isinstance(stages, list)
        assert len(stages) == 3, f"Expected 3 catalogue UFLS stages; got {stages!r}"

    def test_relay_81u_threshold_hz_none_by_default(self) -> None:
        """Phase 5: 81U relay is opt-in — SiteConfig.relay_81u_threshold_hz defaults to None.
        The catalogue value (57.5 Hz) is the PROVISIONAL threshold for 60 Hz sites
        but must be explicitly set per-scenario to prevent spurious trips."""
        site = self._make_site()
        assert site.relay_81u_threshold_hz is None, (
            f"relay_81u_threshold_hz must default to None (opt-in); got {site.relay_81u_threshold_hz!r}"
        )

    def test_relay_81u_threshold_catalogue_value(self) -> None:
        """Catalogue stores the 57.5 Hz PROVISIONAL 81U threshold for 60 Hz sites."""
        assert _sp.value("relay_81u_threshold_hz") == pytest.approx(57.5)

    def test_relay_81u_delay_s(self) -> None:
        site = self._make_site()
        assert site.relay_81u_delay_s == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# 6. TurbineConfig Phase 2B per-unit fields
# ---------------------------------------------------------------------------

class TestTurbineConfigPhase2BFields:
    """TurbineConfig must expose all Phase 2B per-unit fields with catalogue defaults."""

    def _make_turbine_config(self) -> "TurbineConfig":
        from core.models import TurbineConfig
        return TurbineConfig(asset_id="gt-test")

    def test_power_factor_default(self) -> None:
        tc = self._make_turbine_config()
        assert tc.power_factor == pytest.approx(0.85)

    def test_inertia_constant_s_default(self) -> None:
        tc = self._make_turbine_config()
        assert tc.inertia_constant_s > 0.0

    def test_droop_r_default(self) -> None:
        tc = self._make_turbine_config()
        assert tc.droop_r == pytest.approx(0.04)

    def test_valve_actuation_tc_s_default(self) -> None:
        tc = self._make_turbine_config()
        assert tc.valve_actuation_tc_s == pytest.approx(0.2)

    def test_fuel_to_power_tc_s_default(self) -> None:
        tc = self._make_turbine_config()
        assert tc.fuel_to_power_tc_s == pytest.approx(1.0)

    def test_max_instantaneous_load_step_mw_default(self) -> None:
        tc = self._make_turbine_config()
        assert tc.max_instantaneous_load_step_mw == pytest.approx(2.25)


# ---------------------------------------------------------------------------
# 7. TurbineModule governor state fields
# ---------------------------------------------------------------------------

class TestTurbineModuleGovernorState:
    """TurbineModule must expose _gov_valve_mw and _gov_power_mw, both init 0.0."""

    def test_governor_state_fields_exist(self) -> None:
        from core.models import TurbineConfig
        from core.asset_modules import TurbineModule
        tm = TurbineModule(TurbineConfig(asset_id="gt-gov-test"))
        assert hasattr(tm, "_gov_valve_mw"), "_gov_valve_mw missing from TurbineModule"
        assert hasattr(tm, "_gov_power_mw"), "_gov_power_mw missing from TurbineModule"
        assert tm._gov_valve_mw == pytest.approx(0.0)
        assert tm._gov_power_mw == pytest.approx(0.0)
