"""
api/schemas.py — Pydantic request / response models for the HTTP API.

Step 6 / v2.5 §8.1.
Step 8: adds ScenarioSpec + related models; removes F1 scenario_preset scaffolding.
Step 9: adds AssertionSpec (imported from runtime.verdict) + ScenarioSpec.assertions;
        adds RunResultResponse and TimeseriesResponse for the results screen.

No imports from core/ — the wire format is owned here; core/models.py
is the authoritative in-process representation and is not exposed
directly to callers.

The import of AssertionSpec from runtime.verdict (api/ → runtime/) is an allowed
direction per §21.1; runtime/ → api/ is the forbidden direction.
"""

from __future__ import annotations

import uuid as _uuid
import math as _math
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from runtime.fuel_cell_defaults import DEFAULT_BLOCK_FUEL_CELL_HOT_START_S
# Step 9: AssertionSpec lives in runtime/verdict.py so that runtime/ code can
# import it without creating a runtime/ → api/ circular dependency.
from runtime.verdict import AssertionSpec  # noqa: F401 (re-exported for callers)


_INTERNAL_SCENARIO_PATH_REFERENCES = (
    "gridsignal_sim/tests/test_unit_trip.py",
    "gridsignal_sim/tests/test_aggregate_sources.py",
    "gridsignal_sim/tests/test_13_2_balance_decomp.py",
    "tests/test_unit_trip.py",
    "tests/test_aggregate_sources.py",
    "tests/test_13_2_balance_decomp.py",
)


def sanitize_scenario_payload(value: Any) -> Any:
    """Remove the internal test paths that must never become scenario data.

    Scenario specs can be created through the editor, uploads, Ask Gridley,
    seeded JSON, and API clients.  Keeping the rule here makes each route
    produce the same portable, operator-facing payload.
    """
    if isinstance(value, str):
        sanitized = value
        for path in _INTERNAL_SCENARIO_PATH_REFERENCES:
            sanitized = sanitized.replace(path, "")
        return " ".join(sanitized.split())
    if isinstance(value, list):
        return [sanitize_scenario_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_scenario_payload(item) for item in value)
    if isinstance(value, dict):
        return {
            key: sanitize_scenario_payload(item)
            for key, item in value.items()
        }
    return value


# ---------------------------------------------------------------------------
# Step 11: PMS config schema (AB1)
# ---------------------------------------------------------------------------

class PmsConfigSpec(BaseModel):
    """Wire-format mirror of core.models.PmsConfig.

    All fields match the dataclass fields exactly so that
    ``PmsConfig(...)`` wiring in build_run_context_from_spec is safe
    without any field-name translation.

    transition_mode must be one of the TransitionMode string values:
      "open_transition"   — default; brief coverage gap during reconnect
                            (open_transition_gap_mw for open_transition_duration_s).
      "closed_transition" — instantaneous; no coverage gap.

    shed_priority_order: list of workload job_ids to shed first (highest
    priority first).  Empty list → PMS sheds in arbitrary order.

    All bounds are CHOSEN (PROTO-11).
    """
    shed_priority_order: list[str] = Field(default_factory=list)
    transition_mode: Literal["open_transition", "closed_transition"] = "open_transition"
    open_transition_gap_mw: float = Field(default=2.0, ge=0.0)
    open_transition_duration_s: float = Field(default=5.0, gt=0.0)
    fast_shed_duration_s: float = Field(default=30.0, gt=0.0)


# ---------------------------------------------------------------------------
# Step 10: Pre-staging config schema (AA1)
# ---------------------------------------------------------------------------

class PreStagingConfigSpec(BaseModel):
    """Wire-format mirror of core.models.PreStagingConfig.

    All fields match the dataclass fields exactly so that
    ``PreStagingConfig(**spec_data["pre_staging_config"])`` is safe in
    build_run_context_from_spec without any field-name translation.

    All values are CHOSEN (PROTO-10).  See core/models.py PreStagingConfig
    for the hold-analysis and design rationale.
    """
    max_shift_mw: float = Field(default=1.0, ge=0.0, le=50.0)
    inlet_temp_low_c: float = Field(default=18.0, ge=10.0, le=30.0)
    inlet_temp_high_c: float = Field(default=24.0, ge=15.0, le=35.0)
    cooling_gain_c_per_mw_s: float = Field(default=0.05, gt=0.0)
    warmup_rate_c_per_s: float = Field(default=0.002, ge=0.0)
    initial_temp_c: float = Field(default=21.0, ge=10.0, le=35.0)
    bms_override: bool = False
    # Two-phase thermal SoC fields (§8.1 load-shifting, not curtailment).
    # thermal_soc_initial_mwh: pre-charged thermal energy at run start (MWh).
    #   0.0 = no stored energy; engine must charge before it can discharge.
    # eta: charge-phase efficiency (dimensionless, 0 < η ≤ 1).
    thermal_soc_initial_mwh: float = Field(default=0.0, ge=0.0)
    eta: float = Field(default=0.9, gt=0.0, le=1.0)


# ---------------------------------------------------------------------------
# AD1: Procurement config schema (TC-47, TC-52)
# ---------------------------------------------------------------------------

class ProcurementConfigSpec(BaseModel):
    """Wire-format config for §24 grid procurement (ProcurementLayer).

    Gates whether a ProcurementLayer is instantiated in the run context.
    The layer calls NonFirmImportEffect.apply() (TC-47) and creates
    ReservationProposal objects (TC-52) each tick when reserve_gap > 0.

    All capacity values are CHOSEN (PROTO-AD1).
    """
    firm_available_mw: float = Field(default=20.0, ge=0.0)
    reserved_available_mw: float = Field(default=10.0, ge=0.0)
    non_firm_available_mw: float = Field(default=3.0, ge=0.0)
    price_curve_seed: int = Field(default=42, ge=0)


# ---------------------------------------------------------------------------
# AD1: Maintenance config schema (TC-58, TC-59, TC-60)
# ---------------------------------------------------------------------------

class MaintenanceConfigSpec(BaseModel):
    """Wire-format config for §27 prescriptive maintenance (MaintenanceLayer).

    Gates whether a MaintenanceLayer is instantiated in the run context.
    The layer calls reserve_contribution_mw_per_s() (TC-58), validate_window()
    (TC-59), and propose_rating_change() (TC-60) during live runs.

    effective_ramp_mw_per_s < nameplate_ramp_mw_per_s → asset starts DEGRADED,
    so the first propose_rating_change() call is a RAISE (TC-60 requires
    confirmation; reduction is immediate).

    All values are CHOSEN (PROTO-AD1).
    """
    asset_id: str = "turbine-0"
    nameplate_ramp_mw_per_s: float = Field(default=0.2, gt=0.0)
    effective_ramp_mw_per_s: float = Field(default=0.15, gt=0.0)
    reserve_threshold_mw: float = Field(default=1.0, ge=0.0)


# ---------------------------------------------------------------------------
# AD1: Ramp relaxation config schema (TC-75, TC-76)
# ---------------------------------------------------------------------------

class RampRelaxationConfigSpec(BaseModel):
    """Wire-format config for §23.7.2 adaptive ramp relaxation (RampRelaxationEngine).

    Gates whether a RampRelaxationEngine is instantiated in the run context.
    The engine's evaluate() runs each tick (TC-75: upper-bound reserve check;
    TC-76: gridSignal_connected=False reverts to baseline — tested via unit test,
    but the evaluate() path is exercised every demo tick).

    All values are CHOSEN (PROTO-AD1).
    """
    reserve_threshold_mw: float = Field(default=2.0, ge=0.0)
    baseline_ramp_cap_mw: float = Field(default=5.0, gt=0.0)
    baseline_ramp_duration_s: float = Field(default=75.0, gt=0.0)
    adaptive_ramp_duration_s: float = Field(default=30.0, gt=0.0)


# ---------------------------------------------------------------------------
# Step 8: Scenario schemas
# ---------------------------------------------------------------------------

class WorkloadEventSpec(BaseModel):
    """One scripted workload event (GPU job or renewable step) within a scenario.

    event_type must be a WorkloadEventType string value:
      "starting"   — GPU job ramp begins; staging fires with dt_lead_seconds.
      "job_end"    — GPU job finishes.
      "solar_step" — Renewable curtailment; staging fires with dt_lead=0 (§7.1.1).
      "unit_trip"  — Force a generating unit offline immediately (TC-84/G-2).
                     job_id carries a turbine or fuel-cell asset_id. For a
                     block fuel-cell array, electrical_group_id optionally
                     addresses one declared group; omission trips the array.
                     node_count and hardware_profile_id are ignored.
      Any other WorkloadEventType value is forwarded as-is.

    For solar_step events job_id, node_count, and hardware_profile_id are
    ignored by the runtime; renewable_shortfall_mw carries the staging delta.
    """
    event_id: str = Field(default_factory=lambda: f"evt-{_uuid.uuid4().hex[:8]}")
    job_id: str = ""
    event_type: str  # WorkloadEventType string value
    timestamp: float = Field(ge=0.0)
    node_count: int = Field(default=0, ge=0)
    hardware_profile_id: str = "enterprise_8gpu_air"
    workload_class: Literal["training", "inference", "other"] = "training"
    scheduler_domain: Optional[str] = None
    # Scheduler provenance for deterministic scripted jobs.  These fields let
    # scenario-authored workload events retain the same K8S/SLURM/RAY identity
    # used by live scheduler ingestion and the multi-cluster kube path.
    tenant_id: Optional[str] = None
    cluster_id: Optional[str] = None
    scheduler_type: Optional[Literal["SLURM", "K8S", "RAY"]] = None
    capacity_unit: Optional[str] = None
    gpus_per_unit: int = Field(default=1, ge=1)
    request_rate: Optional[float] = Field(default=None, ge=0.0)
    # §7.1.1 SOLAR_STEP: magnitude of the renewable drop that triggers staging.
    # Zero for all other event types.
    renewable_shortfall_mw: float = Field(default=0.0, ge=0.0)
    electrical_group_id: Optional[str] = None


class SlurmJobPayload(BaseModel):
    """The slurmrestd GET /slurm/v0.0.40/jobs job shape used for ingestion.

    slurmrestd adds fields over time and different clusters expose optional
    fields differently, so the model validates the fields needed to build a
    WorkloadSignal while preserving the rest of the payload.
    """

    model_config = ConfigDict(extra="allow")

    job_id: int = Field(gt=0)
    job_state: list[str] = Field(min_length=1)
    node_count: int = Field(ge=0)
    # PENDING jobs normally have requested resources but no allocated TRES yet.
    tres_req_str: Optional[str] = None
    tres_alloc_str: Optional[str] = None
    account: Optional[str] = None
    partition: Optional[str] = None


class WorkloadSignalResponse(BaseModel):
    """Public representation of the WorkloadSignal created by an ingest call."""

    event_id: str
    job_id: str
    event_type: str
    timestamp: float
    hardware_profile_id: str
    node_count: int
    workload_class: str
    site_id: str
    queue_depth: Optional[float] = None
    request_rate: Optional[float] = None
    scheduler_domain: Optional[str] = None
    tenant_id: Optional[str] = None
    cluster_id: Optional[str] = None
    scheduler_type: Optional[str] = None
    capacity_unit: Optional[str] = None
    gpus_per_unit: int = 1


