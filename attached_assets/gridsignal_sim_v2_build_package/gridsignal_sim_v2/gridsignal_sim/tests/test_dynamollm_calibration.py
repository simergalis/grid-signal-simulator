from __future__ import annotations

import pytest

from core.asset_modules import GPUModule
from core.dynamollm_calibration import (
    DYNAMOLLM_DEFAULT_MODEL_ID,
    DYNAMOLLM_H100_CHASSIS_RATED_KW,
    DYNAMOLLM_TABLE_III_SINGLEPOOL_ENERGY_WH,
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
    node_count: int = 8,
) -> WorkloadSignal:
    return WorkloadSignal(
        event_id=f"event-{model_id or workload_class.value}",
        job_id="job-1",
        event_type=WorkloadEventType.RUNNING,
        timestamp=0.0,
        hardware_profile_id="hopper_8gpu_air",
        node_count=node_count,
        workload_class=workload_class,
        site_id="site-1",
        model_id=model_id,
    )


def test_hopper_profile_preserves_chassis_envelope_and_figure8_context():
    profile = DEFAULT_HARDWARE_LIBRARY["hopper_8gpu_air"]
    assert profile.rated_kw == pytest.approx(DYNAMOLLM_H100_CHASSIS_RATED_KW)
    assert profile.rated_kw / profile.gpus_per_unit == pytest.approx(1.275)
    assert DEFAULT_HARDWARE_LIBRARY["enterprise_8gpu_air"].rated_kw == profile.rated_kw


def test_table_iii_singlepool_duration_multiplier_is_ordered_and_exact():
    small = dynamollm_model_multiplier(WorkloadClass.INFERENCE, "llama2-13b")
    medium = dynamollm_model_multiplier(WorkloadClass.INFERENCE, "llama2-70b")
    large = dynamollm_model_multiplier(WorkloadClass.INFERENCE, "falcon-180b")
    reference = DYNAMOLLM_TABLE_III_SINGLEPOOL_ENERGY_WH["llama2-70b"]
    assert small == pytest.approx(
        DYNAMOLLM_TABLE_III_SINGLEPOOL_ENERGY_WH["llama2-13b"] / reference
    )
    assert medium == pytest.approx(1.0)
    assert large == pytest.approx(
        DYNAMOLLM_TABLE_III_SINGLEPOOL_ENERGY_WH["falcon-180b"] / reference
    )
    assert small < medium < large


def test_inference_without_model_uses_70b_reference():
    assert DYNAMOLLM_DEFAULT_MODEL_ID == "llama2-70b"
    assert dynamollm_model_multiplier(WorkloadClass.INFERENCE, None) == pytest.approx(1.0)


def test_dynamollm_applies_only_to_explicit_inference():
    assert dynamollm_model_multiplier(WorkloadClass.TRAINING, "falcon-180b") == 1.0
    assert dynamollm_model_multiplier(WorkloadClass.CHECKPOINTING, "llama2-70b") == 1.0
    assert dynamollm_model_multiplier(WorkloadClass.INFERENCE, "unknown-model") == 1.0


def test_gpu_current_and_target_draw_never_apply_energy_ratio_to_power():
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

    expected = 8 * 10.2 / 1000.0
    assert gpu.per_job_target_mw("job-1") == pytest.approx(expected)
    assert gpu.output_mw() == pytest.approx(expected)
    # The model changes modeled work duration, not the 10.2 kW per-chassis
    # hardware envelope.  With one chassis, instantaneous draw is never above
    # its rated/nameplate draw regardless of model.
    one_chassis = GPUModule(asset_id="gpu-2", site=site, hardware_library=library)
    one_chassis.apply_signal(_running_signal(
        workload_class=WorkloadClass.INFERENCE,
        model_id="falcon-180b",
        node_count=1,
    ))
    assert one_chassis.per_job_target_mw("job-1") <= (10.2 / 1000.0) + 1e-12


def test_kube_uses_model_ratio_on_duration_not_power():
    base = KubeDemandAgent(KubeConfig(
        max_nodes=10,
        min_nodes=0,
        model_id="llama2-70b",
    ))
    large = KubeDemandAgent(KubeConfig(
        max_nodes=10,
        min_nodes=0,
        model_id="falcon-180b",
    ))
    assert base._model_duration_multiplier() == pytest.approx(1.0)
    assert large._model_duration_multiplier() == pytest.approx(10.34 / 5.44)
    assert large._model_duration_multiplier() > base._model_duration_multiplier()


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