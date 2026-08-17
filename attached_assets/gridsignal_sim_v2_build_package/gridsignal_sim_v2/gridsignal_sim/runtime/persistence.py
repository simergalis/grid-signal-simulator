"""
runtime/persistence.py — SQLAlchemy-async persistence layer.

v2.5 §22.7: ONE SQLite file on disk, WAL mode.  This is the Tier 0 + Tier 1
store for the simulator.  Promoting to PostgreSQL is a connection-string
change per §22.1 principle 4; all access goes through the ORM — no raw SQL
in application code.

reference/schema_fix.sql is the PostgreSQL PROMOTION TARGET; it is not used
here.  Table shapes and constraint reasoning come from that file; dialect
(SERIAL, JSONB, partitioning) does not.

Write paths
-----------
Two separate queues are maintained so that Tier-0 audit data (ControlEvent)
can never be dropped even under sustained write pressure:

  _write_queue  — bounded asyncio.Queue(maxsize=QUEUE_MAXSIZE) for
                  RunTimeseries (tick) rows.  append() uses put_nowait(); on
                  QueueFull the tick is DROPPED, _dropped_ticks is incremented,
                  and a WARNING is emitted once per LOG_DROP_EVERY_N drops.

                  RECORDED SIMULATOR DEVIATION (§22.2): §22.2 Tier 1 specifies
                  "buffer to Tier 0 and drain on recovery" — dropping is what
                  §22.4 permits for Tier 2 analytical batches.  In this
                  simulator, Tier 0 and Tier 1 share one SQLite file (§22.7),
                  so there is nowhere else to buffer to; drop-on-full behaviour
                  is defensible on that basis but is NOT spec-compliant §22.2
                  Tier 1 behaviour.  The _dropped_ticks counter and finalize()
                  WARNING are the mitigation and stay.
                  (D5 fix: was await put(), which could suspend inside the tick
                  and backpressure the control plane — §22.7 forbids that.)

  _ce_queue     — UNBOUNDED asyncio.Queue() for ControlEvent rows.
                  append_control_event() uses put_nowait() which never raises
                  on an unbounded queue.  ControlEvent is FR-2.5/NFR-5 audit
                  data and must never be dropped.  Keeping it on a separate
                  unbounded queue means backpressure on the SQLite write path
                  is absorbed by memory, not by silent row loss.

Both drain tasks (_drain_task for RunTimeseries, _ce_drain_task for
ControlEvent) are started by start() and stopped by stop().

This decouples SQLite write latency from tick scheduling latency: a 1–5 ms
embedded-store write in a single-process async app would otherwise appear as
tick delivery latency during NFR-2 load testing and get misattributed to the
forecast path (§22.7).

Where the queues live
---------------------
Both queues and both drain tasks are attributes of SqlitePersistedTimeseriesSink;
neither is module-level state, so concurrent runs each driven by the same sink
instance share the same serialised INSERT streams, which is correct for a
single SQLite file.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.models import TickResult

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TickResult → JSON serializer (Log-and-Trace)
# ---------------------------------------------------------------------------

def _tick_to_json(tick: TickResult) -> str:
    """Serialize a complete TickResult to a JSON string for tick_json column.

    Covers all ~80 fields: dashboard, GPU-Colo, scheduler, power-supply, and
    internal physics variables.  Uses dataclasses.asdict() for recursive
    conversion of nested dataclasses (ConfidenceBand, ContingencyCoverage,
    KubeMetrics …).  Frozensets, Enums, and IEEE-754 non-finite floats are
    handled by the _default encoder below.
    """
    import dataclasses

    def _default(obj: object) -> object:
        # frozenset/set → sorted list (handles DataQualityTag frozensets)
        if isinstance(obj, (frozenset, set)):
            try:
                return sorted(x.value for x in obj)   # Enum members
            except (AttributeError, TypeError):
                return sorted(str(x) for x in obj)
        # Enum → primitive value
        try:
            return obj.value  # type: ignore[attr-defined]
        except AttributeError:
            pass
        # IEEE-754 non-finite floats are not valid JSON
        if isinstance(obj, float) and (obj != obj or abs(obj) == float("inf")):
            return None
        return str(obj)

    try:
        return json.dumps(dataclasses.asdict(tick), default=_default)
    except Exception as exc:  # noqa: BLE001
        _log.warning("_tick_to_json: serialization failed (%s) — storing {}", exc)
        return "{}"

# Sentinel placed on _write_queue by stop() to signal the drain task to exit.
_STOP = object()


# ---------------------------------------------------------------------------
# ORM base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# §8.1 core entities
# ---------------------------------------------------------------------------

class Site(Base):
    """§8.1 Site: top-level configuration container for one physical facility."""

    __tablename__ = "site"

    site_id: Mapped[str] = mapped_column(String, primary_key=True)
    pue_base: Mapped[float] = mapped_column(Float, nullable=False)
    alpha_max: Mapped[float] = mapped_column(Float, nullable=False)
    tau_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    dt_thermal_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    uncalibrated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AssetConfig(Base):
    """§8.1 AssetConfig: one row per physical asset (GPU module, turbine,
    BESS unit, solar array) associated with a site.  config_json holds the
    full serialised config dataclass so the row is self-contained."""

    __tablename__ = "asset_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(
        String, ForeignKey("site.site_id"), nullable=False, index=True
    )
    asset_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # gpu | turbine | bess | solar
    asset_id: Mapped[str] = mapped_column(String, nullable=False)
    config_json: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON-serialised config dataclass


class Scenario(Base):
    """§8.1 Scenario: a named run configuration; one row per run.
    finalize() creates or updates this row when the run completes.

    Step 8 additions:
    - scenario_id (String, nullable, indexed): the stable ID used by
      api/routes/scenarios.py ScenarioStore.  Null for runs that were
      started via the direct job_id+node_count path.
    - spec_json (Text, nullable): JSON-serialised ScenarioSpec, copied from
      ScenarioRecord.spec_json at run start.  Null for direct-path runs.
      Step 9 migrates ScenarioStore.create() to write rows here instead of
      to the in-memory dict.

    The run_id PK is kept for backwards compatibility with the Step 2 ORM
    schema.  scenario_id is a separate, stable identifier created once per
    scenario (vs. run_id which is minted per run).
    """

    __tablename__ = "scenario"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    site_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("site.site_id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verdict: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Step 8: stable scenario ID and full spec (both nullable for old rows).
    scenario_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True, default=None
    )
    spec_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )


class RunTimeseries(Base):
    """§8.1 RunTimeseries: one row per TickResult.  Append-only (NFR-5).
    data_quality_tags and checkpoint_states are JSON strings; SQLite has no
    native JSON column type, and TEXT is portable to PostgreSQL's JSONB on
    promotion (schema_fix.sql uses JSONB)."""

    __tablename__ = "run_timeseries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    tick_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sim_time_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    p_compute_demand_mw: Mapped[float] = mapped_column(Float, nullable=False)
    p_cooling_demand_mw: Mapped[float] = mapped_column(Float, nullable=False)
    p_demand_mw: Mapped[float] = mapped_column(Float, nullable=False)
    net_demand_mw: Mapped[float] = mapped_column(Float, nullable=False)
    turbine_output_mw: Mapped[float] = mapped_column(Float, nullable=False)
    bess_output_mw: Mapped[float] = mapped_column(Float, nullable=False)
    bess_soc_fraction: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_lower_mw: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_upper_mw: Mapped[float] = mapped_column(Float, nullable=False)
    data_quality_tags: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON array of tag value strings
    insufficient_reserve_alert: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # D7 fix: §5.1 onboarding alerts — JSON array of hardware_profile_id strings
    # for which the one-time alert fired on this tick.  Empty array = no new alerts.
    unrecognised_profile_alerts: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]"
    )
    checkpoint_states: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON object: job_id -> state string
    # Step 5: wall-clock stamp alongside simulated time for every persisted row.
    # Enables forecast-error attribution against real latency (v2.5 §22.8).
    # UTC Unix timestamp (float); 0.0 when a test does not inject a real stamp.
    wall_stamp_utc: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # ── Log-and-Trace full-capture column ────────────────────────────────────
    # tick_json: complete JSON serialization of the TickResult (all ~80 fields).
    # Populated every tick via _tick_to_json(); used by the CSV export to surface
    # every dashboard, GPU-Colo, scheduler, power-supply, and internal variable
    # without requiring schema migrations each time a new field is added.
    # Empty JSON object '{}' is the safe sentinel for rows written before this
    # column was introduced (pre-migration rows that lack a real value).
    tick_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class EconomicProfile(Base):
    """Margin Contribution Tool — Economic Profile.

    One row per operator-saved rate card.  site_id FK matches the pattern
    used by AssetConfig (persistence.py:163–165) and Scenario (196–198) —
    locked decision 2: site_id scoping, no tenant_id + RLS.

    All cost fields are Optional[float] — None means "not configured" (the
    operator did not supply a value for that cost component).  The calculation
    engine treats None as 0.0 for that component, not as a fallback default.
    See api/routes/runs.py:194–200 for the is-not-None discipline this follows.

    The `proposed_here_fields` JSON column stores a list of field names the
    operator tagged as third-party estimates pending validation (PROPOSED_HERE
    amber-tag in the UI).  Example: '["turbine_capex_per_mwh","bess_capex_per_mwh"]'.
    """

    __tablename__ = "economic_profile"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID
    site_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("site.site_id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # ── Energy cost fields (variable + amortised capital) ─────────────────
    # Grid TOU rates ($/MWh imported at PCC).  grid_exchange_mw is
    # positive-on-import in tick_dicts (simulation_core.py:2089 negation).
    grid_peak_rate_per_mwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    grid_offpeak_rate_per_mwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Turbine: fuel (variable $/MWh) + amortised capital ($/MWh)
    turbine_fuel_per_mwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    turbine_capex_per_mwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # BESS: marginal charge cost (variable $/MWh dispatched) + amortised capital
    bess_marginal_per_mwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bess_capex_per_mwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Solar: amortised capital only (zero fuel cost)
    solar_capex_per_mwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Curtailment SLA credit ($/MWh curtailed or $/job-hour — stored as $/MWh curtailed)
    curtailment_per_mwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # JSON list of field names tagged PROPOSED_HERE by the operator.
    # e.g. '["turbine_capex_per_mwh","bess_capex_per_mwh","grid_peak_rate_per_mwh"]'
    proposed_here_fields: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class EconomicProfileTenantRate(Base):
    """Per-tenant billing parameters within one EconomicProfile.

    One row per (economic_profile_id, tenant_id) pair.
    tenant_id matches the values in scenario_factory._TENANT_DEFS: "A", "B", "C".
    billing_basis: "per_mw_committed" | "per_mwh_consumed" | "per_gpu_hour".
    overage_rate is Optional — None means flat billing with no overage tier
    (AC-2.5 / TC-MC-9: a tenant with no overage_rate bills at base_rate only,
    no error state).
    """

    __tablename__ = "economic_profile_tenant_rate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    economic_profile_id: Mapped[str] = mapped_column(
        String, ForeignKey("economic_profile.id"), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)  # "A" | "B" | "C"
    billing_basis: Mapped[str] = mapped_column(String, nullable=False)
    base_rate: Mapped[float] = mapped_column(Float, nullable=False)
    contracted_allocation: Mapped[float] = mapped_column(Float, nullable=False)
    overage_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sla_credit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class ControlEvent(Base):
    """§8.1 ControlEvent: append-only log of all workload signals received
    by a run.  Acknowledgments live in ControlEventAck so this table
    stays immutable per FR-2.5 / NFR-5 — no UPDATE ever touches this table."""

    __tablename__ = "control_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String, nullable=False)
    job_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    hardware_profile_id: Mapped[str] = mapped_column(String, nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False)
    workload_class: Mapped[str] = mapped_column(String, nullable=False)
    site_id: Mapped[str] = mapped_column(String, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# §17.1 deduplication window
# ---------------------------------------------------------------------------

class DedupeKey(Base):
    """§17.1: 15-minute rolling deduplication window.
    A row records the first time a (site_id, job_id, event_type, event_id)
    4-tuple was seen.  Duplicate deliveries within the window are discarded
    by checking for the row's existence before processing."""

    __tablename__ = "dedupe_key"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(String, nullable=False)
    job_id: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_id: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "site_id", "job_id", "event_type", "event_id",
            name="uq_dedupe_key_tuple",
        ),
    )