class BessUnitSpec(BaseModel):
    """One BESS unit within a scenario's fleet."""
    asset_id: str
    rated_mw: float = Field(gt=0)
    usable_mwh: float = Field(gt=0)
    initial_soc_fraction: float = Field(default=0.95, ge=0.1, le=1.0)
    # §7.1.2: at most one unit per scenario may be the grid-forming anchor.
    # Validated at the ScenarioSpec level.
    grid_forming: bool = False
    # PW-3 / §15: explicit per-unit anchor-reserve override (MW).
    # When present, build_run_context_from_spec uses this value directly instead
    # of deriving from anchor_reserve_pct.  1.0 MW is the BessConfig default
    # (PROTO-9 / CHOSEN).  San Diego demo scenario uses 2.0 MW explicitly.
    p_anchor_reserve_mw: float = Field(default=1.0, ge=0.0)
    # PSP-002 §2.1: dispatch authority tier.
    # "autonomous": EDL allocates without operator action (default).
    # "confirm": operator/PMS must confirm before dispatch.
    # "human_only": operator must command directly; always escalated on shortfall.
    authority_tier: Optional[str] = Field(
        default="autonomous",
        pattern=r"^(autonomous|confirm|human_only)$",
    )

    def c_rate(self) -> float:
        return self.rated_mw / self.usable_mwh

    def c_rate_warning(self) -> Optional[str]:
        """D12 / PROTO-9: warn if C-rate is outside 0.25–4.0 C.
        Returns None when within bounds.  Callers include the warning as a
        response field; it never causes a 400 (the bound is chosen, not
        measured)."""
        c = self.c_rate()
        if not (0.25 <= c <= 4.0):
            return (
                f"{self.asset_id}: C-rate {c:.2f} C outside 0.25–4.0 C "
                f"(PROTO-9 — chosen, no measured basis; "
                f"rated_mw={self.rated_mw}, usable_mwh={self.usable_mwh})"
            )
        return None


class FuelCellElectricalGroupSpec(BaseModel):
    electrical_group_id: str = Field(min_length=1)
    block_count: int = Field(gt=0)

    @model_validator(mode="after")
    def _meaningful_name(self) -> "FuelCellElectricalGroupSpec":
        name = self.electrical_group_id.strip()
        if not name or not any(character.isalpha() for character in name):
            raise ValueError(
                "electrical_group_id must be a human-meaningful name containing a letter"
            )
        self.electrical_group_id = name
        return self


class FuelCellUnitSpec(BaseModel):
    """A block-addressable fuel-cell unit (Addendum G-1).

    Capacity is deliberately derived from ``block_rated_mw * block_count``.
    There is no independently authorable ``rated_mw`` field for this model.
    """

    asset_id: str = Field(min_length=1)
    block_rated_mw: float = Field(gt=0.0)
    block_count: int = Field(ge=1)
    initial_running_blocks: int = Field(default=0, ge=0)
    initial_hot_standby_blocks: Optional[int] = Field(default=None, ge=0)
    commit_rate_blocks_per_s: float = Field(default=1.0, gt=0.0)
    decommit_rate_blocks_per_s: float = Field(default=1.0, gt=0.0)
    cold_start_s: float = Field(default=8.0 * 60.0 * 60.0, gt=0.0)
    warm_start_s: float = Field(default=4.0 * 60.0 * 60.0, gt=0.0)
    hot_start_s: float = Field(default=DEFAULT_BLOCK_FUEL_CELL_HOT_START_S, gt=0.0)
    controlled_cooling_s: Optional[float] = Field(default=None, gt=0.0)
    hot_standby: bool = True
    min_stable_frac: float = Field(default=0.5, ge=0.0, le=1.0)
    hot_standby_floor_blocks: int = Field(default=0, ge=0)
    dispatch_mechanism: Literal["discrete_blocks", "modulating", "hybrid"] = "hybrid"
    readiness_dwell_s: float = Field(default=0.0, ge=0.0)
    electrical_groups: list[FuelCellElectricalGroupSpec] = Field(default_factory=list)
    beginning_of_life_heat_rate_btu_per_kwh: float = Field(default=5811.0, gt=0)
    end_of_life_heat_rate_btu_per_kwh: float = Field(default=7127.0, gt=0)
    degradation_fraction: float = Field(default=0.5, ge=0, le=1)
    part_load_heat_rate_multiplier: float = Field(default=1.0, gt=0)
    gas_heating_value_btu_per_scf: float = Field(default=1030.0, gt=0)
    hot_standby_fuel_fraction: float = Field(default=0.10, ge=0)
    gas_price_usd_per_mmbtu: Optional[float] = Field(default=5.0, ge=0)
    provenance: Dict[
        str, Literal["vendor_published", "derived", "proposed", "site_specific"]
    ] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _reject_independent_rated_mw(cls, value: Any) -> Any:
        if isinstance(value, dict) and "rated_mw" in value:
            raise ValueError(
                "fuel_cell_units derive rated_mw from block_rated_mw * block_count; "
                "do not provide rated_mw"
            )
        return value

    @model_validator(mode="after")
    def _validate_block_counts(self) -> "FuelCellUnitSpec":
        if self.initial_hot_standby_blocks is None:
            # Operational scenarios assume every non-running block is retained
            # hot unless an explicit diagnostic fixture authors another state.
            self.initial_hot_standby_blocks = (
                self.block_count - self.initial_running_blocks
            )
        if self.initial_running_blocks + self.initial_hot_standby_blocks > self.block_count:
            raise ValueError(
                "initial_running_blocks + initial_hot_standby_blocks cannot exceed block_count"
            )
        if self.hot_standby_floor_blocks > self.block_count:
            raise ValueError("hot_standby_floor_blocks cannot exceed block_count")
        if not self.hot_standby and self.hot_standby_floor_blocks:
            raise ValueError("hot_standby_floor_blocks requires hot_standby=true")
        if not self.hot_start_s <= self.warm_start_s <= self.cold_start_s:
            raise ValueError("expected hot_start_s <= warm_start_s <= cold_start_s")
        ids = [group.electrical_group_id for group in self.electrical_groups]
        if len(ids) != len(set(ids)):
            raise ValueError("electrical group names must be unique within unit")
        if self.electrical_groups and sum(g.block_count for g in self.electrical_groups) != self.block_count:
            raise ValueError("electrical group block_count values must sum exactly to block_count")
        defaults = {
            "beginning_of_life_heat_rate_btu_per_kwh": "vendor_published",
            "end_of_life_heat_rate_btu_per_kwh": "vendor_published",
            "degradation_fraction": "site_specific",
            "part_load_heat_rate_multiplier": "proposed",
            "gas_heating_value_btu_per_scf": "site_specific",
            "hot_standby_fuel_fraction": "proposed",
            "gas_price_usd_per_mmbtu": "site_specific",
        }
        # G-2 assigns these source classes normatively. In particular, callers
        # must never relabel the hot-standby placeholder as vendor-published.
        self.provenance = {**self.provenance, **defaults}
        return self

    @property
    def rated_mw(self) -> float:
        """Derived unit nameplate; omitted from the serialized request model."""
        return self.block_rated_mw * self.block_count


# TODO: When diesel gets a real PowerSource entry wired into
# core/power_source_priority.py / core/economic_dispatch_loop.py in a later
# phase, it MUST be tagged AuthorityTier.CONFIRM, never AUTONOMOUS — diesel
# activation should always surface as a confirmation/escalation candidate,
# never be auto-allocated by EDL.step(). This is a deliberate decision, not a
# placeholder to be picked later.
class DieselPowerBlockSpec(BaseModel):
    """Scenario-author-facing configuration for a diesel power block.

    The default values are intentionally marked PROPOSED_HERE.  They are
    placeholders from Addendum H and are not catalogue-backed validations.
    ``target_capacity_mw`` is the one required author input.
    """

    enabled: bool = False
    target_capacity_mw: float
    unit_rating_mw: float = 3.0
    p_start: float = 0.985
    target_reliability: float = 0.999
    f_block: float = 0.80
    delta_t_start_s: float = 10.0
    residual_ramp_s: float = 8.0
    start_stagger_interval_s: float = 2.0
    debounce_s: float = 1.0
    restore_hold_s: float = 300.0
    min_run_s: float = 900.0
    min_down_s: float = 300.0
    min_stable_load_mw_fraction: float = 0.30
    cooldown_s: float = 300.0
    fuel_burn_gal_per_hr_per_unit_at_full_load: float = 230.0
    fuel_type: Literal["diesel", "hvo"] = "diesel"
    min_fuel_runtime_hours: float = 48.0
    # Deliberately distinct from core.power_source_priority.AuthorityTier
    # (autonomous/confirm/human_only), which gates real EDL allocation
    # eligibility. Diesel has no GridSignal execution path by construction
    # (TC-68); this is advisory metadata only.
    authority_tier: Literal["advisory_only"] = "advisory_only"


class DieselUnitSpec(BaseModel):
    """Materialized per-unit diesel fleet shape.

    This is deliberately a schema-only representation in this phase.  It is
    not a runtime asset configuration and is not consumed by dispatch.
    """

    asset_id: str
    rated_mw: float
    role: Literal["primary", "standby"]
    start_offset_s: Optional[float]
    delta_t_start_s: float
    f_block: float
    residual_ramp_s: float
    min_stable_load_mw: float
    min_run_s: float
    min_down_s: float
    cooldown_s: float
    # Deliberately distinct from core.power_source_priority.AuthorityTier:
    # this is advisory metadata only because diesel has no GridSignal
    # execution path by construction (TC-68).
    authority_tier: Literal["advisory_only"] = "advisory_only"


def binomial_survival(n: int, p: float, k: int) -> float:
    """Return P(X >= k) for X ~ Binomial(n, p).

    This intentionally uses only the Python standard library.  The explicit
    sum keeps the fleet-sizing calculation dependency-free and auditable.
    """
    if n < 0:
        raise ValueError(f"binomial n must be non-negative (got {n})")
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"binomial p must be between 0 and 1 (got {p})")
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return sum(
        _math.comb(n, i) * p**i * (1.0 - p) ** (n - i)
        for i in range(k, n + 1)
    )


def solve_min_fleet_size(
    n_active: int,
    p_start: float,
    target_reliability: float,
    max_n_total: Optional[int] = None,
) -> int:
    """Find the smallest total fleet that starts enough primary units.

    ``n_active`` units are required to meet the block target.  Additional
    units are cold standby replacements and are not started at the trigger.
    The guard is intentionally bounded so impossible configurations fail at
    scenario validation instead of hanging.
    """
    if n_active < 1:
        raise ValueError(f"n_active must be at least 1 (got {n_active})")
    if not 0.0 <= p_start <= 1.0:
        raise ValueError(
            f"p_start must be between 0 and 1 (got {p_start})"
        )
    if not 0.0 <= target_reliability <= 1.0:
        raise ValueError(
            "target_reliability must be between 0 and 1 "
            f"(got {target_reliability})"
        )

    if max_n_total is None:
        max_n_total = n_active * 3
    if max_n_total < n_active:
        raise ValueError(
            f"max_n_total ({max_n_total}) cannot be less than "
            f"n_active ({n_active})"
        )

    for n_total in range(n_active, max_n_total + 1):
        if binomial_survival(n_total, p_start, n_active) >= target_reliability:
            return n_total

    raise ValueError(
        "diesel fleet sizing could not reach target reliability: "
        f"need P(X >= {n_active}) >= {target_reliability:.6g} with "
        f"p_start={p_start:.6g}, but max_n_total={max_n_total} "
        "was reached"
    )


