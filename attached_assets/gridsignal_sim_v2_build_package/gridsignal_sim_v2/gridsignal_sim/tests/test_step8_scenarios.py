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
