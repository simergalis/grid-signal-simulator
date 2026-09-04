"""
tests/test_step8_scenarios.py — Step 8: Scenario Builder + Asset Configuration.

Covers:
  A-fix  TC-33 delta_p uses PUE-adjusted compute (6.3036 MW, not 6.12 MW).
  B-fix  SOLAR_STEP triggers stage_for_predicted_step through apply_workload_signal.
  C-fix  D12/PROTO-9 C-rate guard: out-of-range warns, never 400.
  D-fix  ScenarioStore aligned with Step 2 Scenario ORM entity shape.
  E-fix  §7.1.2 single grid_forming anchor validated on ScenarioSpec.
  Minor  IrradianceProfile zero-order hold; irradiance_steps convention.
  CRUD   POST / GET list / GET detail / PUT / DELETE /scenarios.
  Seeded demo-fleet, demo-tc33-compute, demo-tc33-renewable present.
  StartRunRequest: scenario_id path; scenario_preset removed (422).
"""

from __future__ import annotations

import json
import warnings as _warnings

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.schemas import BessUnitSpec, ScenarioSpec, TurbineUnitSpec, WorkloadEventSpec
from core.asset_modules import IrradianceProfile
from core.generation_factory import (
    compute_floor_mw as _compute_floor_mw,
    peak_compute_mw as _peak_compute_mw,
    _GPU_TDP_MW,
)
from core.models import (
    BessConfig,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from core.simulation_core import SimulationState
from runtime.scenario_factory import (
    DEFAULT_HARDWARE_LIBRARY,
    build_run_context_from_spec,
)
from core.asset_modules import (
    BessModule,
    CoolingModule,
    GPUModule,
    IrradianceProfile,
    SolarModule,
    TurbineModule,
)
from core.models import BessConfig, SiteConfig, SolarConfig, TurbineConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NODES = 600
_ENT_KW = 10.2
_PUE = 1.03
_TC33_MW = _NODES * _ENT_KW * _PUE / 1000.0   # 6.3036 MW (correction A)


def _app_client() -> TestClient:
    return TestClient(create_app())


def _minimal_spec(**overrides) -> ScenarioSpec:
    """ScenarioSpec with one BESS and one turbine — minimal valid."""
    return ScenarioSpec(
        name=overrides.pop("name", "test"),
        description=overrides.pop("description", ""),
        workload_events=overrides.pop("workload_events", [
            WorkloadEventSpec(event_id="e0", job_id="job", event_type="starting",
                              timestamp=0.0, node_count=1),
        ]),
        bess_units=overrides.pop("bess_units", [
            BessUnitSpec(asset_id="bess-0", rated_mw=5.0, usable_mwh=2.0),
        ]),
        turbine_units=overrides.pop("turbine_units", [
            TurbineUnitSpec(asset_id="turbine-0", rated_mw=10.0),
        ]),
        **overrides,
    )


class TestInternalPathsAreExcludedFromScenarios:
    def test_create_scenario_strips_internal_test_paths_from_all_text(self):
        """Scenario payloads must never preserve implementation-only test paths."""
        paths = (
            "tests/test_unit_trip.py",
            "tests/test_aggregate_sources.py",
            "tests/test_13_2_balance_decomp.py",
        )
        payload = _minimal_spec(
            name=f"Operator validation {paths[0]}",
            description=f"Exercise reserve behavior. {paths[1]} is not operator content.",
            demo_description=f"Watch the turbine response; ignore {paths[2]}.",
        ).model_dump()
        payload["generator_config"] = {"note": f"Do not retain {paths[0]} in exports."}

        with _app_client() as client:
            created = client.post("/scenarios", json=payload)
            assert created.status_code == 201, created.text

            detail = client.get(f"/scenarios/{created.json()['scenario_id']}")
            assert detail.status_code == 200, detail.text

        serialized = json.dumps(detail.json()["spec"])
        for path in paths:
            assert path not in serialized


# ---------------------------------------------------------------------------
# Minor fix: IrradianceProfile zero-order hold
# ---------------------------------------------------------------------------

class TestIrradianceZeroOrderHold:
    def test_constant_single_sample(self):
        ip = IrradianceProfile([(0.0, 1.0)])
        assert ip.fraction_at(-5.0) == pytest.approx(1.0)
        assert ip.fraction_at(0.0)  == pytest.approx(1.0)
        assert ip.fraction_at(1000.0) == pytest.approx(1.0)

    def test_step_down_at_30(self):
        """[(0.0, 1.0), (30.0, 0.0)] — zero-order hold, not interpolated."""
        ip = IrradianceProfile([(0.0, 1.0), (30.0, 0.0)])
        assert ip.fraction_at(0.0)  == pytest.approx(1.0)
        assert ip.fraction_at(15.0) == pytest.approx(1.0)   # NOT 0.5 (no interp)
        assert ip.fraction_at(29.9) == pytest.approx(1.0)
        assert ip.fraction_at(30.0) == pytest.approx(0.0)   # step exactly at 30
        assert ip.fraction_at(60.0) == pytest.approx(0.0)

    def test_constant_two_samples(self):
        ip = IrradianceProfile([(0.0, 1.0), (300.0, 1.0)])
        assert ip.fraction_at(150.0) == pytest.approx(1.0)

    def test_before_first_anchor(self):
        ip = IrradianceProfile([(10.0, 0.5), (20.0, 0.0)])
        # Before first anchor: return first sample's value
        assert ip.fraction_at(0.0) == pytest.approx(0.5)

    def test_duplicate_timestamps_last_wins(self):
        """If two samples share a timestamp, the last (by sort order) wins.

        sorted() on tuples sorts element-by-element, so (30.0, 0.0) sorts
        BEFORE (30.0, 1.0).  The loop advances through both and returns the
        LAST value encountered, which is 1.0 — the higher fraction wins for
        equal timestamps.  Duplicate timestamps are unnecessary in practice;
        this test documents the tiebreak behaviour.
        """
        ip = IrradianceProfile([(0.0, 1.0), (30.0, 1.0), (30.0, 0.0)])
        # sorted order: [(0.0,1.0), (30.0,0.0), (30.0,1.0)]
        # last value at t=30 is 1.0
        assert ip.fraction_at(30.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# B-fix: SOLAR_STEP triggers staging through apply_workload_signal
# ---------------------------------------------------------------------------

def _build_site() -> SiteConfig:
    return SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="site-tc33")


def _build_sim_state_with_solar(solar_mw: float = 0.0) -> SimulationState:
    """Build a minimal SimulationState for TC-33 tests.

    BESS is deliberately tiny (usable_mwh=0.01) so that max_sustainable_seconds
    is short enough for the compute gap (≈16.5 s) to exceed it.  The renewable
    alert fires via the D14 power-limited check (peak_shortfall > fleet ceiling).

    Arithmetic (grid_forming=False → no anchor deduction, ceiling=5.0 MW):
      compute case:  peak_shortfall = 6.3036 - 0.2×15 = 3.3036 MW
                     3.3036 ≤ fleet ceiling 5.0 → endurance check:
                     max_sustainable = 0.01/3.3036 × 3600 = 10.9 s < gap=16.5 s → ALERT ✓
      renewable case: peak_shortfall = 6.3036 MW > fleet ceiling 5.0 MW
                     → power-limited early-return (D14) → ALERT ✓
                     (usable_mwh is irrelevant for this path)
    """
    site = _build_site()
    solar_arrays = []
    if solar_mw > 0:
        solar_arrays = [SolarModule(
            SolarConfig(asset_id="solar-0", rated_mw=solar_mw),
            irradiance_profile=IrradianceProfile([(0.0, 1.0)]),
        )]
    return SimulationState(
        run_id="tc33-test",
        site=site,
        gpu_modules=[GPUModule(asset_id="gpu-0", site=site, hardware_library=DEFAULT_HARDWARE_LIBRARY)],
        turbines=[TurbineModule(TurbineConfig(asset_id="turbine-0", rated_mw=25.0, r_asset_mw_per_s=0.2))],
        # tiny BESS: enough power to attempt bridging, but not enough energy to sustain
        bess_units=[BessModule(BessConfig(asset_id="bess-0", rated_mw=5.0, usable_mwh=0.01))],
        solar_arrays=solar_arrays,
        cooling=CoolingModule(asset_id="cooling-0", site=site),
    )


class TestSolarStepTriggersStaging:
    def test_solar_step_sets_pending_alert(self):
        """SOLAR_STEP must call stage_for_predicted_step and set _pending_alert."""
        sim = _build_sim_state_with_solar(solar_mw=0.0)
        signal = WorkloadSignal(
            event_id="solar-step",
            job_id="",
            event_type=WorkloadEventType.SOLAR_STEP,
            timestamp=30.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=0,
            workload_class=WorkloadClass.TRAINING,
            site_id="site-tc33",
            renewable_shortfall_mw=_TC33_MW,
        )
        assert sim._pending_alert is None, "should start with no pending alert"
        sim.apply_workload_signal(signal, dt_lead_seconds=0.0)
        assert sim._pending_alert is not None, "SOLAR_STEP must set pending alert"

    def test_solar_step_does_not_touch_gpu_state(self):
        """SOLAR_STEP early-return must leave GPU modules unchanged."""
        sim = _build_sim_state_with_solar(solar_mw=0.0)
        gpu_output_before = sum(g.output_mw() for g in sim.gpu_modules)
        signal = WorkloadSignal(
            event_id="solar-step",
            job_id="",
            event_type=WorkloadEventType.SOLAR_STEP,
            timestamp=30.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=0,
            workload_class=WorkloadClass.TRAINING,
            site_id="site-tc33",
            renewable_shortfall_mw=_TC33_MW,
        )
        sim.apply_workload_signal(signal, dt_lead_seconds=0.0)
        gpu_output_after = sum(g.output_mw() for g in sim.gpu_modules)
        assert gpu_output_before == pytest.approx(gpu_output_after)


# ---------------------------------------------------------------------------
# A-fix + TC-33 symmetry: compute and renewable produce the same delta_p
# ---------------------------------------------------------------------------

class TestTC33Symmetry:
    def test_tc33_delta_p_is_pue_adjusted(self):
        """Correction A: 600 nodes × 10.2 kW × 1.03 PUE = 6.3036 MW (not 6.12)."""
        expected = 600 * 10.2 * 1.03 / 1000.0
        assert expected == pytest.approx(6.3036, rel=1e-6)
        assert _TC33_MW == pytest.approx(expected, rel=1e-6)

    def test_compute_path_fires_alert(self):
        """TC-33 compute: STARTING at t=30 with dt_lead=15s → gap > 0 → alert."""
        sim = _build_sim_state_with_solar(solar_mw=0.0)
        # Queue the job into the GPU first so target_output_mw() works
        starting = WorkloadSignal(
            event_id="starting",
            job_id="job-tc33c",
            event_type=WorkloadEventType.STARTING,
            timestamp=30.0,
            hardware_profile_id="enterprise_8gpu_air",
            node_count=600,
            workload_class=WorkloadClass.TRAINING,
            site_id="site-tc33",
        )
        sim.apply_workload_signal(starting, dt_lead_seconds=15.0)
        # required_ramp = 6.3036 / 0.2 = 31.518 s; gap = 31.518 - 15 = 16.518 s > 0
        assert sim._pending_alert is not None, "compute step must fire alert"

    def test_renewable_path_fires_alert_with_larger_gap(self):
        """TC-33 renewable: SOLAR_STEP at t=30 with dt_lead=0 → gap > 0 → alert.
        Gap is larger than compute case (31.518 s vs 16.518 s), so renewable
        shortfall ≥ compute shortfall for equal delta_p."""
        sim_compute = _build_sim_state_with_solar(solar_mw=0.0)
        sim_renew   = _build_sim_state_with_solar(solar_mw=0.0)

        starting = WorkloadSignal(
            event_id="start-c", job_id="job-tc33c",
            event_type=WorkloadEventType.STARTING, timestamp=30.0,
            hardware_profile_id="enterprise_8gpu_air", node_count=600,
            workload_class=WorkloadClass.TRAINING, site_id="site-tc33",
        )
        solar_step = WorkloadSignal(
            event_id="solar", job_id="",
            event_type=WorkloadEventType.SOLAR_STEP, timestamp=30.0,
            hardware_profile_id="enterprise_8gpu_air", node_count=0,
            workload_class=WorkloadClass.TRAINING, site_id="site-tc33",
            renewable_shortfall_mw=_TC33_MW,
        )

        sim_compute.apply_workload_signal(starting, dt_lead_seconds=15.0)
        sim_renew.apply_workload_signal(solar_step, dt_lead_seconds=0.0)

        # Both must alert
        assert sim_compute._pending_alert is not None
        assert sim_renew._pending_alert is not None

        # Renewable gap (31.518 s) > compute gap (16.518 s) →
        # renewable shortfall_mw >= compute shortfall_mw
        assert (sim_renew._pending_alert.shortfall_mw
                >= sim_compute._pending_alert.shortfall_mw)

    def test_solar_event_type_is_defined(self):
        """WorkloadEventType.SOLAR_STEP must exist."""
        assert WorkloadEventType.SOLAR_STEP == "solar_step"


# ---------------------------------------------------------------------------
# C-fix: D12/PROTO-9 C-rate guard
# ---------------------------------------------------------------------------

class TestCRateGuard:
    def test_valid_c_rate_no_warning(self):
        cfg = BessConfig(asset_id="bess-0", rated_mw=5.0, usable_mwh=2.5)   # 2.0 C
        with _warnings.catch_warnings(record=True) as w:
            _warnings.simplefilter("always")
            cfg2 = BessConfig(asset_id="bess-0", rated_mw=5.0, usable_mwh=2.5)
        assert all("C-rate" not in str(x.message) for x in w)

    def test_low_c_rate_warns(self):
        with _warnings.catch_warnings(record=True) as w:
            _warnings.simplefilter("always")
            BessConfig(asset_id="bess-bad", rated_mw=1.0, usable_mwh=10.0)  # 0.1 C
        assert any("C-rate" in str(x.message) for x in w)
        assert any("PROTO-9" in str(x.message) for x in w)

    def test_high_c_rate_warns(self):
        with _warnings.catch_warnings(record=True) as w:
            _warnings.simplefilter("always")
            BessConfig(asset_id="bess-bad", rated_mw=20.0, usable_mwh=2.0)  # 10.0 C
        assert any("C-rate" in str(x.message) for x in w)

    def test_api_c_rate_warning_not_400(self):
        """D12: out-of-range C-rate → 201 with warning field, never 400."""
        with TestClient(create_app()) as client:
            spec = _minimal_spec(
                name="high-c",
                bess_units=[
                    BessUnitSpec(asset_id="bess-0", rated_mw=20.0, usable_mwh=1.0),  # 20.0 C
                ],
            )
            resp = client.post("/scenarios", json=spec.model_dump())
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["c_rate_warnings"]) >= 1
        assert "PROTO-9" in data["c_rate_warnings"][0]

    def test_api_valid_c_rate_no_warnings(self):
        with TestClient(create_app()) as client:
            spec = _minimal_spec(
                name="ok-c",
                bess_units=[
                    BessUnitSpec(asset_id="bess-0", rated_mw=5.0, usable_mwh=2.5),  # 2.0 C
                ],
            )
            resp = client.post("/scenarios", json=spec.model_dump())
        assert resp.status_code == 201
        assert resp.json()["c_rate_warnings"] == []