def generate_diesel_fleet(
    block: DieselPowerBlockSpec,
) -> list[DieselUnitSpec]:
    """Materialize the block-level diesel configuration into per-unit specs.

    Primary units receive staggered trigger offsets.  Reliability reserve
    units are cold standby: their offset remains ``None`` until a later phase
    activates a specific 1:1 replacement.
    """
    if not block.enabled:
        return []
    if block.target_capacity_mw <= 0.0:
        raise ValueError(
            "diesel_power_block.target_capacity_mw must be greater than 0 "
            f"when enabled (got {block.target_capacity_mw})"
        )
    if block.unit_rating_mw <= 0.0:
        raise ValueError(
            "diesel_power_block.unit_rating_mw must be greater than 0 "
            f"(got {block.unit_rating_mw})"
        )

    n_active = _math.ceil(block.target_capacity_mw / block.unit_rating_mw)
    n_total = solve_min_fleet_size(
        n_active=n_active,
        p_start=block.p_start,
        target_reliability=block.target_reliability,
    )
    min_stable_load_mw = (
        block.unit_rating_mw * block.min_stable_load_mw_fraction
    )

    fleet: list[DieselUnitSpec] = []
    for index in range(n_total):
        is_primary = index < n_active
        fleet.append(
            DieselUnitSpec(
                asset_id=f"diesel-{index:03d}",
                rated_mw=block.unit_rating_mw,
                role="primary" if is_primary else "standby",
                start_offset_s=(
                    index * block.start_stagger_interval_s
                    if is_primary
                    else None
                ),
                delta_t_start_s=block.delta_t_start_s,
                f_block=block.f_block,
                residual_ramp_s=block.residual_ramp_s,
                min_stable_load_mw=min_stable_load_mw,
                min_run_s=block.min_run_s,
                min_down_s=block.min_down_s,
                cooldown_s=block.cooldown_s,
                authority_tier=block.authority_tier,
            )
        )
    return fleet


class TurbineUnitSpec(BaseModel):
    """One turbine unit within a scenario's fleet."""
    asset_id: str
    rated_mw: float = Field(default=10.0, gt=0)
    r_asset_mw_per_s: float = Field(default=0.2, gt=0)
    # Optional operating-hours counter for narrative / re-rating context.
    # None = not tracked (most scenarios).  When set, the fleet modal shows
    # the value in the RUN h column and names the unit in the degraded footnote.
    run_hours_h: Optional[float] = Field(default=None, ge=0)
    # hot_standby: True when this unit is commissioned but not synchronized.
    # Hot-standby units are excluded from dispatch staging and contribute zero
    # to contingency ramp capability (§7.4 / TC-83).  Default False.
    hot_standby: bool = False
    # Phase E §7.1.3.6 / closeout Item 1 — physical constraints (all CHOSEN).
    # p_min_stable_frac: minimum stable load floor as fraction of rated_mw.
    # 0.40 = frame-class representative (PW-1 / §15 / PROTO-R4).
    p_min_stable_frac: float = Field(default=0.40, ge=0.0, le=1.0)
    # t_min_run_s: duration used by the R5 guard when min_run_enabled=True.
    # 1800 s = 30 min — frame-class representative minimum stable operation
    # period before a controlled shutdown (CHOSEN, §7.1.3.6).
    t_min_run_s: float = Field(default=1800.0, ge=0.0)
    # min_run_enabled: D-03 enable flag for the R5 guard.
    # True = command_stop() enforces t_min_run_s; False = constraint disabled.
    # Scenario API always enables it (True default here); unit tests that create
    # TurbineConfig() directly use the False default in the dataclass.
    min_run_enabled: bool = Field(default=True)
    # t_min_down_s: duration used by the R6 guard when min_down_enabled=True.
    # 900 s = 15 min — cooling / purge cycle for frame-class turbines (CHOSEN).
    t_min_down_s: float = Field(default=900.0, ge=0.0)
    # min_down_enabled: D-03 enable flag for the R6 guard.
    # True = command_start() enforces t_min_down_s; False = constraint disabled.
    min_down_enabled: bool = Field(default=True)
    # Start-duration overrides — default None means "use the locked parameter value"
    # from gridsignal_parameters.json (cold=900 s, warm=600 s, hot=300 s).
    # Set per-unit when a scenario needs a non-standard sync time (e.g. a short
    # cold_start_s for a diagnostic run, or an aeroderivative unit).
    # Cross-parameter invariant: hot_start_s < warm_start_s < cold_start_s.
    # Validated by _check_start_duration_ordering below using effective values
    # (None fields resolved to catalogue defaults before comparison).
    cold_start_s: Optional[float] = Field(default=None, gt=0)
    warm_start_s: Optional[float] = Field(default=None, gt=0)
    hot_start_s: Optional[float] = Field(default=None, gt=0)
    # thermal_state: initial thermal classification for this unit at run start.
    # Controls which start-duration path applies on the first command_start().
    # "hot" | "warm" | "cold" (default "cold" — conservative, always safe).
    thermal_state: Optional[str] = Field(default="cold", pattern=r"^(hot|warm|cold)$")
    # Phase 2B (DR-2026-08-08-FREQ): per-unit turbine physics overrides.
    # When None, TurbineConfig defaults (from catalogue) are used.
    # Use these for heterogeneous fleets where individual units differ from
    # the fleet-level catalogue values.
    power_factor: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    inertia_constant_s: Optional[float] = Field(default=None, gt=0.0)
    droop_r: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    valve_actuation_tc_s: Optional[float] = Field(default=None, gt=0.0)
    fuel_to_power_tc_s: Optional[float] = Field(default=None, gt=0.0)
    max_instantaneous_load_step_mw: Optional[float] = Field(default=None, gt=0.0)
    # PSP-002 §2.1: dispatch authority tier per unit.
    authority_tier: Optional[str] = Field(
        default="autonomous",
        pattern=r"^(autonomous|confirm|human_only)$",
    )

    @model_validator(mode="after")
    def _check_start_duration_ordering(self) -> "TurbineUnitSpec":
        """Enforce hot_start_s < warm_start_s < cold_start_s using effective values.

        Each None field is resolved to its locked catalogue default before
        comparison (cold=900 s, warm=600 s, hot=300 s from
        gridsignal_parameters.json).  This means a partial override is also
        validated against the effective triplet the engine will actually use.
        For example, {"hot_start_s": 1000} produces effective hot=1000,
        warm=600, cold=900 — which violates hot < warm and is rejected here
        rather than silently misbehaving in the thermal-state machine.

        A scenario author who only wants to override cold_start_s must supply
        warm_start_s and hot_start_s values that maintain the ordering, or set
        all three together.  Omitting all three (all None) is always valid —
        the engine uses the catalogue defaults which already satisfy the
        invariant.
        """
        # Catalogue defaults: locked in gridsignal_parameters.json.
        _DEFAULT_COLD_S = 900.0
        _DEFAULT_WARM_S = 600.0
        _DEFAULT_HOT_S = 300.0

        cold = self.cold_start_s if self.cold_start_s is not None else _DEFAULT_COLD_S
        warm = self.warm_start_s if self.warm_start_s is not None else _DEFAULT_WARM_S
        hot = self.hot_start_s if self.hot_start_s is not None else _DEFAULT_HOT_S

        # If all three are None the effective values are the defaults, which
        # already satisfy the ordering.  Skip the check to avoid spurious errors
        # when no overrides are present.
        if self.cold_start_s is None and self.warm_start_s is None and self.hot_start_s is None:
            return self

        violations: list[str] = []
        if not (hot < warm):
            violations.append(
                f"effective hot_start_s ({hot} s) must be < warm_start_s ({warm} s)"
            )
        if not (warm < cold):
            violations.append(
                f"effective warm_start_s ({warm} s) must be < cold_start_s ({cold} s)"
            )
        if violations:
            # Annotate which values came from defaults to aid diagnosis.
            sources = {
                "cold_start_s": f"{cold} s" + ("" if self.cold_start_s is not None else " [default]"),
                "warm_start_s": f"{warm} s" + ("" if self.warm_start_s is not None else " [default]"),
                "hot_start_s": f"{hot} s" + ("" if self.hot_start_s is not None else " [default]"),
            }
            raise ValueError(
                f"TurbineUnitSpec {self.asset_id!r}: start-duration ordering violated "
                f"(required hot_start_s < warm_start_s < cold_start_s after resolving "
                f"None fields to catalogue defaults). "
                f"Effective values: cold={sources['cold_start_s']}, "
                f"warm={sources['warm_start_s']}, hot={sources['hot_start_s']}. "
                + "; ".join(violations) + "."
            )
        return self


class StepTimingConfigSpec(BaseModel):
    """Wire-format mirror of core.step_config.StepTimingConfig.

    All defaults match the spec document (SPEC_DEFAULT).  Only override fields
    whose values differ from the default; the engine fills in the rest.
    """
    median_step_s: float = Field(default=0.70, gt=0.0, description="Median inter-step gap (s). SPEC_DEFAULT.")
    step_cv: float = Field(default=0.08, ge=0.0, le=1.0, description="Lognormal CV. SPEC_DEFAULT.")
    tau_drift_s: float = Field(default=300.0, gt=0.0, description="OU mean-reversion time (s). SPEC_DEFAULT.")
    sigma_drift: float = Field(default=0.03, ge=0.0, description="OU diffusion (dimensionless). SPEC_DEFAULT.")
    p_straggler: float = Field(default=0.02, ge=0.0, le=1.0, description="Straggler injection probability. SPEC_DEFAULT.")
    straggler_scale: float = Field(default=1.5, gt=0.0, description="Exponential straggler scale. SPEC_DEFAULT.")
    straggler_max: float = Field(default=10.0, gt=1.0, description="Hard cap on straggler multiplier. SPEC_DEFAULT.")
    ckpt_interval_steps: int = Field(default=400, ge=1, description="Steps between checkpoint long-steps. SPEC_DEFAULT.")
    ckpt_jitter_steps: int = Field(default=40, ge=0, description="±Uniform jitter on checkpoint interval. SPEC_DEFAULT.")
    ckpt_min_s: float = Field(default=5.0, gt=0.0, description="Checkpoint step minimum duration (s). SPEC_DEFAULT.")
    ckpt_max_s: float = Field(default=30.0, gt=0.0, description="Checkpoint step maximum duration (s). SPEC_DEFAULT.")


class LoadProfileConfigSpec(BaseModel):
    """Wire-format mirror of core.step_config.LoadProfileConfig.

    Controls the within-step compute load profile that makes step events
    physically present in compute_load_mw.  All defaults are SPEC_DEFAULT.
    """
    f_compute: float = Field(default=0.72, ge=0.0, le=1.0, description="Compute-phase fraction. SPEC_DEFAULT.")
    p_comm_ratio: float = Field(default=0.55, ge=0.0, le=1.0, description="Relative power during allreduce. SPEC_DEFAULT.")
    tau_gpu_s: float = Field(default=0.06, gt=0.0, description="GPU power transition lag (s). SPEC_DEFAULT.")
    phase_coherence: float = Field(default=0.85, ge=0.0, le=1.0, description="Fleet phase coherence. SPEC_DEFAULT.")
    noise_sigma_fraction: float = Field(default=0.005, ge=0.0, le=0.1, description="Noise sigma as fraction of base draw. CHOSEN.")


