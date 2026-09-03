"""Regression coverage for aggregate Kubernetes signal identity.

Each KubeDemandAgent emits the tenant's total admitted-node count.  Repeated
SCALE signals therefore must retain a stable job_id: GPUModule replaces the
aggregate rather than accumulating a second copy of the whole cluster.
"""

from __future__ import annotations

import unittest

from core.asset_modules import GPUModule
from core.kube_demand import KubeConfig, KubeDemandAgent, _PendingAdmission
from core.models import (
    GENERIC_FALLBACK_PROFILE,
    SiteConfig,
    WorkloadEventType,
)


class TestKubeAggregateSignalIdentity(unittest.TestCase):
    """Repeated admissions must update one aggregate GPU workload."""

    def _make_agent(self, tenant_id: str = "default") -> KubeDemandAgent:
        agent = KubeDemandAgent(
            KubeConfig(
                max_nodes=1000,
                min_nodes=0,
                tenant_id=tenant_id,
                mean_interarrival_s=1e6,
                reorder_window_s=0.0,
                ntp_jitter_s=0.0,
                rng_seed=42,
            ),
            site_id="test-site",
        )
        # This test injects deterministic admissions; suppress Poisson arrivals.
        agent._next_arrival_sim_time = 1e9
        return agent

    @staticmethod
    def _queue_admission(
        agent: KubeDemandAgent,
        *,
        event_id: str,
        nodes: int,
        observed_at: float,
    ) -> None:
        agent._reorder_buffer.append(
            _PendingAdmission(
                event_id=event_id,
                node_count=nodes,
                hardware_profile_id="enterprise_8gpu_air",
                observed_at=observed_at,
                event_timestamp=observed_at,
                duration_s=1000.0,
            )
        )

    def test_repeated_arrivals_do_not_accumulate_duplicate_cluster_totals(self):
        """Five admissions reach 1,000 nodes, not the old 3,000-node overcount."""
        agent = self._make_agent()
        site = SiteConfig(site_id="test-site", pue_base=1.03)
        gpu = GPUModule(asset_id="gpu-0", site=site, hardware_library={})

        stable_job_ids: list[str] = []
        for index in range(5):
            # Model the changing arrival counter that previously changed job_id
            # on every aggregate SCALE signal.
            agent._job_counter = index + 1
            self._queue_admission(
                agent,
                event_id=f"arrival-{index + 1}",
                nodes=200,
                observed_at=float(index * 5),
            )

            signals, metrics = agent.tick(
                sim_time=float(index * 5),
                dt_seconds=5.0,
            )
            self.assertEqual(len(signals), 1)
            signal = signals[0]
            stable_job_ids.append(signal.job_id)
            self.assertEqual(
                signal.event_type,
                WorkloadEventType.STARTING if index == 0 else WorkloadEventType.SCALE,
            )
            gpu.apply_signal(signal)

            expected_nodes = (index + 1) * 200
            self.assertEqual(metrics.admitted_nodes, expected_nodes)
            self.assertEqual(
                sum(gpu._node_counts.values()),
                expected_nodes,
                "GPU aggregate nodes must match the scheduler's admitted nodes.",
            )
            self.assertLessEqual(
                sum(gpu._node_counts.values()),
                agent.config.max_nodes * 1.10,
                "Repeated arrivals must never inflate GPU nodes beyond fleet capacity.",
            )

            expected_forecast_mw = (
                expected_nodes
                * GENERIC_FALLBACK_PROFILE.rated_kw
                * site.pue_base
                / 1000.0
            )
            self.assertAlmostEqual(gpu.target_output_mw(), expected_forecast_mw)

        self.assertEqual(
            set(stable_job_ids),
            {"kube-admission-default"},
            "All aggregate signals from one KubeDemandAgent must share one job_id.",
        )

    def test_tenants_use_distinct_stable_aggregate_identities(self):
        """Multi-tenant agents remain separate while each agent stays stable."""
        agent_a = self._make_agent("A")
        agent_b = self._make_agent("B")

        self._queue_admission(agent_a, event_id="a-1", nodes=100, observed_at=0.0)
        self._queue_admission(agent_b, event_id="b-1", nodes=100, observed_at=0.0)

        signals_a, _ = agent_a.tick(sim_time=0.0, dt_seconds=5.0)
        signals_b, _ = agent_b.tick(sim_time=0.0, dt_seconds=5.0)

        self.assertEqual(signals_a[0].job_id, "kube-admission-A")
        self.assertEqual(signals_b[0].job_id, "kube-admission-B")
        self.assertNotEqual(signals_a[0].job_id, signals_b[0].job_id)