# ---------------------------------------------------------------------------
# §17.2 quarantine
# ---------------------------------------------------------------------------

class Quarantine(Base):
    """§17.2: Events that failed schema, domain, or parseability validation.

    raw_payload is TEXT (never a JSON column) because a malformed event may
    not be valid JSON at all, and §17.2 requires the full byte sequence be
    logged.  parsed_json is an optional JSON-string sidecar for events that
    parsed successfully but failed domain validation.

    failure_kind is one of: schema | domain | unparseable
    The CHECK constraint is enforced by the DB, not application code, so it
    holds even on direct writes (e.g., during a post-incident investigation).
    """

    __tablename__ = "quarantine"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)  # TEXT — never JSON column
    parsed_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # optional JSON sidecar
    failure_kind: Mapped[str] = mapped_column(
        String, nullable=False
    )  # schema | domain | unparseable
    field_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rule_violated: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Recovery path (§17.2): a correcting event may clear a quarantined entry.
    corrected_by_event: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cleared_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "failure_kind IN ('schema', 'domain', 'unparseable')",
            name="ck_quarantine_failure_kind",
        ),
    )


# ---------------------------------------------------------------------------
# §21.6 / §26.3 recommendation + audit trail
# ---------------------------------------------------------------------------

class Principal(Base):
    """§21.6: human or system principals who can review recommendations.
    role is one of: viewer | operator | approver."""

    __tablename__ = "principal"

    principal_id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # viewer|operator|approver

    __table_args__ = (
        CheckConstraint(
            "role IN ('viewer', 'operator', 'approver')",
            name="ck_principal_role",
        ),
    )