class KubeConfigSpec(BaseModel):
    """Kubernetes gang-admission demand simulator configuration.

    When present on a ScenarioSpec, the simulator replaces the scripted
    workload-event path with a discrete gang-admission simulator that models
    steps 1–2 of the Kubernetes-to-turbine path:

      1. OBSERVE:  Poisson-arrival jobs enter a 10-second reorder buffer,
         simulating an in-cluster informer watching Kueue/Volcano objects.
      2. MAP TO CONTRACT: Each admitted gang emits a WorkloadSignal with
         node_count and hardware_profile_id.  Steps 3–8 (P_compute formula,
         thermal lag, BESS arbitration, turbine ramp) run unchanged in the
         scheduler-agnostic core pipeline.

    dt_lead = 0 throughout — Kubernetes gives no advance notice to the grid.

    Use rng_seed for deterministic replay; rng_seed=None gives time-seeded variety.
    Activate stochastic step timing by supplying step_config; activate the
    within-step load profile by supplying load_config.
    """
    hardware_profile_id: str = "enterprise_8gpu_air"

    # Fleet sizing
    max_nodes: int = Field(default=1900, ge=1)
    min_nodes: int = Field(default=200, ge=1,
                           description="Idle-baseline nodes — cluster never fully drains")

    # Gang-admission arrival pattern (Poisson process)
    mean_interarrival_s: float = Field(
        default=60.0, ge=5.0, le=3600.0,
        description="Mean simulated seconds between successive gang admissions",
    )

    # Job size distribution (Gaussian, clipped)
    mean_job_nodes: int = Field(default=200, ge=1,
                                description="Mean gang size in nodes")
    job_node_std: float = Field(default=80.0, ge=0.0,
                                description="Std deviation of gang size")
    min_job_nodes: int = Field(default=50, ge=1,
                               description="Minimum nodes per admission")
    max_job_nodes: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Per-job scheduling-unit ceiling. When omitted, the legacy "
            "max_nodes/2 fallback is used."
        ),
    )

    # Job duration distribution (exponential, clipped)
    mean_job_duration_s: float = Field(default=300.0, ge=10.0,
                                       description="Mean job duration in sim-seconds")
    min_job_duration_s: float = Field(default=30.0, ge=5.0,
                                      description="Minimum job duration in sim-seconds")

    # Reorder buffer and NTP jitter
    reorder_window_s: float = Field(
        default=10.0, ge=0.0, le=60.0,
        description="Events drain from buffer after this many sim-seconds",
    )
    ntp_jitter_s: float = Field(
        default=2.0, ge=0.0, le=10.0,
        description="±seconds of NTP jitter added to event timestamps",
    )

    # Power-cap threshold
    headroom_threshold_mw: float = Field(
        default=2.5, ge=0.0,
        description="Grid headroom below which new admissions are held",
    )

    rng_seed: Optional[int] = None

    # ── Stochastic step timing (spec Part 1) ──────────────────────────────────
    # None (default) = step scheduler off; period falls back to no step events.
    step_config: Optional[StepTimingConfigSpec] = None

    # ── Within-step load profile (spec Part 2) ───────────────────────────────
    # None (default) = no profile modulation; compute_load_mw is a pure ramp.
    load_config: Optional[LoadProfileConfigSpec] = None

    @model_validator(mode="after")
    def _validate_job_unit_bounds(self) -> "KubeConfigSpec":
        if (
            self.max_job_nodes is not None
            and self.max_job_nodes < self.min_job_nodes
        ):
            raise ValueError(
                "max_job_nodes must be greater than or equal to min_job_nodes"
            )
        return self


class KubeClusterSpec(KubeConfigSpec):
    """One independently capacity-constrained scheduler cluster."""

    cluster_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    scheduler_type: Literal["SLURM", "K8S", "RAY"]
    capacity_unit: Literal["node", "rack"] = "node"
    workload_share: float = Field(gt=0.0, le=1.0)


class DqInjectEvent(BaseModel):
    """A scripted data-quality tag injection window.

    Activates ``tag`` (a DataQualityTag value string, e.g. ``"invalid_payload"``)
    for every tick where ``start_s <= sim_time < end_s``.  The effect is identical
    to the tag firing naturally: the confidence band widens and the low-confidence
    interlock blocks autonomous curtailment.

    Multiple windows may overlap; each is additive.
    Validated tag strings: unmapped_hardware, uncalibrated_site, invalid_payload,
    stale_profile, workload_signal_stale, workload_signal_absent.
    """
    start_s: float = Field(ge=0.0, description="Sim-time (seconds) at which the tag becomes active.")
    end_s:   float = Field(ge=0.0, description="Sim-time (seconds) at which the tag clears (exclusive).")
    tag:     str   = Field(description="DataQualityTag value string to inject.")


# ── Tenant workload event support ─────────────────────────────────────────────
# Mirror of frontend ComputeRacksModal SHOWN_TENANTS contractedMW values.
# The GPU_TDP_MW constant is the only place in the backend that encodes the
# H100 SXM5 TDP — any change here must match the frontend GPU_TDP_MW constant.
TENANT_CONTRACTED_MW: dict[str, float] = {
    "a": 1.40, "b": 1.00, "c": 0.60, "d": 0.80, "e": 0.45,
    # 20-tenant contract-breach scenario — 1 MW ceiling per tenant (t01–t20).
    "t01": 1.0, "t02": 1.0, "t03": 1.0, "t04": 1.0, "t05": 1.0,
    "t06": 1.0, "t07": 1.0, "t08": 1.0, "t09": 1.0, "t10": 1.0,
    "t11": 1.0, "t12": 1.0, "t13": 1.0, "t14": 1.0, "t15": 1.0,
    "t16": 1.0, "t17": 1.0, "t18": 1.0, "t19": 1.0, "t20": 1.0,
}
_DEFAULT_TENANT_CONTRACTED_MW = 0.20   # fallback for custom / unlisted tenant IDs
_GPU_TDP_MW = 0.0007                   # H100 SXM5 TDP per GPU in MW

# Overage policy: tenants may draw up to _TENANT_BURST_ALLOWANCE × their contracted
# ceiling before the scenario is rejected.  Any draw above 100% of the ceiling up to
# this limit is billed at an additional _TENANT_OVERAGE_SURCHARGE_RATE per MWh (i.e.
# the overage portion costs 1 + _TENANT_OVERAGE_SURCHARGE_RATE times the normal rate).
_TENANT_BURST_ALLOWANCE       = 1.50  # max draw = 150 % of contracted MW
_TENANT_OVERAGE_SURCHARGE_RATE = 0.50  # extra 50 % per MWh on the overage portion


class TenantWorkloadEvent(BaseModel):
    """A scripted GPU burst job assigned to a specific colo tenant.

    Contributes tdp_mw = gpus × 0.0007 MW to p_compute_demand_mw during the
    window [t_start, t_start + duration_s).  Validated against
    TENANT_CONTRACTED_MW at save time — the scenario is rejected if a single
    event's TDP would exceed 150 % of the tenant's contracted power ceiling.
    Overage (draw above 100 % of ceiling) is billed at +50 % per MWh on top
    of the standard rate and is accumulated in SimulationState.tenant_overage_mwh
    during the run.
    """
    tenant_id: str = Field(
        description="Tenant ID ('a'–'e' for catalogued tenants, or a custom string)."
    )
    scheduler: Optional[str] = Field(
        default=None,
        description="Scheduler name for display ('Slurm', 'Kubernetes', 'Ray', or null).",
    )
    label: str = Field(
        default="",
        description="Human-readable job name (e.g. 'llm-finetune-70B burst').",
    )
    gpus: int = Field(ge=1, description="Number of H100 SXM5 GPUs allocated.")
    t_start: float = Field(ge=0.0, description="Simulation time at job start (seconds).")
    duration_s: float = Field(ge=1.0, description="Job duration (seconds).")

    @property
    def tdp_mw(self) -> float:
        return self.gpus * _GPU_TDP_MW


