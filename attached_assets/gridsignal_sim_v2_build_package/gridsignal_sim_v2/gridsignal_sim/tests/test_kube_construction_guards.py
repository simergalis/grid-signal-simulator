"""
tests/test_kube_construction_guards.py — Construction-time guards added in JOBQ-001 Addendum 4.

Tests two fail-loud assertions added to build_run_context_from_spec (scenario_factory.py):

  GUARD-1  max_nodes invariant
    All three KubeDemandAgents must share the same max_nodes value.  When they
    disagree, the cross-agent admissions accumulator enforces the wrong ceiling
    silently — so the factory now raises ValueError immediately with a message
    naming the offending tenant and both values.

  GUARD-2  rated_kw_per_node sentinel
    KubeConfig.rated_kw_per_node defaults to 0.0 and MUST be overwritten by the
    factory from DEFAULT_HARDWARE_LIBRARY.  If the library lookup returns 0.0
    (missing profile or bad library entry), the factory raises ValueError rather
    than silently producing zero-draw job estimates.

Both tests use the 'demo-kube' seeded scenario as the base spec (it already
carries a valid kube_config).  They inject faults via unittest.mock without
touching any physics-engine internals.
"""

import json
import sys, os
import pytest
from unittest.mock import patch

# Tests run from the gridsignal_sim package root via pytest.
# api/ is at the same level; make sure both are importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.routes.scenarios import build_seeded_store
from runtime import scenario_factory as _sf
from runtime.scenario_factory import build_run_context_from_spec


# ---------------------------------------------------------------------------
# Shared fixture: the demo-kube spec dict
# ---------------------------------------------------------------------------

def _kube_spec() -> dict:
    """Return the demo-kube spec as a plain dict (JSON-round-trip safe)."""
    store = build_seeded_store()
    rec = store._data.get("scenario-kube-peak-overage")
    assert rec is not None, "scenario-kube-peak-overage not found in seeded store; check build_seeded_store()"
    return json.loads(rec.spec_json)


# ---------------------------------------------------------------------------
# GUARD-1 — max_nodes invariant
# ---------------------------------------------------------------------------

class TestMaxNodesInvariant:

    def test_mismatched_max_nodes_raises(self):
        """Third agent with a different max_nodes must raise ValueError immediately."""
        call_count = [0]

        class _FakeAgent:
            """Replaces KubeDemandAgent; the third instance gets max_nodes=999."""
            def __init__(self, config, site_id):
                call_count[0] += 1
                self.config = config
                self.rng_load = None
                if call_count[0] == 3:
                    # KubeConfig is a regular (non-frozen) dataclass — direct write is fine.
                    self.config.max_nodes = 999

        with patch.object(_sf, "KubeDemandAgent", _FakeAgent):
            with pytest.raises(ValueError, match="Fleet max_nodes invariant violated"):
                build_run_context_from_spec(
                    run_id="guard-max-nodes-mismatch",
                    spec_data=_kube_spec(),
                )

    def test_error_message_names_offending_tenant(self):
        """The ValueError message must include tenant identifiers and both max_nodes values."""
        call_count = [0]

        class _FakeAgent:
            def __init__(self, config, site_id):
                call_count[0] += 1
                self.config = config
                self.rng_load = None
                if call_count[0] == 3:
                    self.config.max_nodes = 42

        with patch.object(_sf, "KubeDemandAgent", _FakeAgent):
            with pytest.raises(ValueError) as exc_info:
                build_run_context_from_spec(
                    run_id="guard-max-nodes-msg",
                    spec_data=_kube_spec(),
                )
        msg = str(exc_info.value)
        # The message must name at least one tenant id and the bad value.
        assert "42" in msg, f"Expected bad max_nodes value 42 in error: {msg}"
        # The assertion lists all agents, so at least one tenant id should appear.
        assert any(t in msg for t in ("'A'", "'B'", "'C'", '"A"', '"B"', '"C"')), (
            f"Expected tenant id in error message: {msg}"
        )

    def test_matching_max_nodes_passes(self):
        """Three agents that all agree on max_nodes must not raise."""
        spec = _kube_spec()
        # Explicitly set max_nodes to a non-default value; all three agents will
        # inherit it from the same kube_config dict, so they'll always agree.
        spec["kube_config"]["max_nodes"] = 400
        ctx = build_run_context_from_spec(
            run_id="guard-max-nodes-ok",
            spec_data=spec,
        )
        assert len(ctx.sim_state.kube_agents) == 3
        vals = {a.config.max_nodes for a in ctx.sim_state.kube_agents}
        assert vals == {400}, f"Expected all agents max_nodes=400, got {vals}"