# ---------------------------------------------------------------------------
# Authentication — user accounts
# ---------------------------------------------------------------------------

class AuthUser(Base):
    """Authenticated user accounts for the GridSignal operator interface.

    Login requires all three: email + phone + password.
    Accounts are created by the admin (POST /api/admin/users); there is no
    self-registration flow.

    phone is stored as-entered and normalised for comparison in the login
    route (strips spaces, dashes, leading +).
    """

    __tablename__ = "auth_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    phone: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="operator")
    # NOTE: 'admin' must appear here — ck_auth_user_role is enforced by SQLite.
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "role IN ('viewer', 'operator', 'approver', 'admin')",
            name="ck_auth_user_role",
        ),
    )


class AuthOTP(Base):
    """One-time password codes for email-based sign-in.

    Persisted in the database so codes survive server restarts and container
    recycles.  Each row holds exactly one pending code per email address
    (UNIQUE on email).  The route layer upserts on request-code and deletes
    on successful login or exhausted attempts.

    expires_at and last_sent are stored as timezone-aware UTC datetimes so
    comparisons are unambiguous even across DST transitions or container moves.
    """

    __tablename__ = "auth_otp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    code: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_sent: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Recommendation(Base):
    """§21.6 / §26.3: agent-generated parameter change proposal.

    The DB-level CHECK constraint on reviewer_id ensures a row cannot reach
    state='applied' or state='rejected' with reviewer_id IS NULL.  This is
    enforced at the storage layer rather than application code so it holds
    even on direct DB writes during an audit or post-incident review.

    generated_by distinguishes model-produced from fallback-heuristic
    proposals; prompt_digest (SHA-256 hex) records what prompt produced a
    model response so it can be reproduced or audited.
    """

    __tablename__ = "recommendation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state: Mapped[str] = mapped_column(
        String, nullable=False, default="proposed"
    )  # proposed|under_review|applied|rejected
    originating_agent: Mapped[str] = mapped_column(String, nullable=False)
    parameter_name: Mapped[str] = mapped_column(String, nullable=False)
    current_value: Mapped[str] = mapped_column(Text, nullable=False)   # JSON-serialised
    proposed_value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-serialised
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String, nullable=False)  # SHA-256 hex
    estimated_impact: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # free-form JSON
    reversibility: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # immediate|scheduled|irreversible
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    model_vendor: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    prompt_digest: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # SHA-256 hex of the prompt used to generate this recommendation
    generated_by: Mapped[str] = mapped_column(
        String, nullable=False
    )  # model | fallback
    reviewer_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("principal.principal_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('proposed', 'under_review', 'applied', 'rejected')",
            name="ck_recommendation_state",
        ),
        CheckConstraint(
            "generated_by IN ('model', 'fallback')",
            name="ck_recommendation_generated_by",
        ),
        # §21.6: a recommendation cannot be applied or rejected without a
        # reviewer.  DB-enforced so no application code can accidentally bypass
        # it; reviewer_id must be set before the state transition is written.
        CheckConstraint(
            "NOT (state IN ('applied', 'rejected') AND reviewer_id IS NULL)",
            name="ck_recommendation_reviewer_required",
        ),
    )