class ScenarioSpec(BaseModel):
    """Full scenario configuration.  Stored as spec_json in ScenarioRecord.
    Posted to POST /scenarios or PUT /scenarios/{id}.

    irradiance_steps convention — zero-order hold ("value applies from t
    onward"): [(0.0, 1.0), (30.0, 0.0)] gives 1.0 for t<30 and 0.0 for
    t≥30.  The last sample's value applies for all time beyond it.
    """
    name: str = Field(min_length=1)
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def _remove_internal_test_paths(cls, value: Any) -> Any:
        """Keep implementation-only paths out of every ScenarioSpec write."""
        value = sanitize_scenario_payload(value)
        # A block-addressable fleet is the Fuel Cell Module Array.  Its
        # presence is itself an enable declaration; materialize that fact when
        # older scenario JSON omitted the legacy boolean.  An explicitly false
        # value is deliberately retained so the run-start guard can reject the
        # contradictory stored specification with an actionable error instead
        # of silently operating an array that the author disabled.
        if (
            isinstance(value, dict)
            and value.get("fuel_cell_units")
            and "fuel_cell_enabled" not in value
        ):
            value = {**value, "fuel_cell_enabled": True}
        return value

    @staticmethod
    def _default_site_location():
        # Keep geographic literals centralized in site_config.py; scenario
        # defaults should not duplicate coordinates in the API schema.
        from site_config import get_default_site_location
        return get_default_site_location()

    # Per-scenario site identity.  When omitted, runs use the Santa Clara
    # defaults; explicit scenario values still override them.
    site_name: str = Field(
        default_factory=lambda: ScenarioSpec._default_site_location().site_name,
        min_length=1,
    )
    site_latitude: float = Field(
        default_factory=lambda: ScenarioSpec._default_site_location().latitude_deg,
        ge=-90.0,
        le=90.0,
    )
    site_longitude: float = Field(
        default_factory=lambda: ScenarioSpec._default_site_location().longitude_deg,
        ge=-180.0,
        le=180.0,
    )
    site_utc_offset_h: float = Field(
        default_factory=lambda: ScenarioSpec._default_site_location().longitude_deg / 15.0,
        ge=-14.0,
        le=14.0,
    )

    # Workload events ordered by timestamp.  Empty list = no scripted events
    # (idle run or run with pre-existing state from t<0, which is not yet
    # supported — see TC-33 compute scenario for the deferred-start pattern).
    workload_events: list[WorkloadEventSpec] = Field(default_factory=list)
    hardware_profile_id: str = "enterprise_8gpu_air"
    dt_lead_seconds: float = Field(
        default=30.0, ge=0.0, le=300.0,
        description=(
            "Advance warning time for GPU job starts (seconds).  "
            "SOLAR_STEP events always use dt_lead=0 regardless of this value (§7.1.1)."
        ),
    )

    bess_units: list[BessUnitSpec] = Field(min_length=0, default_factory=list)
    turbine_units: list[TurbineUnitSpec] = Field(min_length=0, default_factory=list)
    # Addendum G-1 block-addressable fleet.  When populated it supersedes the
    # legacy aggregate fuel_cell_* fields below; those fields remain wire
    # compatible for existing scenarios.
    fuel_cell_units: list[FuelCellUnitSpec] = Field(min_length=0, default_factory=list)
    diesel_power_block: Optional[DieselPowerBlockSpec] = None
    # Materialized from diesel_power_block during ScenarioSpec validation.
    # Callers should configure the block rather than hand-authoring this list.
    diesel_units: list[DieselUnitSpec] = Field(
        min_length=0,
        default_factory=list,
    )

    solar_rated_mw: float = Field(default=0.0, ge=0.0)

    # ── Fuel Cell Module Array ────────────────────────────────────────────────
    fuel_cell_enabled: bool = False
    fuel_cell_rated_mw: float = Field(
        default=0.0, ge=0.0,
        description=(
            "Nameplate MW rating of ONE fuel cell stack. "
            "The physics engine and EDL use fuel_cell_rated_mw × fuel_cell_stack_count "
            "as the fleet-total available capacity. "
            "Example: 5 MW/stack × 4 stacks = 20 MW fleet."
        ),
    )
    fuel_cell_stack_count: int = Field(default=1, ge=1)
    fuel_cell_initial_state: Optional[
        Literal["cold", "warming", "hot_standby", "running", "controlled_cooling"]
    ] = Field(
        default=None,
        description=(
            "Initial thermal state for the aggregate fuel-cell array. "
            "When omitted for an enabled scenario, defaults to running."
        ),
    )
    # Backward-compatible wire spelling for clients that call this simply
    # fuel_cell_state.  The factory gives fuel_cell_initial_state precedence.
    fuel_cell_state: Optional[
        Literal["cold", "warming", "hot_standby", "running", "controlled_cooling"]
    ] = Field(
        default=None,
        description="Alias for fuel_cell_initial_state.",
    )
    fuel_cell_baseload_target_mw: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "Fixed aggregate fuel-cell baseload target in MW when load-following "
            "is disabled. When omitted, defaults to the full fleet nameplate."
        ),
    )
    fuel_cell_load_following: bool = Field(
        default=False,
        description=(
            "When true, the running fuel-cell array follows live net site demand "
            "instead of holding the fixed baseload target."
        ),
    )
    fuel_cell_ramp_rate_mw_per_s: float = Field(
        default=0.02,
        gt=0.0,
        description="Aggregate fuel-cell output ramp rate in MW per simulated second.",
    )
    fuel_cell_ramp_down_rate_mw_per_s: Optional[float] = Field(
        default=None,
        gt=0.0,
        description=(
            "Aggregate fuel-cell ramp-down rate in MW per simulated second. "
            "When omitted, uses the ramp-up rate."
        ),
    )
    fuel_cell_min_stable_fraction: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum stable output as a fraction of aggregate nameplate.",
    )

    # ── Power Management (GS-IMPL-PSP-002) ──────────────────────────────────────
    # §23.4 Ladder A: site-level operating tier — controls the authority ladder.
    # "advisory": all actions require human approval; no autonomous dispatch.
    # "supervised": autonomous within pre-approved limits; deviations escalated.
    # "autonomous": full GridSignal autonomous dispatch; no per-action approval.
    operating_tier: Optional[str] = Field(
        default=None,
        pattern=r"^(advisory|supervised|autonomous)$",
    )
    # Calendar month (1–12) for TOU pricing in EconomicDispatchLoop.step().
    # None = caller falls back to current calendar month at runtime (§4.1).
    edl_calendar_month: Optional[int] = Field(default=None, ge=1, le=12)

    # Per-tenant power budget ceilings enforced by TenantBudgetGate (MT section).
    # Each dict: {"tenant_id": str, "ceiling_mw": float (> 0)}.
    tenant_budgets: Optional[list[dict]] = Field(default=None)
    # Operator response profile for PMSTestDouble replay (§3.4 / TC-C14 / INV-7).
    # Injected at run-start when GS_PRODUCTION_HARNESS env var is not set.
    operator_response_profile: Optional[dict] = Field(default=None)
    # PSP-002 §4.3 / Task #372: dispatch authority tier for the grid-firm source.
    # "autonomous" (default): grid is always dispatched; EDL shortfall never fires.
    # "confirm": operator/PMS must confirm; shortfall fires when BESS + turbine +
    #   FC cannot cover demand, triggering the §4.3 PMSTestDouble escalation.
    # "human_only": operator must command directly; always escalated on shortfall.
    grid_authority_tier: Optional[str] = Field(
        default="autonomous",
        pattern=r"^(autonomous|confirm|human_only)$",
    )

    # GS-DES-CFG-001 §Phase-6 / Item-3: declared design peak site load.
    design_peak_load_mw: Optional[float] = Field(
        default=None, ge=0.0,
        description=(
            "Declared design peak site load (MW). "
            "Definition: peak_it_load_mw (node_count × rated_kw × PUE_base / 1000) "
            "+ rated_cooling_mw (alpha_max × peak_it_load_mw × cooling_margin). "
            "Optional — old specs without this field load with a fallback derived at run start "
            "from workload_events and hardware_profile. Broadcast on TickPayload so fleet panels "
            "can use the declared figure for N−1 checks instead of the observed run maximum."
        ),
    )
    irradiance_steps: list[tuple[float, float]] = Field(
        default_factory=lambda: [(0.0, 1.0)],
        description="Zero-order-hold irradiance profile. Duplicate timestamps unnecessary.",
    )
    gpu_load_profile: list[tuple[float, float]] = Field(
        default_factory=list,
        description=(
            "Zero-order-hold GPU load profile. Each tuple is (sim_time_s, non-negative "
            "load multiplier), where 1.0 is nominal full load and values above 1.0 model "
            "a planned GPU over-peak. Empty = constant 1.0. The active multiplier scales "
            "p_compute_demand_mw each tick so operators can shape GPU utilisation over time."
        ),
    )

    # Phase 11.4 — Workload floor fraction.
    # Sets the minimum compute load as a fraction (0–1) of the scenario's declared
    # peak compute load (derived from workload_events node counts or kube_config.max_nodes).
    # When set, evaluate_tick() clamps compute_load_mw to at least
    #   workload_floor_fraction × peak_compute_mw
    # throughout the run, ensuring the Forecast Quality panel always has a visible
    # actual-vs-forecast gap rather than a near-zero flatline when no jobs are active.
    # None (default) = no floor enforced (backward-compatible with all existing scenarios).
    workload_floor_fraction: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum compute load as a fraction of peak (0.0–1.0). "
            "When set, p_compute_demand_mw never falls below "
            "workload_floor_fraction × peak_compute_mw. "
            "None = no floor (default, backward-compatible)."
        ),
    )

    island_mode: bool = True
    grid_import_limit_mw: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "Maximum real-power import at the point of common coupling (MW). "
            "None = unlimited grid balancing. Applies only when island_mode is false; "
            "exports are not capped."
        ),
    )
    bess_normal_dispatch_depth_fraction: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Fractional BESS depth of discharge permitted in normal operation, "
            "measured from each unit's configured initial SoC. Once used, the "
            "remaining BESS charge is held for an emergency that fuel-cell "
            "capacity plus available grid import cannot cover. 0 = historical "
            "BESS-first dispatch with no operating reserve."
        ),
    )
    bess_bridging_floor_fraction: float = Field(default=0.15, gt=0.0, le=1.0)
    bess_bridging_floor_anchor_multiple: float = Field(default=2.0, ge=1.0)
    bess_material_discharge_fraction: float = Field(default=0.05, gt=0.0, le=1.0)
    bess_material_discharge_min_mw: float = Field(default=1.0, ge=0.0)
    bess_catchup_sustain_s: float = Field(default=30.0, gt=0.0)
    bess_catchup_slope_window_s: float = Field(default=15.0, gt=0.0)
    bess_catchup_bridge_margin: float = Field(default=0.8, gt=0.0, le=1.0)
    # A1 / Task #200: site nominal grid frequency.
    # San Diego (SDG&E territory) = 60 Hz; EU/APAC grids = 50 Hz.
    # Default 60.0 — primary deployment site is WECC.  Override explicitly for
    # non-WECC scenarios.  Carried through scenario_factory → SiteConfig;
    # SiteConfig has no default so omitting this from the spec fails at startup.
    frequency_nominal_hz: float = Field(
        default=60.0,
        ge=45.0, le=65.0,
        description=(
            "Nominal grid frequency for the site (Hz).  "
            "60 Hz for WECC/ERCOT (North America); 50 Hz for EU/APAC. "
            "Drives the swing-equation denominator and all frequency-response criteria."
        ),
    )

    # ── §FP: Frequency-protection thresholds (Optional — None = threshold disabled) ──
    # IEEE 1547-2018 Cat I defaults for a 60 Hz WECC site.  All five are Optional so
    # legacy specs (no protection fields) continue to load without modification.
    # The factory (scenario_factory.py) already passes these through to SiteConfig;
    # adding them here makes them part of the validated schema so Pydantic rejects
    # out-of-range values before a run starts.
    #
    # Field order mirrors the frequency axis (low → high):
    #   island_collapse_hz < ufls_stage1_hz < uf_warning_hz  < f_nominal
    #                       < of_warning_hz  < of_trip_hz
    uf_warning_hz: Optional[float] = Field(
        default=None, ge=45.0, le=65.0,
        description=(
            "Under-frequency advisory threshold (Hz).  Below this frequency the "
            "advisory system alerts but the island does not collapse.  "
            "IEEE 1547-2018 Cat I / SDG&E default: 59.5 Hz.  "
            "None = threshold disabled (legacy scenario compatibility)."
        ),
    )
    ufls_stage1_hz: Optional[float] = Field(
        default=None, ge=45.0, le=65.0,
        description=(
            "Stage-1 under-frequency load-shedding threshold (Hz).  "
            "Below this frequency automatic load shedding begins.  "
            "IEEE 1547-2018 Cat I / SDG&E default: 58.5 Hz.  "
            "None = UFLS stage 1 disabled."
        ),
    )
    island_collapse_hz: Optional[float] = Field(
        default=None, ge=45.0, le=65.0,
        description=(
            "Island collapse (mandatory under-frequency trip) threshold (Hz).  "
            "Below this frequency the island de-energises.  "
            "IEEE 1547-2018 Cat I / SDG&E default: 57.0 Hz.  "
            "None = UF collapse disabled."
        ),
    )
    of_warning_hz: Optional[float] = Field(
        default=None, ge=45.0, le=65.0,
        description=(
            "Over-frequency advisory threshold (Hz).  Above this frequency the "
            "§INV-CURT inverter curtailment ramp begins.  "
            "IEEE 1547-2018 Cat I / SDG&E default: 60.5 Hz.  "
            "None = OF advisory and inverter curtailment disabled."
        ),
    )
    of_trip_hz: Optional[float] = Field(
        default=None, ge=45.0, le=65.0,
        description=(
            "Over-frequency trip threshold (Hz).  Above this frequency the island "
            "collapses via OF protection; inverter curtailment saturates at 100 % here.  "
            "IEEE 1547-2018 Cat I / SDG&E default: 62.0 Hz.  "
            "None = OF trip disabled."
        ),
    )

    # ── Phase 5: UFLS and 81U relay (opt-in — disabled by default) ───────────
    # PROVISIONAL-UNMEASURED thresholds. Must be explicitly set per-scenario.
    # Empty list / None = protection stage disabled (backward-compatible default).
    ufls_stages: Optional[list[dict]] = Field(
        default=None,
        description=(
            "Under-frequency load-shedding relay stages.  Each entry: "
            "{'threshold_hz': float, 'delay_s': float, 'block_fraction': float}. "
            "PROVISIONAL-UNMEASURED. None = UFLS disabled (default)."
        ),
    )
    relay_81u_threshold_hz: Optional[float] = Field(
        default=None, ge=45.0, le=65.0,
        description=(
            "Islanded 81U under-frequency relay trip threshold (Hz). "
            "PROVISIONAL-UNMEASURED. None = 81U relay disabled (default). "
            "57.5 Hz is the PROVISIONAL value for 60 Hz (WECC) systems."
        ),
    )
    relay_81u_delay_s: Optional[float] = Field(
        default=None, ge=0.0, le=10.0,
        description=(
            "81U relay time delay before trip (s). "
            "PROVISIONAL-UNMEASURED. None = use catalogue default (0.10 s)."
        ),
    )

    power_factor: float = Field(
        default=0.85,
        gt=0.0, le=1.0,
        description=(
            "Rated power factor of the synchronous generator fleet (dimensionless).  "
            "Converts rated_mw to MVA base: S_base = Σ rated_mw / power_factor.  "
            "Typical gas turbine: 0.85 (CHOSEN — calibrate against nameplate or vendor data).  "
            "Raising pf toward 1.0 lowers S_base and increases df/dt; lowering it slows frequency response."
        ),
    )
    pue_base: float = Field(default=1.03, ge=1.0, le=2.0)
    end_sim_time: float = Field(default=300.0, ge=60.0, le=86400.0)
    # Operator-facing "What this demonstrates" copy shown in the DemoBar.
    # Plain prose, 1-3 sentences.  Empty string = fall back to the hardcoded default.
    demo_description: str = ""

    # Default playback speed stored with the scenario so operators don't have to
    # re-select it every run.  0 = max-speed sentinel; >0 = simulated-s per real-s.
    # Honoured by the "Run" button in the Scenarios modal and the DemoBar auto-fill.
    default_playback_speed: float = Field(
        default=1.0,
        ge=0.0,
        description=(
            "Default simulation playback speed for this scenario.  "
            "0 = run as fast as possible; >0 = simulated-seconds per real-second.  "
            "Stored in the spec so the operator's choice persists across sessions."
        ),
    )

    # ── Physics parameters (gridsignal_parameters.json §2) ─────────────────
    # Generated from gridsignal_parameters.json at runtime; never hand-coded.
    # Split parameters (split=true in JSON) have optional plant_ variants.
    # When plant_* is None the simulation uses the engine value (linked default).
    #
    # §2.1 / §2.2 — Thermal response (PARAM-02/03/04)
    dt_thermal_seconds: float = Field(
        default=90.0, ge=0.0, le=300.0,
        description=(
            "Engine value: thermal-delay before cooling ramp (Δt_thermal, s). "
            "Source: §8–9, SPEC_DEFAULT."
        ),
    )
    plant_dt_thermal_seconds: Optional[float] = Field(
        default=None, ge=0.0, le=300.0,
        description=(
            "Plant value for Δt_thermal. None = linked to dt_thermal_seconds. "
            "Set explicitly to simulate a plant/engine thermal-model divergence."
        ),
    )
    alpha_max: float = Field(
        default=0.20, ge=0.0, le=1.0,
        description=(
            "Engine value: maximum cooling fraction (α_max). "
            "Source: §8, SPEC_DEFAULT."
        ),
    )
    plant_alpha_max: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Plant value for α_max. None = linked to alpha_max.",
    )
    tau_seconds: float = Field(
        default=20.0, ge=1.0, le=120.0,
        description=(
            "Engine value: cooling time-constant (τ, s). "
            "Source: §8, PROPOSED_HERE."
        ),
    )
    plant_tau_seconds: Optional[float] = Field(
        default=None, ge=1.0, le=120.0,
        description="Plant value for τ. None = linked to tau_seconds.",
    )

    # §2.5 — Reserve-check parameters (PARAM-09/13/14/15)
    # anchor_reserve_pct: % of each grid-forming BESS's rated MW withheld as
    #   anchor reserve.  0.0 = use BessConfig.p_anchor_reserve_mw default (1.0 MW).
    #   PROPOSED_HERE — 8% is the placeholder; calibrate against commissioning specs.
    anchor_reserve_pct: float = Field(
        default=0.0, ge=0.0, le=20.0,
        description=(
            "Anchor reserve as % of BESS rated MW (grid-forming unit only). "
            "0 = use BessConfig default (1.0 MW). PROPOSED_HERE — pending commissioning."
        ),
    )
    # Confidence band (§2.5, INV-2) — PROPOSED_HERE decisions:
    #   band_pct_calibrated = 4%  →  uncalibrated = 4% × 2.0 = 8% = fixture
    #   band_mult_uncalibrated = 2.0×
    #   band_mult_unmapped_hw  = 1.5×
    # Default band_enabled=False preserves backward-compat for all seeded
    # scenarios (which pre-date this parameter and should behave as before).
    # scenario_factory infers band_enabled=True when band_pct_calibrated > 0.
    band_enabled: bool = Field(
        default=False,
        description=(
            "Enable the confidence band for INV-2 reserve check. "
            "False = point-estimate check only (backward-compat default). "
            "scenario_factory sets True automatically when band_pct_calibrated > 0."
        ),
    )
    band_pct_calibrated: float = Field(
        default=0.0, ge=0.0, le=15.0,
        description=(
            "Confidence band ±% of peak_shortfall for reserve check (INV-2). "
            "0 = disabled (point-estimate check only, backward-compat). "
            "PROPOSED_HERE default: 4.0%. "
            "Effective band = band_pct × mult_uncalib × mult_unmapped_hw."
        ),
    )
    band_mult_uncalibrated: float = Field(
        default=2.0, ge=1.0, le=4.0,
        description=(
            "Reserve-band multiplier for uncalibrated sites (§17.3). "
            "PROPOSED_HERE decision: 2.0× (calibrated × 2.0 = fixture 8%)."
        ),
    )
    band_mult_unmapped_hw: float = Field(
        default=1.5, ge=1.0, le=4.0,
        description=(
            "Reserve-band multiplier for unmapped hardware profiles (§5.1). "
            "PROPOSED_HERE decision: 1.5× (independent of uncalibrated mult)."
        ),
    )

    # Step 10: optional §8.1 pre-staging configuration.
    # None = PreStagingEngine not instantiated (SiteConfig.pre_staging_config = None).
    pre_staging_config: Optional[PreStagingConfigSpec] = None

    # Step 11: optional §28.4 PMS configuration.
    # None = SimulatedPMS not instantiated (SiteConfig.pms_config = None).
    # fast_shed and open_transition are injected at runtime via
    # SimulatedPMS.inject_fast_shed() / inject_transition(); the scenario only
    # gates whether the PMS code path is active.
    pms_config: Optional[PmsConfigSpec] = None

    # AD1: optional §24 procurement configuration.
    # None = ProcurementLayer not instantiated.
    # When set, NonFirmImportEffect.apply() (TC-47) and ReservationProposal
    # (TC-52) are exercised each tick during the live run.
    procurement_config: Optional[ProcurementConfigSpec] = None

    # AD1: optional §27 maintenance configuration.
    # None = MaintenanceLayer not instantiated.
    # When set, reserve_contribution_mw_per_s (TC-58), validate_window (TC-59),
    # and propose_rating_change (TC-60) are exercised during the live run.
    maintenance_config: Optional[MaintenanceConfigSpec] = None

    # AD1: optional §23.7.2 ramp relaxation configuration.
    # None = RampRelaxationEngine not instantiated.
    # When set, evaluate() is called each tick (TC-75 upper-bound reserve check;
    # TC-76 gridSignal_connected=False revert is covered by unit test).
    ramp_relaxation_config: Optional[RampRelaxationConfigSpec] = None

    # Kubernetes demand agent — autonomous stochastic GPU cluster demand.
    # None = standard scripted workload path (default; existing tests unaffected).
    # When set, the agent emits STARTING then SCALE signals each tick, driven by
    # an OU process + EMA.  Power-cap fires when grid headroom < headroom_threshold_mw.
    kube_config: Optional[KubeConfigSpec] = None
    # Heterogeneous multi-cluster path.  Each entry receives an independent
    # capacity ceiling and RNG stream.  Mutually exclusive with kube_config.
    kube_clusters: list[KubeClusterSpec] = Field(default_factory=list)

    # ── Within-step compute load profile (scripted-event / non-kube path) ────
    # Activates compute-phase vs allreduce-phase power variation for scenarios
    # that use workload_events rather than kube_config.  The step phase is
    # self-managed by GPUModule.advance() using a fixed 0.70 s step period
    # (StepTimingConfig.median_step_s default) so tick-to-tick p_compute_mw
    # varies realistically between ~100% TDP (compute) and ~55% TDP (allreduce).
    #
    # Ignored when kube_config is set — kube_config.load_config takes priority.
    # None (default) = flat profile, preserving all existing test behaviour.
    load_config: Optional[LoadProfileConfigSpec] = None

    # ── Pre-run generation architecture ────────────────────────────────────────
    # All generators run concurrently BEFORE t=0, materialising timelines that
    # the tick loop replays deterministically.  No generator runs during ticks.

    # Correlated ambient weather: when solar_rated_mw > 0 and irradiance_steps
    # is the bare default, generate_solar_forecast() already emits ambient_steps.
    # This field carries those steps (injected by runs.py, not user-settable).
    ambient_steps: list[tuple[float, float, float]] = Field(
        default_factory=list,
        description="Pre-generated (sim_time_s, drybulb_c, wetbulb_c) timeline. "
                    "Populated automatically by generate_solar_forecast(); not user-settable.",
    )

    # LLM cluster arrival generator — replaces (or supplements) scripted workload events
    # with a Mistral-generated bursty, correlated cluster traffic timeline.
    # None = use existing workload_events and/or kube_config as-is.
    cluster_gen_config: Optional[ClusterGenConfigSpec] = None

    # LLM fault/stressor timeline generator — adds compound fault scenarios
    # (cloud fronts, inverter trips) as SOLAR_STEP events.
    # None = no stressor injection.
    stressor_gen_config: Optional[StressorGenConfigSpec] = None

    # Per-run seeded RNG parameter sampling — draws physics params from their
    # documented ranges once, producing a distinct sensitivity point per run.
    # None = no parameter sampling.
    param_sampling_config: Optional[ParamSamplingConfigSpec] = None

    # Pre-generated telemetry corruption schedule — stresses §17.2 quarantine.
    # None = clean telemetry (default; existing tests unaffected).
    telemetry_corruption_config: Optional[TelemetryCorruptionConfigSpec] = None

    # Generation block — populated by runs.py after all generators complete.
    # Distinguishes a scenario definition from a materialised spec and makes
    # any failing run replayable.
    generation_block: Optional[GenerationBlock] = None

    # AD2: site calibration flag.
    # False (default) = SiteConfig.uncalibrated=True (§17.3 default: uncalibrated
    # until explicit calibration run).  The TC-43 low-confidence interlock
    # resets the curtailment dwell every tick while uncalibrated is True, so
    # curtailment proposals never fire in the default state.
    # True = SiteConfig.uncalibrated=False — site is treated as calibrated,
    # curtailment ladder fires normally once the dwell elapses.
    # Only set True for scenarios where the curtailment path must engage
    # (e.g. demo-pms-shortfall for TC-65 conflict detection).
    calibrated: bool = False

    # Scripted DQ tag injection windows — each entry fires the named tag for
    # every tick in [start_s, end_s).  Produces ATTENTION state on the Forecast
    # Quality tile, widens the confidence band, and blocks autonomous curtailment
    # (TC-43 interlock) exactly as a real DQ tag would.  Use in demo scenarios
    # so operators can see the tile trip to ATTENTION mid-run.
    dq_inject_events: list[DqInjectEvent] = Field(default_factory=list)

    # Solar origin UTC hour override — demo-solar-peak uses this to anchor
    # generate_solar_forecast() at a fixed midday UTC time (UTC 20 = 12:00 PST)
    # regardless of when the demo is actually run.  None = use real UTC now.
    # Valid range [0, 23]; runs.py converts to a datetime before calling
    # generate_solar_forecast() so the Mistral prompt and physics curve both
    # see the anchored local SV1 (Santa Clara / Silicon Valley) time.
    solar_origin_utc_hour: Optional[int] = Field(
        default=None, ge=0, le=23,
        description=(
            "Fix the UTC hour passed to generate_solar_forecast(). "
            "Use 20 for UTC 20:00 = 12:00 PST SV1 solar noon (America/Los_Angeles). "
            "None = real wall-clock UTC (default for all other scenarios)."
        ),
    )

    # ── Approach 1: Scripted tenant workload events ───────────────────────────
    # Each event adds its GPU TDP to p_compute_demand_mw during its active window.
    # Validated against TENANT_CONTRACTED_MW ceilings (× _TENANT_BURST_ALLOWANCE)
    # at save time — see _check_tenant_ceilings.
    tenant_events: list[TenantWorkloadEvent] = Field(
        default_factory=list,
        description=(
            "Scripted GPU burst jobs per colo tenant. Each event contributes "
            "gpus × 0.0007 MW to p_compute_demand_mw during [t_start, t_start+duration_s). "
            "Rejected at save if any event's draw exceeds 150% of the tenant's "
            "contracted power ceiling (draw between 100% and 150% is allowed and "
            "billed at a surcharge)."
        ),
    )

    # ── Approach 2: GPU Generator preset auto-armed at run start ─────────────
    # Frontend reads this at run start and auto-arms the GPU Generator store.
    # Opaque JSON — shape matches GeneratorConfig in gpuGeneratorStore.ts.
    # null / absent = no auto-start; operator must arm the generator manually.
    generator_config: Optional[dict] = Field(
        default=None,
        description=(
            "GPU Generator config auto-armed when the run starts. "
            "Keys match GeneratorConfig in frontend/src/store/gpuGeneratorStore.ts. "
            "null = no auto-start."
        ),
    )

    # Step 9: optional pass/fail assertions evaluated at run completion.
    # Each element is one of the AssertionSpec union members (discriminated
    # on 'check').  Empty list → verdict is INCONCLUSIVE.
    assertions: list[AssertionSpec] = Field(default_factory=list)

    # Phase 10: fabric regression scenario reference.
    # When set, the FabricEngine loads the named regression-test scenario JSON from
    # config/scenarios/, using its jobs/stressors/capability_tier, and
    # evaluates the scenario's fabric-specific assertions at run completion.
    # The value is the scenario_id field from the JSON file
    # (e.g. "regression-test-checkpoint-storage-hotspot").
    fabric_scenario_id: Optional[str] = Field(
        default=None,
        description=(
            "ID of a fabric regression scenario JSON file to drive the FabricEngine. "
            "Set to one of the regression-test-* scenario IDs."
        ),
    )

    # Cascade commit fraction — per-unit output threshold that triggers the next
    # standby-turbine start.  When set, the commitment engine issues command_start()
    # on the next offline unit as soon as the LAST on-bus active (non-hot-standby)
    # turbine's output reaches (cascade_commit_fraction × its rated MW).
    # None (default) = use fleet-utilisation threshold (commit_utilisation) instead.
    cascade_commit_fraction: Optional[float] = Field(
        default=None,
        ge=0.0, le=1.0,
        description=(
            "Per-unit output fraction of the last on-bus turbine that triggers "
            "the next standby-turbine start.  0.5 = commit next unit when lead "
            "turbine reaches 50% of its rated MW.  None = fleet-utilisation trigger."
        ),
    )
    fuel_cell_turbine_commit_fraction: Optional[float] = Field(
        default=None,
        gt=0.0,
        le=1.0,
        description=(
            "Deprecated compatibility field.  The former fuel-cell output "
            "threshold commit policy is removed; this value is accepted for "
            "legacy scenario JSON but has no runtime effect."
        ),
    )

    # UI hint: operator BESS config widget seeds these values when this scenario
    # is selected, overriding the global default (30 MW / 30 MWh Freq. Anchor).
    # Null / absent = fall back to the global UI default.  Does not affect
    # physics — only the initial operator-facing override shown in the widget.
    ui_bess_rated_mw:  Optional[float] = Field(default=None, ge=0.0)
    ui_bess_usable_mwh: Optional[float] = Field(default=None, ge=0.0)

    # ── §21.2 cost model overrides (DIAG-1 / DIAG-2) ─────────────────────────
    # Both default to None ("not set by operator") so the cost engine can
    # distinguish an explicit $0.0 from "use the system fallback".  Use
    # `is not None` checks everywhere — never `or`-based fallback — because
    # $0.0 is a valid and meaningful override (fully self-generated site).
    #
    # grid_import_price_per_mwh: billing price for grid energy, in $/MWh.
    #   None → cost engine falls back to _COST_CFG_DEFAULTS ($120/MWh, a
    #   CAISO-style wholesale/direct-access spot price — see DIAG-4).
    #   Sites on C&I utility tariffs (e.g. PG&E B-20 all-in: ~$150–350/MWh)
    #   should supply the relevant energy-charge line item here.
    #   This is the PATH A billing price; it is SEPARATE from the
    #   SyntheticPriceCurve.BASE_MARKET_PRICE_PER_MWH ($55) market signal
    #   used by the advisory procurement layer.
    grid_import_price_per_mwh: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "Grid import energy price for §21.2 cost accounting ($/MWh). "
            "None = use system default ($120/MWh wholesale spot fallback). "
            "Set to the all-in energy-charge line item for C&I utility tariffs."
        ),
    )
    # bess_charge_price_override_per_mwh: explicit per-MWh cost for energy
    #   delivered INTO the BESS (gross charge).  None → cost engine derives
    #   this from the effective grid_import_price_per_mwh (DIAG-2 fix: BESS
    #   charging is billed at the same rate as the import it consumes, not a
    #   flat $60).  Set only if the site has a separate contracted off-peak
    #   charging tariff that differs from the general import price.
    bess_charge_price_override_per_mwh: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "Override BESS charge price ($/MWh). "
            "None = derive from effective grid_import_price_per_mwh. "
            "Set only for sites with a separate contracted charging tariff."
        ),
    )

    @model_validator(mode="after")
    def _validate_kube_clusters(self) -> "ScenarioSpec":
        """Keep legacy and multi-cluster scheduler configuration unambiguous."""
        if self.kube_config is not None and self.kube_clusters:
            raise ValueError(
                "kube_config and kube_clusters are mutually exclusive"
            )
        if not self.kube_clusters:
            return self

        cluster_ids = [cluster.cluster_id for cluster in self.kube_clusters]
        if len(cluster_ids) != len(set(cluster_ids)):
            raise ValueError("kube_clusters cluster_id values must be unique")

        workload_share = sum(
            cluster.workload_share for cluster in self.kube_clusters
        )
        if abs(workload_share - 1.0) > 1e-6:
            raise ValueError(
                "kube_clusters workload_share values must sum to 1.0 "
                f"(got {workload_share:.6f})"
            )
        return self

    @model_validator(mode="after")
    def _check_tenant_ceilings(self) -> "ScenarioSpec":
        """Reject any tenant event whose GPU TDP exceeds 150 % of the contracted ceiling.

        Tenants are permitted to burst up to _TENANT_BURST_ALLOWANCE (1.5×) of their
        contracted MW.  Draw above 100 % but below 150 % is allowed and billed at a
        +50 % surcharge per MWh by the runtime engine.  A single event above 150 %
        is rejected here — author the event as two overlapping events if a blended
        draw exceeding the per-event burst limit is required by the scenario.
        """
        for ev in self.tenant_events:
            ceiling = TENANT_CONTRACTED_MW.get(ev.tenant_id.lower(), _DEFAULT_TENANT_CONTRACTED_MW)
            hard_cap = ceiling * _TENANT_BURST_ALLOWANCE
            if ev.tdp_mw > hard_cap + 1e-6:
                max_gpus = int(hard_cap / _GPU_TDP_MW)
                raise ValueError(
                    f"Tenant {ev.tenant_id!r} event '{ev.label or ev.tenant_id}': "
                    f"{ev.gpus} GPUs = {ev.tdp_mw:.3f} MW exceeds the 150 % burst cap "
                    f"({hard_cap:.2f} MW, ceiling {ceiling:.2f} MW × 1.5). "
                    f"Reduce to ≤ {max_gpus} GPUs."
                )
        return self

    @model_validator(mode="after")
    def _single_grid_forming_anchor(self) -> "ScenarioSpec":
        """§7.1.2: only one BESS unit may be the grid-forming anchor."""
        forming = [u for u in self.bess_units if u.grid_forming]
        if len(forming) > 1:
            ids = [u.asset_id for u in forming]
            raise ValueError(
                f"§7.1.2: at most one BESS unit may have grid_forming=True "
                f"(found {len(forming)}: {ids}). "
                f"Only the designated island-frequency anchor holds the anchor reserve."
            )
        return self

    @model_validator(mode="after")
    def _materialize_diesel_fleet(self) -> "ScenarioSpec":
        """Expand an enabled diesel block into its deterministic unit list."""
        self.diesel_units = (
            generate_diesel_fleet(self.diesel_power_block)
            if self.diesel_power_block is not None
            else []
        )
        return self

    @model_validator(mode="after")
    def _gpu_load_profile_within_duration(self) -> "ScenarioSpec":
        """Reject any GPU load point whose timestamp exceeds the run duration.

        gpu_load_profile is a zero-order-hold step function keyed by sim_time_s.
        A point at t > end_sim_time is never reached during the run, so it is
        either a data entry mistake or a stale point left over after the operator
        shortened the run.  Either way it should be rejected at save time rather
        than silently ignored during replay.
        """
        bad = [
            t for t, _frac in self.gpu_load_profile
            if t > self.end_sim_time
        ]
        if bad:
            bad_str = ", ".join(f"{t:.1f}s" for t in bad)
            raise ValueError(
                f"gpu_load_profile contains {len(bad)} point(s) beyond the run "
                f"duration ({self.end_sim_time:.0f}s): {bad_str}. "
                f"Remove or adjust these points so every timestamp is ≤ end_sim_time."
            )
        return self

    def collect_c_rate_warnings(self) -> list[str]:
        """Return all non-None C-rate warnings across the BESS fleet."""
        return [w for u in self.bess_units if (w := u.c_rate_warning()) is not None]