# ---------------------------------------------------------------------------
# GUARD-2 — rated_kw_per_node sentinel
# ---------------------------------------------------------------------------

class TestRatedKwSentinel:

    def test_zero_rated_kw_raises(self):
        """A hardware profile whose rated_kw resolves to 0.0 must raise, not silently pass."""
        from core.models import HardwareProfile

        fake_lib = dict(_sf.DEFAULT_HARDWARE_LIBRARY)
        fake_lib["zero_kw_profile"] = HardwareProfile(
            profile_id="zero_kw_profile",
            rated_kw=0.0,
        )

        spec = _kube_spec()
        spec["kube_config"]["hardware_profile_id"] = "zero_kw_profile"

        with patch.object(_sf, "DEFAULT_HARDWARE_LIBRARY", fake_lib):
            with pytest.raises(ValueError, match="resolved to rated_kw=0.0"):
                build_run_context_from_spec(
                    run_id="guard-kw-zero",
                    spec_data=spec,
                )

    def test_error_message_names_profile_id(self):
        """The ValueError must name the offending hardware_profile_id."""
        from core.models import HardwareProfile

        fake_lib = dict(_sf.DEFAULT_HARDWARE_LIBRARY)
        fake_lib["bad_profile_xyz"] = HardwareProfile(
            profile_id="bad_profile_xyz",
            rated_kw=0.0,
        )

        spec = _kube_spec()
        spec["kube_config"]["hardware_profile_id"] = "bad_profile_xyz"

        with patch.object(_sf, "DEFAULT_HARDWARE_LIBRARY", fake_lib):
            with pytest.raises(ValueError) as exc_info:
                build_run_context_from_spec(
                    run_id="guard-kw-msg",
                    spec_data=spec,
                )
        assert "bad_profile_xyz" in str(exc_info.value), (
            f"Expected profile id in error: {exc_info.value}"
        )

    def test_positive_rated_kw_passes(self):
        """A hardware profile with a positive rated_kw must produce agents with rated_kw_per_node > 0."""
        ctx = build_run_context_from_spec(
            run_id="guard-kw-ok",
            spec_data=_kube_spec(),   # enterprise_8gpu_air → 10.2 kW
        )
        for agent in ctx.sim_state.kube_agents:
            assert agent.config.rated_kw_per_node > 0.0, (
                f"Agent {agent.config.tenant_id} has rated_kw_per_node=0.0 "
                f"after factory construction"
            )

    def test_factory_sources_rated_kw_from_library_not_config_default(self):
        """Confirm the factory writes library.rated_kw into all three agents' configs."""
        from core.models import HardwareProfile

        fake_lib = dict(_sf.DEFAULT_HARDWARE_LIBRARY)
        fake_lib["custom_profile"] = HardwareProfile(
            profile_id="custom_profile",
            rated_kw=77.7,   # unusual value — easy to assert
        )

        spec = _kube_spec()
        spec["kube_config"]["hardware_profile_id"] = "custom_profile"

        with patch.object(_sf, "DEFAULT_HARDWARE_LIBRARY", fake_lib):
            ctx = build_run_context_from_spec(
                run_id="guard-kw-library-source",
                spec_data=spec,
            )

        for agent in ctx.sim_state.kube_agents:
            assert agent.config.rated_kw_per_node == pytest.approx(77.7), (
                f"Agent {agent.config.tenant_id}: expected rated_kw_per_node=77.7 "
                f"(from library), got {agent.config.rated_kw_per_node}"
            )