class ParameterChangeAudit(Base):
    """§21.6: immutable record of every parameter change that was applied.
    reviewer_id is NOT NULL here (unlike Recommendation where it starts null);
    a row is only written after the review step passes and the change is live.
    effective_from records when the new value took effect (§21.6)."""

    __tablename__ = "parameter_change_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("recommendation.id"), nullable=True
    )
    parameter_name: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-serialised
    new_value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-serialised
    reviewer_id: Mapped[str] = mapped_column(
        String, ForeignKey("principal.principal_id"), nullable=False  # NOT NULL — §21.6
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False  # §21.6
    )
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# FR-2.5 / NFR-5 control event acknowledgment
# ---------------------------------------------------------------------------

class ControlEventAck(Base):
    """FR-2.5 / NFR-5: acknowledgments live here, not as a mutable column on
    ControlEvent, so that ControlEvent stays append-only.  An ACK is written
    when a downstream consumer (SCADA layer, advisory agent) confirms it
    has processed a control event.  One event may accumulate multiple ACKs
    from different consumers.

    ack_kind is one of: received | processed | rejected."""

    __tablename__ = "control_event_ack"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    control_event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("control_event.id"), nullable=False, index=True
    )
    acknowledged_by: Mapped[str] = mapped_column(
        String, nullable=False
    )  # system component id or principal_id
    ack_kind: Mapped[str] = mapped_column(
        String, nullable=False
    )  # received | processed | rejected
    acked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "ack_kind IN ('received', 'processed', 'rejected')",
            name="ck_control_event_ack_kind",
        ),
    )