# ---------------------------------------------------------------------------
# Generation architecture — pre-run generators (materialized before t=0)
# ---------------------------------------------------------------------------

class GenerationBlock(BaseModel):
    """Metadata record for all pre-run generators that ran for a scenario.

    Stored on RunContext and emitted in run metadata so that a scenario
    definition and a materialised spec are distinguishable artifacts.
    A run ID + generation_block is sufficient to replay any run exactly:
    - physics/RNG paths replay from seed alone.
    - LLM paths replay by re-running the generators (Mistral may vary) or by
      reading the stored event lists from the scenario spec.

    Fields
    ------
    seed              : master RNG seed for this run (None = time-seeded).
    generated_at      : ISO-8601 UTC timestamp when generation ran.
    generators_used   : list of generator names that actually ran.
    solar_source      : "mistral" | "physics" | "none".
    cluster_source    : "mistral" | "rng" | "none".
    stressor_source   : "mistral" | "rng" | "none".
    param_sampler_note: human-readable summary from param_sampler.
    corruption_note   : human-readable summary from telemetry_corruption.
    """
    seed:               Optional[int]   = None
    generated_at:       str             = ""
    generators_used:    list[str]       = Field(default_factory=list)
    solar_source:       str             = "none"
    cluster_source:     str             = "none"
    stressor_source:    str             = "none"
    param_sampler_note: str             = ""
    corruption_note:    str             = ""


