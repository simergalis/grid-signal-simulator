"""tests/test_tenant_ceiling_gate.py — ScenarioSpec._check_tenant_ceilings regression coverage.

Guards api/schemas.py's tenant-power-ceiling gate: POST /scenarios must reject a
tenant workload event whose GPU draw exceeds the tenant's allowed cap, and must
accept events within it, so the validator cannot silently break or be removed.

Boundary note
-------------
TENANT_CONTRACTED_MW['c'] = 0.60 MW is the tenant's *contracted* ceiling, but the
live validator (_check_tenant_ceilings) enforces a burst-tolerant hard cap of
_TENANT_BURST_ALLOWANCE (1.5x) = 0.90 MW — draw between 100% and 150% of the
ceiling is accepted and billed at a surcharge by the runtime engine; only draw
above 150% is rejected at save time. At _GPU_TDP_MW = 0.0007 MW/GPU that puts:
  - 857 GPUs  (0.5999 MW) at the 100% contracted ceiling  -> accepted
  - 1285 GPUs (0.8995 MW) at the 150% hard cap             -> accepted (boundary)
  - 1286 GPUs (0.9002 MW) one GPU over the hard cap        -> rejected (422)
These are the values exercised below, rather than a value merely above the
100% ceiling, since draw in the 100%-150% band is valid by design.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app
from api.schemas import (
    BessUnitSpec,
    ScenarioSpec,
    TurbineUnitSpec,
    WorkloadEventSpec,
    _GPU_TDP_MW,
    _TENANT_BURST_ALLOWANCE,
    TENANT_CONTRACTED_MW,
)

_CEILING_C = TENANT_CONTRACTED_MW["c"]                       # 0.60 MW
_HARD_CAP_C = _CEILING_C * _TENANT_BURST_ALLOWANCE            # 0.90 MW
_AT_CEILING_GPUS = int(_CEILING_C / _GPU_TDP_MW)               # 857
_AT_HARD_CAP_GPUS = int(_HARD_CAP_C / _GPU_TDP_MW)             # 1285
_OVER_HARD_CAP_GPUS = _AT_HARD_CAP_GPUS + 1                    # 1286


def _app_client() -> TestClient:
    return TestClient(create_app())


def _minimal_spec_payload(tenant_gpus: int, tenant_id: str = "c") -> dict:
    """Minimal valid ScenarioSpec payload with one tenant workload event.

    The tenant event is assembled as a plain dict (not a TenantWorkloadEvent
    instance) so an intentionally over-cap GPU count can be round-tripped
    through the API/model validators under test, instead of raising early
    while the fixture itself is being built.
    """
    spec = ScenarioSpec(
        name="tenant ceiling gate test",
        workload_events=[
            WorkloadEventSpec(
                event_id="e0", job_id="job", event_type="starting",
                timestamp=0.0, node_count=1,
            ),
        ],
        bess_units=[BessUnitSpec(asset_id="bess-0", rated_mw=5.0, usable_mwh=2.0)],
        turbine_units=[TurbineUnitSpec(asset_id="turbine-0", rated_mw=10.0)],
    )
    payload = spec.model_dump(mode="json")
    payload["tenant_events"] = [
        {
            "tenant_id": tenant_id,
            "label": "burst job",
            "gpus": tenant_gpus,
            "t_start": 0.0,
            "duration_s": 60.0,
        },
    ]
    return payload


class TestTenantCeilingGateAcceptsWithinBounds:
    def test_at_contracted_ceiling_succeeds(self):
        """857 GPUs for Tenant C (exactly the 100% contracted ceiling) is accepted."""
        payload = _minimal_spec_payload(_AT_CEILING_GPUS)
        with _app_client() as client:
            resp = client.post("/scenarios", json=payload)
        assert resp.status_code == 201, resp.text

    def test_at_hard_cap_boundary_succeeds(self):
        """1285 GPUs (exactly the 150% burst hard cap) is still accepted."""
        payload = _minimal_spec_payload(_AT_HARD_CAP_GPUS)
        with _app_client() as client:
            resp = client.post("/scenarios", json=payload)
        assert resp.status_code == 201, resp.text

    def test_constructing_scenario_spec_directly_at_ceiling_succeeds(self):
        """Model-level construction (not just the route) accepts the ceiling value."""
        payload = _minimal_spec_payload(_AT_CEILING_GPUS)
        ScenarioSpec.model_validate(payload)  # must not raise


class TestTenantCeilingGateRejectsAboveHardCap:
    def test_over_hard_cap_returns_422(self):
        """1286 GPUs (one GPU over the 150% hard cap) returns HTTP 422."""
        payload = _minimal_spec_payload(_OVER_HARD_CAP_GPUS)
        with _app_client() as client:
            resp = client.post("/scenarios", json=payload)
        assert resp.status_code == 422, resp.text

    def test_error_message_identifies_tenant_excess_and_max_gpus(self):
        """422 body must name the tenant, the offending draw, and the max allowed GPUs."""
        payload = _minimal_spec_payload(_OVER_HARD_CAP_GPUS)
        with _app_client() as client:
            resp = client.post("/scenarios", json=payload)
        assert resp.status_code == 422
        body_text = resp.text
        assert "'c'" in body_text or '"c"' in body_text, (
            "error must identify the offending tenant id"
        )
        # The rejected draw in MW must be surfaced (excess over the cap).
        assert "0.900" in body_text, (
            "error must surface the offending draw in MW"
        )
        # The max allowed GPU count at the hard cap must be surfaced.
        assert str(_AT_HARD_CAP_GPUS) in body_text, (
            "error must surface the max allowed GPU count"
        )

    def test_far_over_hard_cap_still_returns_422(self):
        """A GPU count far beyond the hard cap (not just marginally over) is rejected."""
        payload = _minimal_spec_payload(2000)
        with _app_client() as client:
            resp = client.post("/scenarios", json=payload)
        assert resp.status_code == 422, resp.text

    def test_constructing_scenario_spec_directly_over_hard_cap_raises(self):
        """Model-level construction (not just the route) rejects the over-cap draw."""
        payload = _minimal_spec_payload(_OVER_HARD_CAP_GPUS)
        try:
            ScenarioSpec.model_validate(payload)
        except Exception as exc:  # pydantic ValidationError
            assert "c" in str(exc)
        else:
            raise AssertionError(
                "ScenarioSpec.model_validate must reject GPU draw over the hard cap"
            )