# ---------------------------------------------------------------------------
# Runtime error log
# ---------------------------------------------------------------------------

class RuntimeErrorLog(Base):
    """Structured record written whenever the simulator detects an internal
    error during a run:

      'balance_violation' — d4_balance_defect_mw ≥ 1e-3 on any tick.
        The D4 power-accounting identity (grid_exchange + frequency_forcing
        = balance_residual) did not close.  This indicates a model-level
        accounting bug — a signal that cannot normally fire unless new code
        introduces a decomposition error.

      'exception' — an unexpected Python exception escaped the main tick
        loop in RunManager._drive().  The run terminates abnormally; detail
        carries the full traceback.

    error_kind is constrained to these two values via a CHECK constraint.
    detail is a JSON string with context-dependent fields:
      balance_violation → defect_mw, p_generation_mw, p_demand_mw,
                          grid_exchange_mw, islanded
      exception         → traceback (formatted string)
    """

    __tablename__ = "runtime_error_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    sim_time_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tick_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    __table_args__ = (
        CheckConstraint(
            "error_kind IN ('balance_violation', 'exception')",
            name="ck_runtime_error_log_kind",
        ),
    )


# ---------------------------------------------------------------------------
# SqlitePersistedTimeseriesSink
# ---------------------------------------------------------------------------