class ClusterGenConfigSpec(BaseModel):
    """Configuration for the LLM-driven cluster arrival process generator.

    When present on a ScenarioSpec, the generator is called ONCE at run start
    (before the tick loop).  The resulting STARTING/JOB_END/SCALE events are
    merged into spec_data["workload_events"] before the RunContext is built.

    use_llm=True (default) calls Mistral for temporal structure — bursts,
    business-hours patterns — that a Poisson process cannot reproduce.
    Falls back to seeded RNG when MISTRAL_API_KEY is absent or the call fails.

    use_llm=False forces the seeded RNG path.  Prefer this when the arrival
    statistics are fully specified by the other fields (the Poisson case).
    """
    description:        str   = "plausible weekday on a 1900-node ML cluster"
    hardware_profile_id: str  = "enterprise_8gpu_air"
    max_nodes:          int   = Field(default=1900, ge=1)
    min_nodes:          int   = Field(default=200,  ge=1)
    mean_interarrival_s: float = Field(default=60.0, ge=5.0, le=3600.0)
    mean_job_nodes:     int   = Field(default=200, ge=1)
    job_node_std:       float = Field(default=80.0, ge=0.0)
    min_job_nodes:      int   = Field(default=50, ge=1)
    mean_job_duration_s: float = Field(default=300.0, ge=10.0)
    min_job_duration_s: float = Field(default=30.0,  ge=5.0)
    rng_seed:           Optional[int] = None
    use_llm:            bool  = True