# ---------------------------------------------------------------------------
# E-fix: §7.1.2 single grid_forming anchor
# ---------------------------------------------------------------------------

class TestGridFormingConstraint:
    def test_two_grid_forming_units_rejected(self):
        with pytest.raises(ValueError, match="§7.1.2"):
            ScenarioSpec(
                name="bad",
                workload_events=[WorkloadEventSpec(event_id="e", job_id="j", event_type="starting",
                                                   timestamp=0.0, node_count=1)],
                bess_units=[
                    BessUnitSpec(asset_id="bess-0", rated_mw=5.0, usable_mwh=2.0, grid_forming=True),
                    BessUnitSpec(asset_id="bess-1", rated_mw=5.0, usable_mwh=2.0, grid_forming=True),
                ],
                turbine_units=[TurbineUnitSpec(asset_id="t-0")],
            )

    def test_single_grid_forming_accepted(self):
        spec = ScenarioSpec(
            name="ok-anchor",
            workload_events=[WorkloadEventSpec(event_id="e", job_id="j", event_type="starting",
                                               timestamp=0.0, node_count=1)],
            bess_units=[
                BessUnitSpec(asset_id="bess-0", rated_mw=18.0, usable_mwh=8.0, grid_forming=True),
                BessUnitSpec(asset_id="bess-1", rated_mw=5.0,  usable_mwh=2.5, grid_forming=False),
            ],
            turbine_units=[TurbineUnitSpec(asset_id="t-0")],
        )
        forming = [u for u in spec.bess_units if u.grid_forming]
        assert len(forming) == 1

    def test_api_two_grid_forming_returns_422(self):
        with TestClient(create_app()) as client:
            spec_dict = _minimal_spec().model_dump()
            spec_dict["bess_units"] = [
                {"asset_id": "bess-0", "rated_mw": 5.0, "usable_mwh": 2.0,
                 "initial_soc_fraction": 0.95, "grid_forming": True},
                {"asset_id": "bess-1", "rated_mw": 5.0, "usable_mwh": 2.0,
                 "initial_soc_fraction": 0.95, "grid_forming": True},
            ]
            resp = client.post("/scenarios", json=spec_dict)
        assert resp.status_code == 422
        assert "7.1.2" in resp.text


