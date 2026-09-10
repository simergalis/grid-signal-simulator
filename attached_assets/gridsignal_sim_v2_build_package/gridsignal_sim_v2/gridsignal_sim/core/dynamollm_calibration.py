"""Published DynamoLLM calibration constants.

The values in this module are deliberately narrow in scope.  DynamoLLM
characterizes inference energy for medium-sized requests at medium load; it
does not provide a training or checkpointing power model.  Table III reports
Wh per request, not instantaneous kW.  Therefore the model multiplier is a
duration/energy multiplier and must never be multiplied into hardware power.

Source:
    J. Stojkovic, C. Zhang, I. Goiri, J. Torrellas, and E. Choukse,
    "DynamoLLM: Designing LLM Inference Clusters for Performance and Energy
    Efficiency," HPCA 2025, Fig. 8 and Table III.
    https://arxiv.org/html/2408.00741v1

Table III values below are the SinglePool baseline: TP8 at the highest tested
GPU frequency (1980 MHz / the paper's 2.0 GHz table column).  This is the
state-of-practice fixed configuration used before DynamoLLM's dynamic
optimization, so it is the representative baseline for an unoptimized
design-partner cluster.  The full table's observed range is 0.98--10.34
Wh/request.
"""

from __future__ import annotations

from typing import Mapping

from .models import WorkloadClass


DYNAMOLLM_CITATION = (
    "Stojkovic et al., DynamoLLM: Designing LLM Inference Clusters for "
    "Performance and Energy Efficiency, HPCA 2025, Fig. 8 and Table III "
    "(arXiv:2408.00741v1)"
)

# Figure 8's GPU-power bars are approximately 250--800 W/GPU across the
# P50/P90/P99 operating points and evaluated systems.  This validates using a
# dynamic workload factor against a chassis envelope; it does not justify a
# flat 300 W/GPU assumption.  The simulator's H100 profile is 10.2 kW/chassis
# = 1.275 kW/GPU and is retained as a conservative chassis/nameplate envelope
# that includes host, memory, networking, and cooling overhead.
DYNAMOLLM_FIGURE8_GPU_POWER_RANGE_W = (250.0, 800.0)
# Approximate visual range read from the Cluster Power [kW] panel in Fig. 8.
DYNAMOLLM_FIGURE8_CLUSTER_POWER_RANGE_KW = (18.0, 56.0)
DYNAMOLLM_H100_CHASSIS_RATED_KW = 10.2

# Table III, medium request / medium load, SinglePool baseline by model.
# SinglePool is TP8 at 1980 MHz.  The values remain explicit so a future
# calibration can replace them with a request-shape-specific table rather than
# silently changing the baseline.
DYNAMOLLM_TABLE_III_SINGLEPOOL_ENERGY_WH: Mapping[str, float] = {
    "llama2-13b": 3.45,
    "mixtral-8x7b": 4.66,
    "llama2-70b": 5.44,
    "llama3-70b": 6.45,
    "mixtral-8x22b": 4.03,
    "falcon-180b": 10.34,
}
DYNAMOLLM_DEFAULT_MODEL_ID = "llama2-70b"
DYNAMOLLM_REFERENCE_ENERGY_WH = DYNAMOLLM_TABLE_III_SINGLEPOOL_ENERGY_WH[
    DYNAMOLLM_DEFAULT_MODEL_ID
]


def normalize_dynamollm_model_id(model_id: str | None) -> str | None:
    """Normalize common model spellings to the Table III keys."""
    if not model_id:
        return None
    normalized = model_id.strip().lower().replace("_", "-").replace(" ", "")
    aliases = {
        "llama-2-13b": "llama2-13b",
        "llama-2-70b": "llama2-70b",
        "llama-3-70b": "llama3-70b",
        "mixtral-8x7b-instruct": "mixtral-8x7b",
        "mixtral-8x22b-instruct": "mixtral-8x22b",
        "falcon180b": "falcon-180b",
    }
    return aliases.get(normalized, normalized)


def dynamollm_model_multiplier(
    workload_class: WorkloadClass | str | None,
    model_id: str | None,
) -> float:
    """Return the inference duration/energy multiplier.

    Table III is Wh/request, so this ratio belongs on the modeled request
    duration (or an equivalent work quantity), not on instantaneous hardware
    power.  The default reference model is Llama2-70B.  Unknown explicit
    models and non-inference workloads intentionally return 1.0.
    """
    try:
        workload = WorkloadClass(workload_class) if workload_class is not None else None
    except ValueError:
        workload = None
    if workload is not WorkloadClass.INFERENCE:
        return 1.0
    model_key = normalize_dynamollm_model_id(model_id)
    if model_key is None:
        model_key = DYNAMOLLM_DEFAULT_MODEL_ID
    energy_wh = (
        DYNAMOLLM_TABLE_III_SINGLEPOOL_ENERGY_WH.get(model_key)
    )
    if energy_wh is None:
        return 1.0
    return energy_wh / DYNAMOLLM_REFERENCE_ENERGY_WH