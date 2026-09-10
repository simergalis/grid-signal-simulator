from __future__ import annotations

import pytest

from core.asset_modules import GPUModule
from core.dynamollm_calibration import (
    DYNAMOLLM_H100_CHASSIS_RATED_KW,
    DYNAMOLLM_TABLE_III_MIN_ENERGY_WH,
    dynamollm_model_multiplier,
)
from core.kube_demand import KubeConfig, KubeDemandAgent
from core.models import (
    HardwareProfile,
    SiteConfig,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from runtime.scenario_factory import DEFAULT_HARDWARE_LIBRARY


def _running_signal(
    *,
    workload_class: WorkloadClass,
    model_id: str | None = None,
) -> WorkloadSignal:
    return WorkloadSignal(
        event_id=f"event-{model_id or workload_class.value}",
        job_id="job-1",
        event_type=WorkloadEventType.RUNNING,
        timestamp=0.0,
        hardware_profile_id="hopper_8gpu_air",
        node_count=8,
        workload_class=workload_class,
        site_id="site-1",
        model_id=model_id,
    )


def test_hopper_profile_preserves_chassis_envelope_and_figure8_context():
    profile = DEFAULT_HARDWARE_LIBRARY["hopper_8gpu_air"]
    assert profile.rated_kw == pytest.approx(DYNAMOLLM_H100_CHASSIS_RATED_KW)
    assert profile.rated_kw / profile.gpus_per_unit == pytest.approx(1.275)
    assert DEFAULT_HARDWARE_LIBRARY["enterprise_8gpu_air"].rated_kw == profile.rated_kw


def test_table_iii_model_multiplier_is_ordered_and_exact():
    small = dynamollm_model_multiplier(WorkloadClass.INFERENCE, "llama2-13b")
    medium = dynamollm_model_multiplier(WorkloadClass.INFERENCE, "llama2-70b")
    large = dynamollm_model_multiplier(WorkloadClass.INFERENCE, "falcon-180b")
    assert small == pytest.approx(DYNAMOLLM_TABLE_III_MIN_ENERGY_WH["llama2-13b"] / 0.98)
    assert medium == pytest.approx(DYNAMOLLM_TABLE_III_MIN_ENERGY_WH["llama2-70b"] / 0.98)
    assert large == pytest.approx(DYNAMOLLM_TABLE_III_MIN_ENERGY_WH["falcon-180b"] / 0.98)
    assert small < medium < large


def test_dynamollm_applies_only_to_explicit_inference():
    assert dynamollm_model_multiplier(WorkloadClass.TRAINING, "falcon-180b") == 1.0
    assert dynamollm_model_multiplier(WorkloadClass.CHECKPOINTING, "llama2-70b") == 1.0
    assert dynamollm_model_multiplier(WorkloadClass.INFERENCE, "unknown-model") == 1.0


def test_gpu_current_and_target_draw_apply_model_factor_once():
    site = SiteConfig(
        frequency_nominal_hz=50.0,
        power_factor=0.85,
        site_id="site-1",
        pue_base=1.0,
    )
    library = {"hopper_8gpu_air": HardwareProfile("hopper_8gpu_air", rated_kw=10.2)}
    gpu = GPUModule(asset_id="gpu-1", site=site, hardware_library=library)
    gpu.apply_signal(_running_signal(
        workload_class=WorkloadClass.INFERENCE,
        model_id="llama2-70b",
    ))

    expected = 8 * 10.2 / 1000.0 * (3.91 / 0.98)
    assert gpu.per_job_target_mw("job-1") == pytest.approx(expected)
    assert gpu.output_mw() == pytest.approx(expected)


def test_kube_signal_carries_inference_model_metadata():
    agent = KubeDemandAgent(KubeConfig(
        max_nodes=10,
        min_nodes=0,
        mean_interarrival_s=1000.0,
        model_id="llama3-70b",
    ))
    signals, _ = agent.tick(sim_time=0.0, dt_seconds=5.0, grid_state=None)
    assert len(signals) == 1
    assert signals[0].workload_class is WorkloadClass.INFERENCE
    assert signals[0].model_id == "llama3-70b"