# ---------------------------------------------------------------------------
# Scenario CRUD
# ---------------------------------------------------------------------------

class TestScenarioCRUD:
    def test_create_returns_201_and_id(self):
        with TestClient(create_app()) as client:
            spec = _minimal_spec(name="my-scenario")
            resp = client.post("/scenarios", json=spec.model_dump())
        assert resp.status_code == 201
        body = resp.json()
        assert "scenario_id" in body
        assert body["name"] == "my-scenario"

    def test_list_includes_seeded_and_created(self):
        with TestClient(create_app()) as client:
            # Seeded scenarios present
            resp = client.get("/scenarios")
            assert resp.status_code == 200
            names = {s["name"] for s in resp.json()}
            assert "demo-alert" in names
            assert "demo-fleet" in names
            assert "demo-tc33-compute" in names
            assert "demo-tc33-renewable" in names

            # Create new
            client.post("/scenarios", json=_minimal_spec(name="new-one").model_dump())
            resp2 = client.get("/scenarios")
            names2 = {s["name"] for s in resp2.json()}
            assert "new-one" in names2

    def test_get_detail_returns_spec(self):
        with TestClient(create_app()) as client:
            create_resp = client.post("/scenarios", json=_minimal_spec(name="detail-test").model_dump())
            sid = create_resp.json()["scenario_id"]
            resp = client.get(f"/scenarios/{sid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["spec"]["name"] == "detail-test"
        assert "c_rate_warnings" in body

    def test_get_nonexistent_returns_404(self):
        with TestClient(create_app()) as client:
            resp = client.get("/scenarios/no-such-id")
        assert resp.status_code == 404

    def test_update_changes_name(self):
        with TestClient(create_app()) as client:
            sid = client.post("/scenarios", json=_minimal_spec(name="old").model_dump()).json()["scenario_id"]
            new_spec = _minimal_spec(name="updated").model_dump()
            resp = client.put(f"/scenarios/{sid}", json=new_spec)
            assert resp.status_code == 200
            assert resp.json()["name"] == "updated"

    def test_delete_removes_scenario(self):
        with TestClient(create_app()) as client:
            sid = client.post("/scenarios", json=_minimal_spec(name="to-delete").model_dump()).json()["scenario_id"]
            del_resp = client.delete(f"/scenarios/{sid}")
            assert del_resp.status_code == 204
            get_resp = client.get(f"/scenarios/{sid}")
            assert get_resp.status_code == 404

    def test_delete_nonexistent_returns_404(self):
        with TestClient(create_app()) as client:
            resp = client.delete("/scenarios/ghost-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Seeded scenarios
# ---------------------------------------------------------------------------

class TestSeededScenarios:
    def test_all_seeded_ids_present(self):
        with TestClient(create_app()) as client:
            ids = {s["scenario_id"] for s in client.get("/scenarios").json()}
        expected = {
            "demo-20mw", "demo-alert", "demo-5mw", "demo-baseline",
            "demo-fleet", "demo-tc33-compute", "demo-tc33-renewable",
            "grid-resonance-stress",  # Phase 11.4: preserves near-zero floor
        }
        assert expected <= ids

    def test_demo_fleet_has_two_bess_units(self):
        with TestClient(create_app()) as client:
            detail = client.get("/scenarios/demo-fleet").json()
        bess = detail["spec"]["bess_units"]
        assert len(bess) == 2
        forming = [u for u in bess if u["grid_forming"]]
        assert len(forming) == 1, "exactly one grid-forming anchor"
        assert forming[0]["rated_mw"] == pytest.approx(18.0)

    def test_demo_tc33_solar_is_pue_adjusted(self):
        """Correction A: solar_rated_mw must be PUE-adjusted (6.3036), not raw IT (6.12)."""
        with TestClient(create_app()) as client:
            detail = client.get("/scenarios/demo-tc33-renewable").json()
        solar = detail["spec"]["solar_rated_mw"]
        assert solar == pytest.approx(6.3036, rel=1e-4)
        assert solar != pytest.approx(6.12, rel=1e-3), "must include PUE factor"

    def test_demo_tc33_renewable_has_solar_step_event(self):
        with TestClient(create_app()) as client:
            detail = client.get("/scenarios/demo-tc33-renewable").json()
        evts = detail["spec"]["workload_events"]
        solar_evts = [e for e in evts if e["event_type"] == "solar_step"]
        assert len(solar_evts) == 1
        assert solar_evts[0]["renewable_shortfall_mw"] == pytest.approx(_TC33_MW, rel=1e-4)

    def test_demo_tc33_compute_has_delayed_start(self):
        with TestClient(create_app()) as client:
            detail = client.get("/scenarios/demo-tc33-compute").json()
        evts = detail["spec"]["workload_events"]
        start_evts = [e for e in evts if e["event_type"] == "starting"]
        assert len(start_evts) == 1
        assert start_evts[0]["timestamp"] == pytest.approx(30.0)
        assert start_evts[0]["node_count"] == 600

    def test_demo_tc33_renewable_irradiance_step(self):
        with TestClient(create_app()) as client:
            detail = client.get("/scenarios/demo-tc33-renewable").json()
        steps = detail["spec"]["irradiance_steps"]
        # Should have exactly [(0.0, 1.0), (30.0, 0.0)]
        assert len(steps) == 2
        assert steps[0] == [pytest.approx(0.0), pytest.approx(1.0)]
        assert steps[1] == [pytest.approx(30.0), pytest.approx(0.0)]


# ---------------------------------------------------------------------------
# Phase 11.4 — Workload floor fraction assertions (TC-11.4)
# ---------------------------------------------------------------------------

# JSON-based demo scenario IDs seeded via _seed_json_scenarios().  All of
# these must carry workload_floor_fraction in [0.40, 0.60] as of Phase 11.4.
_JSON_DEMO_IDS = [
    "demo-islanded-ramp",
    "demo-operator-trip",
    "demo-10-tenant-random-gpu",
    "demo-10-tenant-full-ceiling",
    "demo-10-tenant-overload-120pct",
    "demo-grid-fc-bess-shaped-load",
    "demo-20-tenant-contract-breach",
    "demo-turbine-fc-bess-20-tenants-overage",
    "demo-rolling-planning-peaks",
]


class TestWorkloadFloorFraction:
    """TC-11.4 — Validate Phase 11.4 workload_floor_fraction in all demo scenarios."""

    def test_json_demo_scenarios_present(self):
        """All JSON-based demo scenarios must be available in the scenario list."""
        with TestClient(create_app()) as client:
            ids = {s["scenario_id"] for s in client.get("/scenarios").json()}
        missing = set(_JSON_DEMO_IDS) - ids
        assert not missing, f"JSON demo scenarios missing from store: {missing}"

    @pytest.mark.parametrize("scenario_id", _JSON_DEMO_IDS)
    def test_demo_json_floor_fraction_in_range(self, scenario_id: str):
        """Each JSON demo scenario must have workload_floor_fraction in [0.40, 0.60].

        Phase 11.4 raises the floor so the Forecast Quality panel shows a
        realistic actual-vs-forecast gap throughout a run, not just during
        the initial ramp.
        """
        with TestClient(create_app()) as client:
            detail = client.get(f"/scenarios/{scenario_id}").json()
        spec = detail["spec"]
        wff = spec.get("workload_floor_fraction")
        assert wff is not None, (
            f"{scenario_id}: workload_floor_fraction is absent — must be set to 0.40–0.60"
        )
        assert 0.40 <= wff <= 0.60, (
            f"{scenario_id}: workload_floor_fraction={wff!r} is outside [0.40, 0.60]"
        )

    def test_grid_resonance_stress_present(self):
        """Phase 11.4: grid-resonance-stress scenario must be available."""
        with TestClient(create_app()) as client:
            ids = {s["scenario_id"] for s in client.get("/scenarios").json()}
        assert "grid-resonance-stress" in ids

    def test_grid_resonance_stress_low_floor_fraction(self):
        """grid-resonance-stress must preserve the near-zero (≤0.05) floor fraction.

        This scenario retains the pre-Phase-11.4 behaviour so edge-case tests
        can exercise the Forecast Quality panel under near-zero actual load.
        The floor ≈ 0.02 × 6.3036 MW ≈ 0.126 MW ≈ 0.13 MW.
        """
        with TestClient(create_app()) as client:
            detail = client.get("/scenarios/grid-resonance-stress").json()
        spec = detail["spec"]
        wff = spec.get("workload_floor_fraction")
        assert wff is not None, "grid-resonance-stress must have workload_floor_fraction set"
        assert wff <= 0.05, (
            f"grid-resonance-stress floor fraction {wff!r} must be ≤0.05 to "
            f"preserve the near-zero communication-phase floor"
        )
        assert wff == pytest.approx(0.02, rel=1e-4), (
            f"grid-resonance-stress floor fraction expected 0.02, got {wff!r}"
        )


# ---------------------------------------------------------------------------
# Phase 11.4 — Runtime floor tests: computed MW and evaluate_tick() clamp
# ---------------------------------------------------------------------------

class TestGenerationFactoryPeak:
    """TC-11.4 unit tests for core.generation_factory peak / floor helpers."""

    def test_single_job_peak(self):
        """Single STARTING event: peak = nodes × hw_kw × pue / 1000."""
        spec = {
            "workload_floor_fraction": 0.5,
            "workload_events": [
                {"event_type": "starting", "job_id": "job-1",
                 "timestamp": 0.0, "node_count": 100},
            ],
        }
        expected_peak = 100 * 10.2 * 1.03 / 1000.0  # 1.0506 MW
        assert _peak_compute_mw(spec) == pytest.approx(expected_peak, rel=1e-4)
        assert _compute_floor_mw(spec) == pytest.approx(0.5 * expected_peak, rel=1e-4)

    def test_concurrent_multi_job_peak(self):
        """Two overlapping STARTING events: peak uses their *concurrent* sum, not the larger alone."""
        spec = {
            "workload_floor_fraction": 0.5,
            "workload_events": [
                # job-1 starts at t=0 (100 nodes), job-2 at t=10 (200 nodes).
                # No JOB_END in this window → both active simultaneously at t=10.
                {"event_type": "starting", "job_id": "job-1",
                 "timestamp": 0.0, "node_count": 100},
                {"event_type": "starting", "job_id": "job-2",
                 "timestamp": 10.0, "node_count": 200},
            ],
        }
        # Max concurrent: 100 + 200 = 300 nodes
        expected_peak = 300 * 10.2 * 1.03 / 1000.0  # 3.1518 MW
        # The old single-STARTING-max algorithm would have returned 200 * 10.2 * 1.03 / 1000
        old_wrong_peak = 200 * 10.2 * 1.03 / 1000.0
        peak = _peak_compute_mw(spec)
        assert peak == pytest.approx(expected_peak, rel=1e-4), (
            f"Concurrent peak should be {expected_peak:.4f} MW (300 nodes); got {peak:.4f} MW. "
            f"A value near {old_wrong_peak:.4f} MW indicates the old single-event bug."
        )
        assert _compute_floor_mw(spec) == pytest.approx(0.5 * expected_peak, rel=1e-4)

    def test_job_end_removes_nodes_from_concurrent_total(self):
        """After JOB_END, those nodes no longer count toward concurrent peak."""
        spec = {
            "workload_floor_fraction": 0.5,
            "workload_events": [
                {"event_type": "starting", "job_id": "job-1",
                 "timestamp": 0.0, "node_count": 500},
                {"event_type": "job_end", "job_id": "job-1",
                 "timestamp": 10.0, "node_count": 0},
                {"event_type": "starting", "job_id": "job-2",
                 "timestamp": 20.0, "node_count": 100},
            ],
        }
        # Max concurrent: 500 (job-1 alone at t=0); after JOB_END only 100 active
        expected_peak = 500 * 10.2 * 1.03 / 1000.0
        assert _peak_compute_mw(spec) == pytest.approx(expected_peak, rel=1e-4)

    def test_custom_pue_scales_peak_correctly(self):
        """Top-level pue_base is read from spec_data and applied to node power.

        ScenarioSpec serialises pue_base as a top-level field (not nested under
        site_config); build_run_context_from_spec reads it the same way.  This
        test uses the real serialised shape to catch any schema mismatch.
        """
        # Build a real ScenarioSpec with pue_base=1.35 and serialize it to JSON
        # the same way build_run_context_from_spec receives it.
        spec_obj = _minimal_spec(
            name="pue135-test",
            pue_base=1.35,
            workload_floor_fraction=0.5,
            workload_events=[
                WorkloadEventSpec(event_id="e0", job_id="job-1",
                                  event_type="starting", timestamp=0.0, node_count=100),
            ],
        )
        spec_dict = json.loads(spec_obj.model_dump_json())
        # Confirm the PUE landed at the top level (not nested)
        assert spec_dict.get("pue_base") == pytest.approx(1.35, rel=1e-4), (
            f"ScenarioSpec must serialise pue_base at top level; "
            f"got spec_dict['pue_base']={spec_dict.get('pue_base')!r}"
        )
        # PUE 1.35, not 1.03: 100 * 10.2 * 1.35 / 1000 = 1.377 MW
        expected_peak = 100 * 10.2 * 1.35 / 1000.0
        default_pue_peak = 100 * 10.2 * 1.03 / 1000.0
        peak = _peak_compute_mw(spec_dict)
        assert peak == pytest.approx(expected_peak, rel=1e-4), (
            f"PUE 1.35 peak should be {expected_peak:.4f} MW; got {peak:.4f} MW. "
            f"A value near {default_pue_peak:.4f} MW means PUE was not read from spec."
        )

    def test_tenant_event_peak_uses_concurrent_not_total(self):
        """Tenant peak must be max simultaneous GPU TDP, not the run-total sum.

        Non-overlapping tenant jobs must produce a peak equal to the largest
        single-job TDP, not the sum of all jobs.  This prevents the floor from
        exceeding the actual concurrent load when tenants run sequentially.
        """
        spec = {
            "workload_floor_fraction": 0.5,
            "tenant_events": [
                # Two sequential jobs (no overlap)
                {"tenant_id": "t1", "gpus": 10000, "t_start": 0.0, "duration_s": 100.0},
                {"tenant_id": "t2", "gpus": 5000,  "t_start": 200.0, "duration_s": 100.0},
            ],
        }
        # Concurrent peak: 10000 GPUs × 0.0007 MW = 7.0 MW (NOT 15000 × 0.0007 = 10.5)
        expected_peak = 10000 * _GPU_TDP_MW
        wrong_total_sum = 15000 * _GPU_TDP_MW
        peak = _peak_compute_mw(spec)
        assert peak == pytest.approx(expected_peak, rel=1e-4), (
            f"Non-overlapping tenant peak should be {expected_peak:.3f} MW (max single job); "
            f"got {peak:.3f} MW. A value near {wrong_total_sum:.3f} MW means all jobs were "
            f"summed instead of the maximum concurrent draw."
        )
        # Floor = 50% of concurrent peak, not 50% of total
        assert _compute_floor_mw(spec) == pytest.approx(0.5 * expected_peak, rel=1e-4)

    def test_tenant_event_peak_overlapping_jobs(self):
        """Overlapping tenant jobs contribute to the concurrent peak together."""
        spec = {
            "workload_floor_fraction": 0.5,
            "tenant_events": [
                # Two overlapping jobs (both active 100–200s)
                {"tenant_id": "t1", "gpus": 3000, "t_start": 0.0, "duration_s": 200.0},
                {"tenant_id": "t2", "gpus": 2000, "t_start": 100.0, "duration_s": 200.0},
            ],
        }
        # Concurrent peak at 100–200s: (3000 + 2000) × 0.0007 = 3.5 MW
        expected_peak = 5000 * _GPU_TDP_MW
        peak = _peak_compute_mw(spec)
        assert peak == pytest.approx(expected_peak, rel=1e-4), (
            f"Overlapping tenant peak should be {expected_peak:.3f} MW; got {peak:.3f} MW"
        )

    def test_same_timestamp_job_end_and_starting_does_not_create_transient_peak(self):
        """A JOB_END and a new STARTING at the same timestamp must be applied
        atomically — the peak must NOT reflect a transient window where both are
        simultaneously counted.

        Scenario: job-A with 1000 nodes ends at t=100 and job-B with 1000 nodes
        starts at t=100.  The true peak is 1000 nodes (the jobs replace each other).
        A per-event sample would briefly see 2000 nodes if the STARTING is applied
        before the JOB_END, creating a floor at 60% × 2 × peak = 120% of the real
        maximum and injecting artificial demand.
        """
        nodes = 1000
        spec = {
            "workload_floor_fraction": 0.6,
            "workload_events": [
                # job-A runs 0–100 s
                {"event_type": "starting", "job_id": "job-A",
                 "timestamp": 0.0, "node_count": nodes,
                 "hardware_profile_id": "enterprise_8gpu_air"},
                {"event_type": "job_end", "job_id": "job-A",
                 "timestamp": 100.0, "node_count": 0},
                # job-B starts exactly when job-A ends
                {"event_type": "starting", "job_id": "job-B",
                 "timestamp": 100.0, "node_count": nodes,
                 "hardware_profile_id": "enterprise_8gpu_air"},
            ],
        }
        single_job_mw = nodes * 10.2 * 1.03 / 1000.0  # ≈ 10.506 MW
        floor = _compute_floor_mw(spec)
        # 60% of single_job_mw — must NOT be 60% of 2× due to transient peak
        assert floor == pytest.approx(0.6 * single_job_mw, rel=1e-4), (
            f"Same-timestamp handoff: floor should be 60% × {single_job_mw:.4f} MW = "
            f"{0.6 * single_job_mw:.4f} MW; got {floor:.4f} MW. A value near "
            f"{0.6 * 2 * single_job_mw:.4f} MW indicates a transient 2× peak was counted."
        )

    def test_kube_max_nodes_plus_tenant_peak_is_additive_when_concurrent(self):
        """kube_config.max_nodes participates in the unified timeline alongside tenant events.

        evaluate_tick() adds kube demand and tenant demand together, so the floor
        must be derived from their combined concurrent draw, not from kube alone.
        """
        kube_nodes = 100  # enterprise_8gpu_air default
        tenant_gpus = 5000
        spec = {
            "workload_floor_fraction": 0.5,
            "kube_config": {"max_nodes": kube_nodes},
            "tenant_events": [
                # Tenant burst is concurrent with kube capacity
                {"tenant_id": "t1", "gpus": tenant_gpus,
                 "t_start": 0.0, "duration_s": 3600.0},
            ],
        }
        kube_mw = kube_nodes * 10.2 * 1.03 / 1000.0  # ≈ 1.0506 MW
        tenant_mw = tenant_gpus * _GPU_TDP_MW           # 3.5 MW
        expected_combined_peak = kube_mw + tenant_mw    # ≈ 4.5506 MW
        wrong_kube_only = kube_mw                       # 1.0506 MW (wrong)

        peak = _peak_compute_mw(spec)
        assert peak == pytest.approx(expected_combined_peak, rel=1e-4), (
            f"Kube+tenant concurrent peak should be {expected_combined_peak:.4f} MW "
            f"(sum); got {peak:.4f} MW. A value near {wrong_kube_only:.4f} MW means "
            f"kube capacity was not combined with tenant events on the unified timeline."
        )
        floor = _compute_floor_mw(spec)
        assert floor == pytest.approx(0.5 * expected_combined_peak, rel=1e-4)

    def test_combined_workload_and_tenant_peak_coincident_is_additive(self):
        """Concurrent workload and tenant peaks add together.

        When a workload job and a tenant burst are active at the same time,
        peak_compute_mw() must return their sum — evaluate_tick() adds both
        draws on every concurrent tick.
        """
        workload_nodes = 100
        tenant_gpus = 5000
        spec = {
            "workload_floor_fraction": 0.5,
            # Workload job starts at t=0, no job_end → active throughout
            "workload_events": [
                {"event_type": "starting", "job_id": "j1",
                 "timestamp": 0.0, "node_count": workload_nodes,
                 "hardware_profile_id": "enterprise_8gpu_air"},
            ],
            # Tenant burst overlaps the workload job
            "tenant_events": [
                {"tenant_id": "t1", "gpus": tenant_gpus,
                 "t_start": 0.0, "duration_s": 3600.0},
            ],
        }
        workload_peak = workload_nodes * 10.2 * 1.03 / 1000.0  # ≈ 1.0506 MW
        tenant_peak = tenant_gpus * _GPU_TDP_MW                  # 3.5 MW
        expected_peak = workload_peak + tenant_peak               # ≈ 4.5506 MW

        peak = _peak_compute_mw(spec)
        assert peak == pytest.approx(expected_peak, rel=1e-4), (
            f"Coincident workload+tenant peak should be {expected_peak:.4f} MW (sum); "
            f"got {peak:.4f} MW."
        )

    def test_combined_workload_and_tenant_peak_non_overlapping_uses_larger(self):
        """Non-overlapping workload and tenant sources: peak is the larger single source.

        A workload job that ends before any tenant burst starts must not have its
        individual maximum added to the tenant maximum.  The unified timeline
        yields max(workload_peak, tenant_peak) when the windows do not overlap.
        """
        workload_nodes = 100
        tenant_gpus = 5000
        spec = {
            "workload_floor_fraction": 0.5,
            # Workload job runs 0–90 s then ends
            "workload_events": [
                {"event_type": "starting", "job_id": "j1",
                 "timestamp": 0.0, "node_count": workload_nodes,
                 "hardware_profile_id": "enterprise_8gpu_air"},
                {"event_type": "job_end", "job_id": "j1",
                 "timestamp": 90.0, "node_count": 0},
            ],
            # Tenant burst starts after workload ends (no overlap)
            "tenant_events": [
                {"tenant_id": "t1", "gpus": tenant_gpus,
                 "t_start": 200.0, "duration_s": 3600.0},
            ],
        }
        workload_peak_mw = workload_nodes * 10.2 * 1.03 / 1000.0  # ≈ 1.0506 MW
        tenant_peak_mw = tenant_gpus * _GPU_TDP_MW                  # 3.5 MW
        expected_peak = max(workload_peak_mw, tenant_peak_mw)        # 3.5 MW (tenant wins)
        wrong_additive = workload_peak_mw + tenant_peak_mw           # 4.5506 MW (wrong)

        peak = _peak_compute_mw(spec)
        assert peak == pytest.approx(expected_peak, rel=1e-4), (
            f"Non-overlapping peak should be {expected_peak:.4f} MW (max of the two); "
            f"got {peak:.4f} MW.  A value near {wrong_additive:.4f} MW means the "
            f"individual maxima were summed instead of resolved on a unified timeline."
        )
        floor = _compute_floor_mw(spec)
        # Floor must be 50 % of 3.5 MW = 1.75 MW, well below the 3.5 MW actual max.
        assert floor == pytest.approx(0.5 * expected_peak, rel=1e-4)
        assert floor < expected_peak, (
            "Floor must never exceed the actual peak (would inject artificial demand)"
        )

    def test_combined_workload_and_tenant_peak_partial_overlap(self):
        """Partially overlapping sources: peak is the maximum concurrent combined draw."""
        workload_nodes = 100
        tenant_gpus = 5000
        spec = {
            "workload_floor_fraction": 0.5,
            # Workload job: 0–500 s
            "workload_events": [
                {"event_type": "starting", "job_id": "j1",
                 "timestamp": 0.0, "node_count": workload_nodes,
                 "hardware_profile_id": "enterprise_8gpu_air"},
                {"event_type": "job_end", "job_id": "j1",
                 "timestamp": 500.0, "node_count": 0},
            ],
            # Tenant burst: 400–1000 s (overlaps 400–500 s with workload)
            "tenant_events": [
                {"tenant_id": "t1", "gpus": tenant_gpus,
                 "t_start": 400.0, "duration_s": 600.0},
            ],
        }
        wl_mw = workload_nodes * 10.2 * 1.03 / 1000.0  # ≈ 1.0506 MW
        t_mw = tenant_gpus * _GPU_TDP_MW                 # 3.5 MW
        # Peak window 400–500 s: both active → 1.0506 + 3.5 = 4.5506 MW
        expected_peak = wl_mw + t_mw

        peak = _peak_compute_mw(spec)
        assert peak == pytest.approx(expected_peak, rel=1e-4), (
            f"Partial-overlap peak should be {expected_peak:.4f} MW (overlap window); "
            f"got {peak:.4f} MW"
        )

    def test_tenant_event_floor_is_40_to_60_pct_of_concurrent_peak(self):
        """Floor fraction 0.5 yields exactly 50% of the concurrent tenant peak."""
        spec = {
            "workload_floor_fraction": 0.5,
            "tenant_events": [
                {"tenant_id": "t1", "gpus": 4000, "t_start": 0.0, "duration_s": 3600.0},
                {"tenant_id": "t2", "gpus": 3000, "t_start": 0.0, "duration_s": 3600.0},
            ],
        }
        # Both active from t=0; concurrent peak = 7000 × 0.0007 = 4.9 MW
        concurrent_peak = 7000 * _GPU_TDP_MW
        floor = _compute_floor_mw(spec)
        assert floor == pytest.approx(0.5 * concurrent_peak, rel=1e-4)
        assert 0.40 * concurrent_peak <= floor <= 0.60 * concurrent_peak

    def test_scale_without_prior_starting_creates_base_cohort(self):
        """A SCALE event with no prior STARTING must create the initial cohort.

        GPUModule.apply_signal() supports this 'already-running injection' path
        where a SCALE arrives for a job that was already running before the
        scenario timeline begins.  The factory must mirror this so the peak
        includes those nodes rather than returning 0 MW.
        """
        spec = {
            "workload_floor_fraction": 0.5,
            "workload_events": [
                # No STARTING event — job is treated as already running
                {"event_type": "scale", "job_id": "live-job",
                 "timestamp": 0.0, "node_count": 200,
                 "hardware_profile_id": "enterprise_8gpu_air"},
            ],
        }
        expected_peak = 200 * 10.2 * 1.03 / 1000.0  # 2.1012 MW
        peak = _peak_compute_mw(spec)
        assert peak == pytest.approx(expected_peak, rel=1e-4), (
            f"SCALE-without-STARTING peak should be {expected_peak:.4f} MW (200 nodes); "
            f"got {peak:.4f} MW. A value of 0 means the event was ignored."
        )
        assert _compute_floor_mw(spec) == pytest.approx(0.5 * expected_peak, rel=1e-4), (
            "Floor must be 50% of the SCALE-without-STARTING peak"
        )

    def test_scale_up_with_different_hw_profile_uses_scale_event_kw(self):
        """SCALE-UP cohort uses the SCALE event's hardware_profile_id, not the original.

        A job that starts on enterprise_8gpu_air (10.2 kW/node) but scales up
        with nextgen_rack_liquid (120 kW/rack) must derive peak from the mix,
        not from 10.2 kW/node throughout.  This mirrors the runtime's cohort model
        where the scale-up delta forms its own cohort with the SCALE event's profile.
        """
        spec = {
            "workload_floor_fraction": 0.5,
            "workload_events": [
                # Start with 100 enterprise_8gpu_air nodes (10.2 kW)
                {"event_type": "starting", "job_id": "job-1",
                 "timestamp": 0.0, "node_count": 100,
                 "hardware_profile_id": "enterprise_8gpu_air"},
                # Scale up by 10 nextgen_rack_liquid racks (120 kW) — new total=110
                {"event_type": "scale", "job_id": "job-1",
                 "timestamp": 10.0, "node_count": 110,
                 "hardware_profile_id": "nextgen_rack_liquid"},
            ],
        }
        # Peak: 100 * 10.2 * 1.03 / 1000  +  10 * 126 * 1.03 / 1000
        #      = 1.0506  +  1.2978  = 2.3484 MW
        expected_peak = (100 * 10.2 + 10 * 120.0) * 1.03 / 1000.0
        wrong_peak_single_profile = 110 * 10.2 * 1.03 / 1000.0
        peak = _peak_compute_mw(spec)
        assert peak == pytest.approx(expected_peak, rel=1e-4), (
            f"Mixed-profile scale peak should be {expected_peak:.4f} MW; got {peak:.4f} MW. "
            f"A value near {wrong_peak_single_profile:.4f} MW means SCALE kept the "
            f"original profile for new nodes instead of using the SCALE event's profile."
        )

    def test_grid_resonance_stress_computed_floor_approx_013_mw(self):
        """grid-resonance-stress floor ≈ 0.02 × 6.3036 MW ≈ 0.126 MW ≈ 0.13 MW.

        Tests the *computed* floor (not just the stored fraction) so that any
        change to peak derivation or PUE handling is immediately caught.
        """
        with TestClient(create_app()) as client:
            detail = client.get("/scenarios/grid-resonance-stress").json()
        spec_dict = detail["spec"]
        floor = _compute_floor_mw(spec_dict)
        expected_floor = 0.02 * _NODES * _ENT_KW * _PUE / 1000.0   # 0.02 × 6.3036
        assert floor == pytest.approx(expected_floor, rel=1e-3), (
            f"grid-resonance-stress computed floor {floor:.4f} MW ≠ expected "
            f"{expected_floor:.4f} MW (~0.13 MW)"
        )
        assert 0.10 <= floor <= 0.16, (
            f"grid-resonance-stress floor {floor:.4f} MW outside [0.10, 0.16] MW"
        )


class TestComputeFloorRuntime:
    """TC-11.4 runtime tests: SimulationState.compute_floor_mw and evaluate_tick() enforcement."""

    def _floor_spec(self, node_count: int = 100, floor_fraction: float = 0.5,
                    job_start_t: float = 0.0, dt_lead_seconds: float = 30.0) -> dict:
        """Build a minimal valid spec dict with workload_floor_fraction set."""
        spec = _minimal_spec(
            name=f"floor-rt-{node_count}-{floor_fraction}",
            workload_floor_fraction=floor_fraction,
            dt_lead_seconds=dt_lead_seconds,
            workload_events=[
                WorkloadEventSpec(event_id="e-floor", job_id="job-floor",
                                  event_type="starting", timestamp=job_start_t,
                                  node_count=node_count),
            ],
            end_sim_time=120.0,
        )
        return json.loads(spec.model_dump_json())

    def test_sim_state_compute_floor_mw_set_by_factory(self):
        """build_run_context_from_spec() must wire compute_floor_mw onto SimulationState.

        The computed value must equal workload_floor_fraction × peak_compute_mw,
        not a default 0.0 and not a raw fraction.
        """
        spec_dict = self._floor_spec(node_count=100, floor_fraction=0.5)
        ctx = build_run_context_from_spec("run-floor-wire", spec_dict, playback_speed=0.0)
        expected_floor = _compute_floor_mw(spec_dict)
        # RunContext exposes SimulationState via .sim_state
        assert ctx.sim_state.compute_floor_mw == pytest.approx(expected_floor, rel=1e-4), (
            f"SimulationState.compute_floor_mw={ctx.sim_state.compute_floor_mw:.4f} MW "
            f"≠ expected {expected_floor:.4f} MW"
        )
        assert ctx.sim_state.compute_floor_mw > 0.0, (
            "compute_floor_mw must be positive when workload_floor_fraction is set"
        )

    def test_sim_state_no_floor_fraction_leaves_floor_zero(self):
        """Without workload_floor_fraction, compute_floor_mw must remain 0.0 (backward-compat)."""
        spec = _minimal_spec(name="no-floor")
        spec_dict = json.loads(spec.model_dump_json())
        ctx = build_run_context_from_spec("run-no-floor", spec_dict, playback_speed=0.0)
        assert ctx.sim_state.compute_floor_mw == pytest.approx(0.0), (
            f"Without workload_floor_fraction, compute_floor_mw should be 0.0; "
            f"got {ctx.sim_state.compute_floor_mw}"
        )

    def test_evaluate_tick_clamps_demand_at_floor_when_no_jobs_active(self):
        """evaluate_tick() must clamp p_compute_demand_mw >= compute_floor_mw.

        Scenario: job starts at t=50s, floor derived from its 100-node peak.
        At t=5s (first tick), job is not yet active → raw demand would be 0 MW.
        The floor must keep tick.p_compute_demand_mw at ≥ floor.
        """
        spec_dict = self._floor_spec(node_count=100, floor_fraction=0.5, job_start_t=50.0)
        ctx = build_run_context_from_spec("run-floor-enforce", spec_dict, playback_speed=0.0)
        expected_floor = _compute_floor_mw(spec_dict)
        assert expected_floor > 0.0, "Test precondition: expected_floor must be positive"

        # Step one tick; job has not yet started (t=5 < t_start=50)
        tick = ctx.step()
        assert tick.sim_time_seconds == pytest.approx(5.0)
        assert tick.p_compute_demand_mw >= expected_floor - 1e-6, (
            f"Floor not enforced at t={tick.sim_time_seconds:.1f}s: "
            f"p_compute_demand_mw={tick.p_compute_demand_mw:.4f} MW "
            f"< floor {expected_floor:.4f} MW"
        )

    def test_grid_resonance_stress_floor_active_after_job_ends(self):
        """grid-resonance-stress: compute demand must equal the floor after job_end.

        The scenario starts a 600-node job at t=0 then ends it at t=90 s.
        For ticks after t=90 s, no active jobs remain so the floor clamp
        must supply 100% of p_compute_demand_mw ≈ 0.126 MW.
        This proves the idle-phase near-zero stress condition the scenario exists for.
        """
        from api.routes.scenarios import _SEEDED
        spec_dict = next(
            (sd for sid, ss in _SEEDED if sid == "grid-resonance-stress"
             for sd in [ss.model_dump()]),
            None,
        )
        assert spec_dict is not None, "grid-resonance-stress scenario not found in _SEEDED"

        ctx = build_run_context_from_spec("run-grs-idle", spec_dict, playback_speed=0.0)
        expected_floor = _compute_floor_mw(spec_dict)
        assert expected_floor > 0.0, "Test precondition: floor must be positive"

        # Step the simulation past t=90 s (job_end event timestamp).
        # With dt=5 s per tick, 90 s / 5 s = 18 ticks to clear the job.
        ticks_after_job_end: list[float] = []
        last_tick = None
        for i in range(35):
            tick = ctx.step()
            last_tick = tick
            if tick.sim_time_seconds > 90.0:
                ticks_after_job_end.append(tick.p_compute_demand_mw)

        assert ticks_after_job_end, (
            f"No ticks past t=90 s; last tick at sim_time={last_tick.sim_time_seconds:.1f} s"
        )
        for t_idx, demand in enumerate(ticks_after_job_end):
            assert demand == pytest.approx(expected_floor, rel=0.01), (
                f"After job_end, p_compute_demand_mw tick {t_idx} = {demand:.4f} MW "
                f"but floor = {expected_floor:.4f} MW — floor clamp not active."
            )

    def test_floor_produces_cooling_demand_during_idle_ticks(self):
        """Floor load must contribute to lagged cooling demand during idle ticks.

        When no jobs are active, the floor holds p_compute_demand_mw at
        compute_floor_mw.  This compute heat must flow through the cooling model
        so p_cooling_demand_mw rises above zero after enough ticks — confirming
        the __floor__ envelope is registered and record_job_compute() records to it.
        """
        # Job starts very late so we can step idle ticks before it arrives.
        spec_dict = self._floor_spec(node_count=100, floor_fraction=0.5, job_start_t=9999.0)
        ctx = build_run_context_from_spec("run-idle-cool", spec_dict, playback_speed=0.0)
        expected_floor = _compute_floor_mw(spec_dict)
        assert expected_floor > 0.0, "Test precondition: floor must be positive"

        # Step enough ticks (dt_thermal_seconds ≈ 90s, interval 5s → ~20 ticks)
        # so the cooling model accumulates heat from the floor load.
        cooling_after: list[float] = []
        for _ in range(30):
            tick = ctx.step()
            cooling_after.append(tick.p_cooling_demand_mw)
            assert tick.p_compute_demand_mw >= expected_floor - 1e-6, (
                f"Floor not enforced at t={tick.sim_time_seconds:.1f}s"
            )

        # After dt_thermal seconds of floor load, cooling demand must have risen.
        max_cooling = max(cooling_after)
        assert max_cooling > 0.0, (
            f"p_cooling_demand_mw never rose above 0 over 30 idle ticks with "
            f"floor={expected_floor:.4f} MW compute load — __floor__ envelope "
            f"is likely not registered or not contributing to the cooling model."
        )

    def test_evaluate_tick_demand_equals_job_load_when_job_exceeds_floor(self):
        """When an active job drives demand above the floor, the floor must not suppress it.

        This verifies the clamp is a floor (minimum), not a cap.  Uses
        dt_lead_seconds=0.0 so the 1000-node job contributes immediately at t=5s.
        """
        # 1000-node job → large demand; floor fraction 0.5 → floor = 500-node equivalent.
        # dt_lead_seconds=0 so the job contributes to p_compute_demand_mw from the first tick.
        spec_dict = self._floor_spec(node_count=1000, floor_fraction=0.5,
                                     job_start_t=0.0, dt_lead_seconds=0.0)
        ctx = build_run_context_from_spec("run-above-floor", spec_dict, playback_speed=0.0)
        expected_floor = _compute_floor_mw(spec_dict)
        # Peak demand ≈ 1000 * 10.2 * 1.03 / 1000 = 10.506 MW
        expected_full_demand = 1000 * 10.2 * 1.03 / 1000.0

        tick = ctx.step()
        assert tick.p_compute_demand_mw > expected_floor + 1e-6, (
            f"Active job demand {tick.p_compute_demand_mw:.4f} MW should exceed "
            f"floor {expected_floor:.4f} MW — floor must not cap active-job demand"
        )
        assert tick.p_compute_demand_mw == pytest.approx(expected_full_demand, rel=0.05), (
            f"Active job demand {tick.p_compute_demand_mw:.4f} MW should match "
            f"full 1000-node load ≈ {expected_full_demand:.4f} MW (floor must not cap it)"
        )


# ---------------------------------------------------------------------------
# StartRunRequest with scenario_id
# ---------------------------------------------------------------------------

class TestStartRunWithScenarioId:
    def test_scenario_id_path_starts_run(self):
        """POST /runs with scenario_id must return 201 and a run_id."""
        with TestClient(create_app()) as client:
            resp = client.post("/runs", json={
                "scenario_id": "demo-alert",
                "playback_speed": 0.0,
            })
        assert resp.status_code == 201
        assert resp.json()["run_id"].startswith("run-")

    def test_scenario_id_nonexistent_returns_404(self):
        with TestClient(create_app()) as client:
            resp = client.post("/runs", json={
                "scenario_id": "does-not-exist",
                "playback_speed": 0.0,
            })
        assert resp.status_code == 404

    def test_scenario_preset_removed_returns_422(self):
        """F1 scenario_preset scaffolding removed — unknown field → 422."""
        with TestClient(create_app()) as client:
            resp = client.post("/runs", json={
                "scenario_preset": "demo-alert",
                "end_sim_time": 300,
                "playback_speed": 10,
            })
        # With extra fields forbidden OR with no job_id/node_count/scenario_id, must be 422
        assert resp.status_code == 422

    def test_direct_job_node_path_still_works(self):
        """Programmatic path (job_id + node_count) must still return 201."""
        with TestClient(create_app()) as client:
            resp = client.post("/runs", json={
                "job_id": "tc33-direct",
                "node_count": 10,
                "end_sim_time": 1e15,
                "playback_speed": 0.0,
            })
        assert resp.status_code == 201

    def test_no_identifiers_returns_422(self):
        """Empty body → 422 (neither scenario_id nor job_id+node_count)."""
        with TestClient(create_app()) as client:
            resp = client.post("/runs", json={})
        assert resp.status_code == 422
        text = resp.text
        assert "job_id" in text or "node_count" in text or "scenario_id" in text

    def test_build_run_context_from_spec_smoke(self):
        """build_run_context_from_spec must return a functional RunContext."""
        spec = _minimal_spec(name="smoke")  # end_sim_time defaults to 60.0 (schema minimum)
        ctx = build_run_context_from_spec(
            "test-run-smoke",
            json.loads(spec.model_dump_json()),
            playback_speed=0.0,
        )
        # Note: _minimal_spec uses end_sim_time=60.0 (minimum allowed by ScenarioSpec)
        assert ctx.run_id == "test-run-smoke"
        assert not ctx.is_complete()
        tick = ctx.step()
        assert tick.sim_time_seconds == pytest.approx(5.0)  # F5: interval-end


def test_rolling_planning_peaks_seed_preserves_forecast_horizons():
    """The rolling-planning demo keeps all three authored peak horizons."""
    with TestClient(create_app()) as client:
        detail = client.get("/scenarios/demo-rolling-planning-peaks")

    assert detail.status_code == 200
    spec = detail.json()["spec"]
    peak_events = [
        event for event in spec["workload_events"]
        if (
            event["job_id"].startswith("rolling-")
            and event["job_id"] != "rolling-base"
            and event["event_type"] == "starting"
        )
    ]
    assert [event["timestamp"] for event in peak_events] == [900.0, 3600.0, 10800.0]
    assert spec["end_sim_time"] == 14400.0