class SqlitePersistedTimeseriesSink:
    """TimeseriesSink Protocol implementation backed by a local SQLite file.

    v2.5 §22.7: one file, WAL mode.  Promoting to PostgreSQL is a
    connection-string change per §22.1 principle 4.

    Write paths (where the queues live)
    -------------------------------------
    _write_queue  — asyncio.Queue(maxsize=QUEUE_MAXSIZE), created in start().
                    append() enqueues TickResult objects using put_nowait().
                    On QueueFull, the tick is DROPPED (Tier-1 degradation per
                    §22.2), _dropped_ticks is incremented, and a WARNING is
                    emitted once per LOG_DROP_EVERY_N drops.
                    (D5 fix: was await put(), which blocked the event loop
                    under backpressure — §22.7 forbids store writes blocking
                    the event loop.)

    _ce_queue     — asyncio.Queue() with NO maxsize, created in start().
                    append_control_event() enqueues ControlEvent rows here.
                    put_nowait() on an unbounded queue never raises QueueFull,
                    so ControlEvent rows (FR-2.5/NFR-5 audit data) are NEVER
                    dropped under sustained pressure.

    _drain_task   — asyncio.Task draining _write_queue (RunTimeseries INSERTs).
    _ce_drain_task — asyncio.Task draining _ce_queue (ControlEvent INSERTs).

    Tick-path latency is limited to put_nowait() overhead (microseconds),
    not SQLite write latency (1–5 ms).

    Lifecycle
    ---------
    1. Construct: SqlitePersistedTimeseriesSink(db_path)
    2. start()    — engine, schema, both drain tasks
    3. append()   — called per tick from RunManager._drive()
    4. finalize() — drains both queues then records the verdict; logs
                    dropped-tick count if any ticks were lost this run
    5. stop()     — sends sentinels to both queues, awaits both drain tasks,
                    disposes engine
    """

    QUEUE_MAXSIZE: int = 1000
    # 1000 is a chosen value.  A 4-hour run at 5-second ticks produces 2880
    # rows maximum; 1000 gives ~3 minutes of buffering before backpressure.

    LOG_DROP_EVERY_N: int = 100
    # Emit a WARNING at most once per LOG_DROP_EVERY_N tick drops so the
    # operator sees the problem without being flooded during sustained pressure.

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._engine = None
        # _write_queue, _drain_task, _ce_queue, and _ce_drain_task are all
        # created in start() so they are bound to the correct event loop.
        # Do not create asyncio primitives in __init__.
        self._write_queue: asyncio.Queue | None = None
        self._drain_task: asyncio.Task | None = None
        self._ce_queue: asyncio.Queue | None = None
        self._ce_drain_task: asyncio.Task | None = None
        # D5 fix: count RunTimeseries rows dropped due to a full _write_queue.
        # Surfaced in finalize() so operators know data was lost this run.
        self._dropped_ticks: int = 0

    async def start(self) -> None:
        """Create engine, apply schema, start both drain tasks.
        Must be called inside a running event loop before any append()."""
        self._engine = create_async_engine(
            f"sqlite+aiosqlite:///{self._db_path}",
            echo=False,
        )
        async with self._engine.begin() as conn:
            # WAL mode per §22.7: reader/writer concurrency without full table
            # locks; better behaviour than the default rollback-journal mode
            # for a process that both writes ticks and reads them for broadcast.
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.run_sync(Base.metadata.create_all)

        # _write_queue (bounded): RunTimeseries tick rows.
        # _ce_queue (unbounded): ControlEvent audit rows — never dropped.
        # See class docstring for the D5-fix rationale on the two-queue design.
        self._write_queue = asyncio.Queue(maxsize=self.QUEUE_MAXSIZE)
        self._drain_task = asyncio.create_task(
            self._drain_loop(), name="persistence-drain"
        )
        self._ce_queue = asyncio.Queue()  # no maxsize — unbounded by design
        self._ce_drain_task = asyncio.create_task(
            self._ce_drain_loop(), name="persistence-ce-drain"
        )
        _log.debug("SqlitePersistedTimeseriesSink started: db=%s", self._db_path)

    async def stop(self) -> None:
        """Send stop sentinels to both drain tasks, wait for them to exit
        cleanly, then dispose the engine.  Call after finalize() has returned."""
        # Tick (RunTimeseries) drain.
        if self._write_queue is not None:
            await self._write_queue.put(_STOP)
        if self._drain_task is not None:
            await self._drain_task
            self._drain_task = None
        # ControlEvent drain.
        if self._ce_queue is not None:
            await self._ce_queue.put(_STOP)
        if self._ce_drain_task is not None:
            await self._ce_drain_task
            self._ce_drain_task = None
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
        _log.debug("SqlitePersistedTimeseriesSink stopped: db=%s", self._db_path)

    async def _drain_loop(self) -> None:
        """Background task: dequeue TickResult rows and INSERT them.
        Exits when it dequeues the _STOP sentinel placed by stop()."""
        assert self._engine is not None, "_drain_loop started before engine"
        assert self._write_queue is not None

        while True:
            item = await self._write_queue.get()
            if item is _STOP:
                self._write_queue.task_done()
                break
            tick: TickResult = item
            try:
                async with AsyncSession(self._engine) as session:
                    async with session.begin():
                        session.add(
                            RunTimeseries(
                                run_id=tick.run_id,
                                tick_index=tick.tick_index,
                                sim_time_seconds=tick.sim_time_seconds,
                                p_compute_demand_mw=tick.p_compute_demand_mw,
                                p_cooling_demand_mw=tick.p_cooling_demand_mw,
                                p_demand_mw=tick.p_demand_mw,
                                net_demand_mw=tick.net_demand_mw,
                                turbine_output_mw=tick.turbine_output_mw,
                                bess_output_mw=tick.bess_output_mw,
                                bess_soc_fraction=tick.bess_soc_fraction,
                                confidence_lower_mw=tick.confidence.lower_bound_mw,
                                confidence_upper_mw=tick.confidence.upper_bound_mw,
                                data_quality_tags=json.dumps(
                                    sorted(t.value for t in tick.confidence.tags)
                                ),
                                insufficient_reserve_alert=tick.insufficient_reserve_alert,
                                unrecognised_profile_alerts=json.dumps(
                                    sorted(tick.unrecognised_profile_alerts)
                                ),
                                checkpoint_states=json.dumps(tick.checkpoint_states),
                                wall_stamp_utc=tick.wall_stamp_utc,
                                # Log-and-Trace: full serialization of all ~80 fields.
                                # Dashboard, GPU-Colo, scheduler, power-supply, and
                                # every internal physics variable are captured here.
                                tick_json=_tick_to_json(tick),
                            )
                        )
            except Exception:
                _log.exception(
                    "persistence drain: failed to write tick %d for run %s",
                    tick.tick_index,
                    tick.run_id,
                )
            finally:
                # task_done() must be called whether the write succeeded or
                # failed so that join() in finalize() is not blocked by errors.
                self._write_queue.task_done()

    async def _ce_drain_loop(self) -> None:
        """Background task: dequeue ControlEvent rows and INSERT them.
        Uses an unbounded queue so no audit row is ever dropped.
        Exits when it dequeues the _STOP sentinel placed by stop()."""
        assert self._engine is not None, "_ce_drain_loop started before engine"
        assert self._ce_queue is not None

        while True:
            item = await self._ce_queue.get()
            if item is _STOP:
                self._ce_queue.task_done()
                break
            ce: ControlEvent = item
            try:
                async with AsyncSession(self._engine) as session:
                    async with session.begin():
                        session.add(ce)
            except Exception:
                _log.exception(
                    "persistence ce-drain: failed to write ControlEvent %r "
                    "for run %s",
                    ce.event_id,
                    ce.run_id,
                )
            finally:
                self._ce_queue.task_done()

    # ------------------------------------------------------------------
    # TimeseriesSink Protocol
    # ------------------------------------------------------------------

    async def append(self, tick: TickResult) -> None:
        """Enqueue tick for background write.  Returns as soon as put_nowait()
        is called — does not wait for the DB INSERT to complete.

        D5 fix: uses put_nowait() instead of await put().  §22.7 forbids
        store writes from blocking the event loop; await put() on a full queue
        would suspend inside the tick path, surfacing SQLite latency as tick
        delivery latency.

        If _write_queue is at capacity, the tick is DROPPED (Tier-1 degradation
        per §22.2), _dropped_ticks is incremented, and a WARNING is emitted
        once per LOG_DROP_EVERY_N drops.  ControlEvent rows are NOT routed here;
        use append_control_event() — they travel on the unbounded _ce_queue and
        are never dropped."""
        if self._write_queue is None:
            raise RuntimeError(
                "SqlitePersistedTimeseriesSink.start() has not been called"
            )
        try:
            self._write_queue.put_nowait(tick)
        except asyncio.QueueFull:
            self._dropped_ticks += 1
            if self._dropped_ticks % self.LOG_DROP_EVERY_N == 1:
                # Log on the 1st drop and every LOG_DROP_EVERY_N thereafter.
                _log.warning(
                    "persistence write queue full (%d capacity); tick DROPPED "
                    "(total dropped this sink: %d).  Drain task is behind tick "
                    "rate — §22.2 Tier-1 degradation in effect.",
                    self.QUEUE_MAXSIZE,
                    self._dropped_ticks,
                )

    async def append_control_event(self, ce: ControlEvent) -> None:
        """Enqueue a ControlEvent row for background write on the unbounded
        _ce_queue.  put_nowait() on an unbounded queue never raises QueueFull,
        so ControlEvent rows (FR-2.5/NFR-5 audit data) are NEVER dropped.

        This is the correct path for audit rows.  Tick rows belong in append().
        """
        if self._ce_queue is None:
            raise RuntimeError(
                "SqlitePersistedTimeseriesSink.start() has not been called"
            )
        self._ce_queue.put_nowait(ce)

    async def append_error(
        self,
        error_kind: str,
        run_id: Optional[str],
        message: str,
        detail: Optional[str] = None,
        sim_time_seconds: Optional[float] = None,
        tick_index: Optional[int] = None,
    ) -> None:
        """Persist a structured runtime error record directly (no queue).

        Errors are rare (balance violations, unexpected exceptions) so a
        synchronous inline write is used rather than enqueueing.  A failure
        here is logged at WARNING level and swallowed — the caller must not
        crash because error logging failed.

        error_kind must be 'balance_violation' or 'exception' (enforced by
        the DB CHECK constraint; a wrong value will raise on commit).
        """
        if self._engine is None:
            return
        try:
            async with AsyncSession(self._engine) as _err_session:
                async with _err_session.begin():
                    _err_session.add(
                        RuntimeErrorLog(
                            logged_at=datetime.now(timezone.utc),
                            error_kind=error_kind,
                            run_id=run_id,
                            sim_time_seconds=sim_time_seconds,
                            tick_index=tick_index,
                            message=message,
                            detail=detail,
                        )
                    )
        except Exception:  # noqa: BLE001
            _log.warning(
                "append_error: failed to persist %s for run %s (swallowed)",
                error_kind, run_id, exc_info=True,
            )

    async def finalize(self, run_id: str, verdict: str | None) -> None:
        """Flush all pending tick and ControlEvent writes, then record the
        run's completion.

        join() blocks until every item already on both queues has had
        task_done() called by the respective drain task.  Only then is the
        Scenario row written, guaranteeing that when finalize() returns all
        ticks, all ControlEvent rows, and the verdict are durable.

        If any ticks were dropped during this run due to write-queue pressure,
        a WARNING is emitted here so the operator can see the data loss in the
        run summary without having to grep mid-run logs."""
        if self._write_queue is None or self._ce_queue is None:
            raise RuntimeError(
                "SqlitePersistedTimeseriesSink.start() has not been called"
            )
        # Drain both queues before writing the verdict row.
        await self._write_queue.join()
        await self._ce_queue.join()

        if self._dropped_ticks > 0:
            _log.warning(
                "run %s finalized with %d RunTimeseries row(s) dropped due to "
                "write-queue pressure (§22.2 Tier-1 degradation).  "
                "Persisted tick count may be less than total tick count.",
                run_id,
                self._dropped_ticks,
            )

        if self._engine is None:
            return
        now = datetime.now(timezone.utc)
        async with AsyncSession(self._engine) as session:
            async with session.begin():
                stmt = select(Scenario).where(Scenario.run_id == run_id)
                result = await session.execute(stmt)
                scenario = result.scalar_one_or_none()
                if scenario is None:
                    scenario = Scenario(
                        run_id=run_id,
                        name=run_id,
                        created_at=now,
                    )
                    session.add(scenario)
                scenario.completed_at = now
                scenario.verdict = verdict
        _log.debug("run %s finalized: verdict=%r", run_id, verdict)

    # ------------------------------------------------------------------
    # Step 9 — Evaluation helpers (TimeseriesSink Protocol extension)
    # ------------------------------------------------------------------

    async def get_eval_rows(self, run_id: str) -> list:
        """Flush the write queue, then return lightweight EvalRow tuples.

        Flushes via join() so all ticks appended before this call have
        been written before the query executes.  A second join() in the
        subsequent finalize() call is a harmless no-op on an empty queue.

        Returns list[EvalRow] — typed as list to avoid importing EvalRow
        here (the reverse import runtime/persistence.py → runtime/verdict.py
        is safe, but deferring it keeps the import surface narrow).
        """
        from runtime.verdict import EvalRow  # deferred: safe, no circular dep
        if self._write_queue is None or self._engine is None:
            return []
        await self._write_queue.join()
        async with AsyncSession(self._engine) as session:
            stmt = (
                select(RunTimeseries)
                .where(RunTimeseries.run_id == run_id)
                .order_by(RunTimeseries.tick_index)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [
            EvalRow(
                tick_index=r.tick_index,
                p_demand_mw=r.p_demand_mw,
                bess_soc_fraction=r.bess_soc_fraction,
                insufficient_reserve_alert=r.insufficient_reserve_alert,
            )
            for r in rows
        ]

    def get_dropped_ticks(self) -> int:
        """Number of RunTimeseries rows dropped due to write-queue pressure."""
        return self._dropped_ticks

    async def get_tick_dicts(self, run_id: str) -> list[dict]:
        """Flush the write queue, then return all tick rows as serialisation dicts.

        The dict format mirrors _tick_result_to_dict() in run_manager.py
        so the timeseries endpoint can stream rows with gap_before flags
        without any further transformation.

        Note: confidence_lower_mw / confidence_upper_mw and
        data_quality_tags / checkpoint_states are stored in separate
        columns / JSON columns and are re-composed here.
        """
        if self._write_queue is None or self._engine is None:
            return []
        await self._write_queue.join()
        async with AsyncSession(self._engine) as session:
            stmt = (
                select(RunTimeseries)
                .where(RunTimeseries.run_id == run_id)
                .order_by(RunTimeseries.tick_index)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [
            {
                "run_id": r.run_id,
                "tick_index": r.tick_index,
                "sim_time_seconds": r.sim_time_seconds,
                "p_compute_mw": r.p_compute_demand_mw,
                "p_cooling_mw": r.p_cooling_demand_mw,
                "p_total_mw": r.p_demand_mw,
                "net_demand_mw": r.net_demand_mw,
                "turbine_output_mw": r.turbine_output_mw,
                "bess_output_mw": r.bess_output_mw,
                "bess_soc_fraction": r.bess_soc_fraction,
                "confidence_lower_mw": r.confidence_lower_mw,
                "confidence_upper_mw": r.confidence_upper_mw,
                "data_quality_tags": json.loads(r.data_quality_tags),
                "insufficient_reserve_alert": r.insufficient_reserve_alert,
                "checkpoint_states": json.loads(r.checkpoint_states),
                "p_renewable_mw": 0.0,   # not stored in RunTimeseries (Step 9 gap; Step 11 adds it)
                "bess_bridging_seconds": 86400.0,  # not stored; sentinel = "full reserve"
                "dt_lead_next_s": 0.0,
                "bridging_basis": "current_demand",
            }
            for r in rows
        ]