class StressorGenConfigSpec(BaseModel):
    """Configuration for the LLM-driven fault and stressor timeline generator.

    When present on a ScenarioSpec, the generator is called ONCE at run start
    and its output (SOLAR_STEP events) is merged into spec_data["workload_events"].

    The LLM composes plausible compound fault sequences: cloud front arrives,
    inverter trips 90 seconds later, partial recovery — the correlated-failure
    case that a hand-written scenario library under-represents.

    use_llm=False forces the seeded RNG fallback (random cloud fronts).
    """
    description:    str   = "compound cloud-front and inverter-trip scenario"
    n_rng_events:   int   = Field(default=3, ge=1, le=20)
    rng_seed:       Optional[int] = None
    use_llm:        bool  = True


class ParamSamplingConfigSpec(BaseModel):
    """Configuration for per-run seeded RNG parameter sampling (§6.1 sensitivity).

    When present, draws the listed physics parameters from their documented
    [min, max] ranges once at run start and merges them into spec_data.

    The seeded RNG path is always used — there is no LLM call here.  Seeded RNG
    is the correct tool: the sampling distribution is fully specified by the
    parameter ranges and there is no temporal structure an LLM adds value to.

    keys  — parameter keys as in gridsignal_parameters.json (e.g. "alpha_max").
            Keys not in the adjustable list or in the _NEVER_SAMPLE exclusion set
            are silently skipped.
    seed  — RNG seed; None = time-seeded (non-reproducible).
    sample_plant_split — if True, split parameters draw independent plant and
            engine values, producing natural plant/engine divergence.
    """
    keys:               list[str] = Field(
        default_factory=lambda: ["dt_thermal", "alpha_max", "tau"],
        description="Parameter keys to sample from gridsignal_parameters.json",
    )
    seed:               Optional[int] = None
    sample_plant_split: bool = True


class TelemetryCorruptionConfigSpec(BaseModel):
    """Configuration for the pre-generated telemetry corruption schedule.

    When present, a per-tick corruption manifest is generated ONCE at run start
    from a seeded RNG.  The manifest specifies which ticks receive Gaussian noise,
    dropout (record suppressed), or staleness (old reading substituted).

    This exercises the §17.2 quarantine path, NTP-skew handling, and out-of-order
    delivery logic.  All values default to 0.0 / 0 (no corruption) so that adding
    the block without setting values is a safe no-op.
    """
    noise_sigma:  float = Field(
        default=0.0, ge=0.0, le=0.5,
        description="1-sigma of multiplicative Gaussian noise on readings (e.g. 0.05 = ±5%)",
    )
    dropout_prob: float = Field(
        default=0.0, ge=0.0, lt=1.0,
        description="Per-tick probability of record suppression (packet loss)",
    )
    max_stale:    int   = Field(
        default=0, ge=0, le=30,
        description="Maximum staleness in ticks (0 = no staleness injection)",
    )
    seed:         Optional[int] = None


class ScenarioSummary(BaseModel):
    """Lightweight row returned by GET /scenarios (list)."""
    scenario_id: str
    name: str
    description: str
    created_at: str   # ISO-8601 UTC


class ScenarioDetailResponse(BaseModel):
    """Full detail returned by GET /scenarios/{id}."""
    scenario_id: str
    name: str
    description: str
    created_at: str
    spec: ScenarioSpec
    c_rate_warnings: list[str]


class CreateScenarioResponse(BaseModel):
    """Returned by POST /scenarios and PUT /scenarios/{id}."""
    scenario_id: str
    name: str
    c_rate_warnings: list[str]


# ---------------------------------------------------------------------------
# Run lifecycle schemas
# ---------------------------------------------------------------------------

class StartRunRequest(BaseModel):
    """Start a new simulation run.

    Two accepted paths:
      (a) scenario_id  — reference a stored ScenarioSpec; fleet and workload
          parameters come from the stored spec.
      (b) job_id + node_count  — direct programmatic path; used by tests and
          load-test scripts.

    Step 8 removes the F1 scenario_preset scaffolding.  Callers that used
    scenario_preset must switch to scenario_id (POST /scenarios first to
    obtain one).
    """
    scenario_id: Optional[str] = Field(
        default=None,
        description="Stored scenario ID from GET /scenarios. "
                    "When set, all fleet/workload parameters come from the spec.",
    )
    job_id: Optional[str] = Field(
        default=None,
        description="Job identifier; required when scenario_id is not set.",
    )
    node_count: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of GPU nodes; required when scenario_id is not set.",
    )
    hardware_profile_id: str = "enterprise_8gpu_air"
    end_sim_time: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Simulated seconds to run.  None (default) means use the scenario's own "
            "end_sim_time.  Pass 1e15 for an effectively unlimited run."
        ),
    )
    playback_speed: float = Field(
        default=0.0,
        ge=0,
        description="Simulated seconds per real second (0 = max speed)",
    )

    # ── Operator BESS size overrides ──────────────────────────────────────────
    # When present these replace rated_mw / usable_mwh on every BESS unit in the
    # stored scenario spec before the run is built.  Intended for the RunControlBar
    # "BESS" fields; only accepted while no run is active (enforced in the UI).
    # None (default) = use the scenario's stored BESS values unchanged.
    bess_rated_mw_override: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Override rated power (MW) for all BESS units in the scenario. "
            "None = use the scenario's stored value."
        ),
    )
    bess_usable_mwh_override: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Override usable energy capacity (MWh) for all BESS units in the scenario. "
            "None = use the scenario's stored value."
        ),
    )

    # ── GPU Generator wiring ───────────────────────────────────────────────────
    # When the frontend GPU Generator is active the operator can connect it to the
    # backend kube scheduler by sending their GeneratorConfig here.  The run-start
    # handler translates it into a kube_config override so that stochastic Slurm /
    # K8s / Ray job arrivals drive real compute MW in the physics engine.
    # None (default) = use the scenario's own kube_config unchanged (or no kube
    # scheduler if the scenario has no kube_config).
    generator_config_override: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Frontend GeneratorConfig to wire into the backend kube scheduler. "
            "Translated to kube_config before the run context is built."
        ),
    )

    @model_validator(mode="after")
    def _require_scenario_or_job_fields(self) -> "StartRunRequest":
        """scenario_id OR (job_id + node_count) must be present."""
        if self.scenario_id is None:
            missing = [
                name
                for name, val in [("job_id", self.job_id), ("node_count", self.node_count)]
                if val is None
            ]
            if missing:
                raise ValueError(
                    f"Fields {missing} are required when scenario_id is not provided."
                )
        return self


class StartRunResponse(BaseModel):
    run_id: str
    soc_floor_pct: float = 10.0   # operator-set BESS lower display bound
    soc_ceil_pct: float  = 95.0   # operator-set BESS upper display bound


class RunStatusResponse(BaseModel):
    run_id: str
    active: bool
    paused: bool = False


class RunListResponse(BaseModel):
    run_ids: list[str]


# ---------------------------------------------------------------------------
# Step 9: Results / playback response schemas
# ---------------------------------------------------------------------------

class AssertionResultResponse(BaseModel):
    """One assertion's evaluation outcome, as returned by GET /runs/{id}/result."""
    check: str
    status: str   # "PASS" | "FAIL" | "INCONCLUSIVE"
    detail: str


class BalanceGateResponse(BaseModel):
    """Phase 0 power balance gate verdict (DR-2026-08-09-BALANCE).

    Present when the gate was evaluated (balance_defect_tolerance_mw is set in the
    catalogue). When renderable is False the run's derived figures — reserve margin,
    N-1 firm capacity, served load — rest on terms that did not reconcile and should
    not be presented as if they did. The reason string carries the detail.
    """
    renderable: bool
    reason: Optional[str] = None
    worst_defect_mw: float
    worst_tick_index: Optional[int] = None
    n_violating: int


class RunResultResponse(BaseModel):
    """Full verdict returned by GET /runs/{run_id}/result."""
    run_id: str
    scenario_id: Optional[str] = None
    scenario_name: str
    completed_at: str              # ISO-8601 UTC
    overall: str                   # "PASS" | "FAIL" | "INCONCLUSIVE"
    tick_count: int
    dropped_ticks: int
    gap_count: int
    assertions: list[AssertionResultResponse]
    balance_gate: Optional[BalanceGateResponse] = None
    # Task #428: total economic dispatch cost for the run in USD.
    # None on headless runs (EDL not wired); non-None on spec-path runs.
    # Allows operators to compare scenario economics from a single number
    # without aggregating the per-tick timeseries themselves.
    total_edl_dispatch_cost_usd: Optional[float] = None



class TimeseriesRowResponse(BaseModel):
    """One tick row returned by GET /runs/{run_id}/timeseries.

    sim_time_seconds is stored from the serialisation layer (F5 convention:
    interval-END time) and is never re-derived here.
    """
    tick_index: int
    sim_time_seconds: float
    p_compute_demand_mw: float
    p_cooling_demand_mw: float
    p_demand_mw: float
    net_demand_mw: float
    turbine_output_mw: float
    bess_output_mw: float
    bess_soc_fraction: float
    confidence_lower_mw: float
    confidence_upper_mw: float
    insufficient_reserve_alert: bool
    bess_escalation_active: bool = False
    bess_escalation_reason: str = ""
    bess_bridging_available_mw: float = 0.0
    bess_bridging_floor_mw: float = 0.0
    bess_material_discharge_threshold_mw: float = 0.0
    bess_discharge_sustained_s: float = 0.0
    turbine_observed_ramp_mw_per_s: float = 0.0
    turbine_estimated_time_to_close_s: Optional[float] = None
    p_renewable_mw: float
    bess_bridging_seconds: float
    dt_lead_next_s: float
    bridging_basis: str
    gap_before: bool               # True when tick_index jumps > 1 from the previous row


class TimeseriesResponse(BaseModel):
    """Full timeseries returned by GET /runs/{run_id}/timeseries."""
    run_id: str
    gap_count: int
    rows: list[TimeseriesRowResponse]


# ---------------------------------------------------------------------------
# Operator unit command (Task #203)
# ---------------------------------------------------------------------------

class UnitCommandRequest(BaseModel):
    """Body for POST /runs/{run_id}/units/{unit_id}/command.

    action:
      "trip"  — force an on-bus unit to OFFLINE immediately; output zeroed.
                For an OFFLINE hot-standby unit, release standby and begin
                synchronization so it becomes active.
      "start" — enter the start sequence from OFFLINE; unit ramps to
                SYNCHRONISED naturally.  Only valid when state is OFFLINE.
    """
    action: Literal["trip", "start"]


class SetThermalStateRequest(BaseModel):
    """Body for POST /runs/{run_id}/units/{unit_id}/thermal-state.

    thermal_state — the standby readiness tier to assign to an OFFLINE unit:
      "cold" — unit fully cooled (longest start, ~900 s).  Default after
               extended shutdown.
      "warm" — unit partially cooled (medium start, ~300 s).  Use when the
               unit was stopped within the last few hours and conserved heat.
      "hot"  — unit recently stopped and still thermally hot (shortest start,
               ~300 s with immediate ramp).  Use to pre-position a unit for a
               fast response without putting it on the bus.

    Only valid for units in OFFLINE state with hot_standby=False.
    """
    thermal_state: Literal["hot", "warm", "cold"]
