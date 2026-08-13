# GS-DES-GRID-001 — Grid Connection Configuration & Telemetry Schema

Status: DRAFT — for Replit agent integration
Depends on: Functional Spec v2.5 §7.1, §7.1.1, §24 (Grid Procurement), §28.5 (Transition Modes), §28.7 (Boundary)
Introduces: GP-5 (new open item — export-side parameters are unspecified upstream; see §9)

---

## 1. Scope

This document schematizes the GRID CONNECTION modal into three data classes and gives frontend
(TypeScript), backend (Pydantic), and storage (Postgres DDL) representations for each. It does not
change any control boundary in the spec: nothing here is ever written to switchgear, transfer
hardware, or protection relays. Config rows are operator inputs GridSignal *advises against*;
telemetry rows are PMS-owned measurements GridSignal *reads*.

**Three data classes, and why they don't collapse into one:**

| Class | Who writes it | Where it lives | Cadence |
|---|---|---|---|
| `GridConnectionConfig` | Operator, via this modal | Postgres, RLS on `tenant_id` | Changes rarely; versioned |
| `GridConnectionTelemetry` | PMS, via Connector Fabric (Modbus/IEC 61850/DNP3) | Time-series store; latest cached in-memory | Sub-second to seconds |
| `GridConnectionDerived` | Computed server-side on read | Not persisted | Computed per request/tick |

Per the presentation-layer-arithmetic prohibition (spec discipline), the frontend never computes
`GridConnectionDerived` fields itself — it reads them from the API response.

---

## 2. GridConnectionConfig (operator-configurable, persisted)

### 2.1 Identity & versioning

| Field | Type | Notes |
|---|---|---|
| `site_id` | `uuid` | FK to site |
| `tenant_id` | `uuid` | RLS key |
| `config_version` | `integer` | Monotonic; incremented on every save |
| `updated_by` | `uuid` | Operator user id |
| `updated_at` | `timestamptz` | |

### 2.2 Inbound (import)

| Field | Type | Unit | Default | Validation | Spec ref |
|---|---|---|---|---|---|
| `connection_mode` | enum `islanded` \| `grid_tied` \| `hybrid` | — | `islanded` | — | §7.1.1 |
| `p_grid_firm_mw` | `float` | MW | `0.0` | `>= 0` | §24.1 |
| `p_grid_reserved_mw` | `float` | MW | `0.0` | `>= 0` | §24.1 |
| `t_reserve_hours` | `float` | hours | `0.0` | `>= 0` | §24.1 |
| `spot_import_enabled` | `bool` | — | `false` | — | §24.1 |
| `p_grid_spot_cap_mw` | `float` | MW | `0.0` | `>= 0`; ignored if `spot_import_enabled = false` | §24.1 |
| `transition_mode` | enum `open` \| `closed` \| `delayed` \| `soft_load` | — | `open` | — | §28.5 |
| `pcc_import_limit_mw` | `float` | MW | required, no default | `> 0`; `p_grid_firm_mw + p_grid_reserved_mw <= pcc_import_limit_mw` | interconnection agreement |
| `demand_charge_threshold_mw` | `float` | MW | `null` | `>= 0` if set | GP-3 |
| `procurement_budget_ceiling_window_usd` | `decimal(12,2)` | USD | `null` | `>= 0` if set | §24.3 |
| `procurement_budget_ceiling_period_usd` | `decimal(12,2)` | USD | `null` | `>= 0` if set | §24.3 |
| `price_feed_source` | enum `utility_tou_tariff` \| `iso_day_ahead` \| `fixed_rate` | — | `fixed_rate` | — | GP-2 (open — no source/format/cadence specified upstream) |

### 2.3 Outbound (export) — **GP-5, see §9**

| Field | Type | Unit | Default | Validation | Notes |
|---|---|---|---|---|---|
| `export_enabled` | `bool` | — | `false` | Must be `false` when `connection_mode = islanded` (GP-4) | |
| `export_mode` | enum `none` \| `net_metering` \| `wholesale_economic` \| `demand_response` \| `vpp_dispatch` \| `emergency_grid_support` | — | `none` | — | |
| `p_export_max_mw` | `float` | MW | `0.0` | `>= 0`; `0` if `export_enabled = false` | ceiling per interconnection agreement, not derived from `pcc_import_limit_mw` |
| `export_ramp_rate_limit_mw_per_min` | `float` | MW/min | `null` | `> 0` if set | utility-imposed |
| `power_factor_min` | `float` | dimensionless | `0.95` | `0.80 <= x <= 1.00` | |
| `export_price_feed_source` | enum `iso_real_time_lmp` \| `bilateral_ppa_rate` \| `none` | — | `none` | Required (`!= none`) if `export_mode = wholesale_economic` | |
| `utility_curtail_export_channel_enabled` | `bool` | — | `true` | — | utility-initiated DR/curtailment call |
| `backup_genset_export_eligible` | `bool` | — | `false` | **See §9 — recommend read-only from GridSignal's side, not operator-settable here** | |

---

## 3. GridConnectionTelemetry (PMS-owned, read-only, ingested via Connector Fabric)

Never written by GridSignal. Sourced per §28.3's asset-telemetry transport row (Modbus TCP, IEC 61850,
DNP3, IEC 60870-5-104, OPC).

| Field | Type | Unit | Source |
|---|---|---|---|
| `mw_imported` | `float` | MW | PCC meter |
| `mw_exported` | `float` | MW | PCC meter |
| `pcc_frequency_hz` | `float` | Hz | protection relay / station bus |
| `pcc_voltage_pu` | `float` | p.u. | protection relay / station bus |
| `connection_state` | enum `connected` \| `transitioning` \| `islanded` | — | ATS / protection layer |
| `last_updated_at` | `timestamptz` | — | connector fabric ingest time |

`GridConnectionTelemetry` rows are append-only time-series (Section 22 storage tiers apply); the API
serves the latest sample per site.

---

## 4. GridConnectionDerived (computed server-side, not persisted)

| Field | Type | Formula | Notes |
|---|---|---|---|
| `net_pcc_mw` | `float` | `mw_imported - mw_exported` | signed: positive = net import |
| `firm_headroom_mw` | `float` | `max(0, p_grid_firm_mw - mw_imported)` | |
| `reserve_window_active` | `bool` | `t_reserve_hours > 0 and` reservation window contains now | requires a `ReservationProposal` window record (§24.2), not shown here — see PX-1/GP-1 |
| `export_headroom_mw` | `float` | `max(0, p_export_max_mw - mw_exported)` | `0` when `export_enabled = false` |
| `budget_utilization_pct` | `float \| null` | spend-to-date / `procurement_budget_ceiling_period_usd` | `null` if no ceiling configured |

---

## 5. TypeScript (frontend)

```typescript
type ConnectionMode = "islanded" | "grid_tied" | "hybrid";
type TransitionMode = "open" | "closed" | "delayed" | "soft_load";
type PriceFeedSource = "utility_tou_tariff" | "iso_day_ahead" | "fixed_rate";
type ExportMode =
  | "none"
  | "net_metering"
  | "wholesale_economic"
  | "demand_response"
  | "vpp_dispatch"
  | "emergency_grid_support";
type ExportPriceFeedSource = "iso_real_time_lmp" | "bilateral_ppa_rate" | "none";
type ConnectionState = "connected" | "transitioning" | "islanded";

interface GridConnectionConfig {
  siteId: string;
  tenantId: string;
  configVersion: number;
  updatedBy: string;
  updatedAt: string; // ISO 8601

  // Inbound
  connectionMode: ConnectionMode;
  pGridFirmMw: number;
  pGridReservedMw: number;
  tReserveHours: number;
  spotImportEnabled: boolean;
  pGridSpotCapMw: number;
  transitionMode: TransitionMode;
  pccImportLimitMw: number;
  demandChargeThresholdMw: number | null;
  procurementBudgetCeilingWindowUsd: number | null;
  procurementBudgetCeilingPeriodUsd: number | null;
  priceFeedSource: PriceFeedSource;

  // Outbound
  exportEnabled: boolean;
  exportMode: ExportMode;
  pExportMaxMw: number;
  exportRampRateLimitMwPerMin: number | null;
  powerFactorMin: number;
  exportPriceFeedSource: ExportPriceFeedSource;
  utilityCurtailExportChannelEnabled: boolean;
  backupGensetExportEligible: boolean;
}

interface GridConnectionTelemetry {
  mwImported: number;
  mwExported: number;
  pccFrequencyHz: number;
  pccVoltagePu: number;
  connectionState: ConnectionState;
  lastUpdatedAt: string;
}

interface GridConnectionDerived {
  netPccMw: number;
  firmHeadroomMw: number;
  reserveWindowActive: boolean;
  exportHeadroomMw: number;
  budgetUtilizationPct: number | null;
}

interface GridConnectionModalData {
  config: GridConnectionConfig;
  telemetry: GridConnectionTelemetry;
  derived: GridConnectionDerived;
}
```

## 6. Pydantic (backend)

```python
from decimal import Decimal
from enum import Enum
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class ConnectionMode(str, Enum):
    islanded = "islanded"
    grid_tied = "grid_tied"
    hybrid = "hybrid"


class TransitionMode(str, Enum):
    open = "open"
    closed = "closed"
    delayed = "delayed"
    soft_load = "soft_load"


class PriceFeedSource(str, Enum):
    utility_tou_tariff = "utility_tou_tariff"
    iso_day_ahead = "iso_day_ahead"
    fixed_rate = "fixed_rate"


class ExportMode(str, Enum):
    none = "none"
    net_metering = "net_metering"
    wholesale_economic = "wholesale_economic"
    demand_response = "demand_response"
    vpp_dispatch = "vpp_dispatch"
    emergency_grid_support = "emergency_grid_support"


class ExportPriceFeedSource(str, Enum):
    iso_real_time_lmp = "iso_real_time_lmp"
    bilateral_ppa_rate = "bilateral_ppa_rate"
    none = "none"


class ConnectionState(str, Enum):
    connected = "connected"
    transitioning = "transitioning"
    islanded = "islanded"


class GridConnectionConfig(BaseModel):
    site_id: UUID
    tenant_id: UUID
    config_version: int
    updated_by: UUID
    updated_at: datetime

    # Inbound
    connection_mode: ConnectionMode = ConnectionMode.islanded
    p_grid_firm_mw: float = Field(ge=0, default=0.0)
    p_grid_reserved_mw: float = Field(ge=0, default=0.0)
    t_reserve_hours: float = Field(ge=0, default=0.0)
    spot_import_enabled: bool = False
    p_grid_spot_cap_mw: float = Field(ge=0, default=0.0)
    transition_mode: TransitionMode = TransitionMode.open
    pcc_import_limit_mw: float = Field(gt=0)
    demand_charge_threshold_mw: Optional[float] = Field(default=None, ge=0)
    procurement_budget_ceiling_window_usd: Optional[Decimal] = Field(default=None, ge=0)
    procurement_budget_ceiling_period_usd: Optional[Decimal] = Field(default=None, ge=0)
    price_feed_source: PriceFeedSource = PriceFeedSource.fixed_rate

    # Outbound
    export_enabled: bool = False
    export_mode: ExportMode = ExportMode.none
    p_export_max_mw: float = Field(ge=0, default=0.0)
    export_ramp_rate_limit_mw_per_min: Optional[float] = Field(default=None, gt=0)
    power_factor_min: float = Field(ge=0.80, le=1.00, default=0.95)
    export_price_feed_source: ExportPriceFeedSource = ExportPriceFeedSource.none
    utility_curtail_export_channel_enabled: bool = True
    backup_genset_export_eligible: bool = False

    @model_validator(mode="after")
    def check_import_capacity(self) -> "GridConnectionConfig":
        if self.p_grid_firm_mw + self.p_grid_reserved_mw > self.pcc_import_limit_mw:
            raise ValueError(
                "p_grid_firm_mw + p_grid_reserved_mw exceeds pcc_import_limit_mw"
            )
        return self

    @model_validator(mode="after")
    def check_islanded_export(self) -> "GridConnectionConfig":
        # GP-4: islanded sites have no procurement/export surface at all.
        if self.connection_mode == ConnectionMode.islanded and self.export_enabled:
            raise ValueError("export_enabled must be false when connection_mode is islanded")
        return self

    @model_validator(mode="after")
    def check_wholesale_price_feed(self) -> "GridConnectionConfig":
        if (
            self.export_mode == ExportMode.wholesale_economic
            and self.export_price_feed_source == ExportPriceFeedSource.none
        ):
            raise ValueError("export_price_feed_source is required when export_mode is wholesale_economic")
        return self


class GridConnectionTelemetry(BaseModel):
    mw_imported: float
    mw_exported: float
    pcc_frequency_hz: float
    pcc_voltage_pu: float
    connection_state: ConnectionState
    last_updated_at: datetime


class GridConnectionDerived(BaseModel):
    net_pcc_mw: float
    firm_headroom_mw: float
    reserve_window_active: bool
    export_headroom_mw: float
    budget_utilization_pct: Optional[float]


class GridConnectionModalData(BaseModel):
    config: GridConnectionConfig
    telemetry: GridConnectionTelemetry
    derived: GridConnectionDerived
```

## 7. Postgres DDL

```sql
CREATE TABLE grid_connection_config (
    site_id                                 uuid PRIMARY KEY REFERENCES sites(site_id),
    tenant_id                               uuid NOT NULL REFERENCES tenants(tenant_id),
    config_version                          integer NOT NULL DEFAULT 1,
    updated_by                              uuid NOT NULL,
    updated_at                              timestamptz NOT NULL DEFAULT now(),

    connection_mode                         text NOT NULL DEFAULT 'islanded'
        CHECK (connection_mode IN ('islanded', 'grid_tied', 'hybrid')),
    p_grid_firm_mw                          numeric(8,3) NOT NULL DEFAULT 0 CHECK (p_grid_firm_mw >= 0),
    p_grid_reserved_mw                      numeric(8,3) NOT NULL DEFAULT 0 CHECK (p_grid_reserved_mw >= 0),
    t_reserve_hours                         numeric(6,2) NOT NULL DEFAULT 0 CHECK (t_reserve_hours >= 0),
    spot_import_enabled                     boolean NOT NULL DEFAULT false,
    p_grid_spot_cap_mw                      numeric(8,3) NOT NULL DEFAULT 0 CHECK (p_grid_spot_cap_mw >= 0),
    transition_mode                         text NOT NULL DEFAULT 'open'
        CHECK (transition_mode IN ('open', 'closed', 'delayed', 'soft_load')),
    pcc_import_limit_mw                     numeric(8,3) NOT NULL CHECK (pcc_import_limit_mw > 0),
    demand_charge_threshold_mw              numeric(8,3) CHECK (demand_charge_threshold_mw >= 0),
    procurement_budget_ceiling_window_usd   numeric(12,2) CHECK (procurement_budget_ceiling_window_usd >= 0),
    procurement_budget_ceiling_period_usd   numeric(12,2) CHECK (procurement_budget_ceiling_period_usd >= 0),
    price_feed_source                       text NOT NULL DEFAULT 'fixed_rate'
        CHECK (price_feed_source IN ('utility_tou_tariff', 'iso_day_ahead', 'fixed_rate')),

    export_enabled                          boolean NOT NULL DEFAULT false,
    export_mode                             text NOT NULL DEFAULT 'none'
        CHECK (export_mode IN ('none','net_metering','wholesale_economic','demand_response','vpp_dispatch','emergency_grid_support')),
    p_export_max_mw                         numeric(8,3) NOT NULL DEFAULT 0 CHECK (p_export_max_mw >= 0),
    export_ramp_rate_limit_mw_per_min       numeric(8,3) CHECK (export_ramp_rate_limit_mw_per_min > 0),
    power_factor_min                        numeric(4,3) NOT NULL DEFAULT 0.95
        CHECK (power_factor_min BETWEEN 0.80 AND 1.00),
    export_price_feed_source                text NOT NULL DEFAULT 'none'
        CHECK (export_price_feed_source IN ('iso_real_time_lmp', 'bilateral_ppa_rate', 'none')),
    utility_curtail_export_channel_enabled  boolean NOT NULL DEFAULT true,
    backup_genset_export_eligible           boolean NOT NULL DEFAULT false,

    CONSTRAINT import_within_pcc_limit
        CHECK (p_grid_firm_mw + p_grid_reserved_mw <= pcc_import_limit_mw),
    CONSTRAINT no_export_when_islanded
        CHECK (NOT (connection_mode = 'islanded' AND export_enabled))
);

ALTER TABLE grid_connection_config ENABLE ROW LEVEL SECURITY;

CREATE POLICY grid_connection_config_tenant_isolation ON grid_connection_config
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Telemetry is time-series; latest-sample view backs the modal's live stats.
CREATE TABLE grid_connection_telemetry (
    site_id             uuid NOT NULL REFERENCES sites(site_id),
    tenant_id           uuid NOT NULL REFERENCES tenants(tenant_id),
    sampled_at          timestamptz NOT NULL,
    mw_imported         numeric(8,3) NOT NULL,
    mw_exported         numeric(8,3) NOT NULL,
    pcc_frequency_hz    numeric(6,3) NOT NULL,
    pcc_voltage_pu      numeric(5,4) NOT NULL,
    connection_state    text NOT NULL CHECK (connection_state IN ('connected','transitioning','islanded')),
    PRIMARY KEY (site_id, sampled_at)
);

ALTER TABLE grid_connection_telemetry ENABLE ROW LEVEL SECURITY;

CREATE POLICY grid_connection_telemetry_tenant_isolation ON grid_connection_telemetry
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

---

## 8. Advisory-boundary constants (not stored, UI-only)

These four rows render in the modal as read-only status, never as editable fields. Hardcode as a
frontend constant, not a database row — they are not site configuration, they are a statement of
product boundary and must not drift per-site.

```typescript
const ADVISORY_BOUNDARY = [
  { label: "Anti-islanding protection", authority: "PMS owns · never commands" },
  { label: "Droop secondary regulation", authority: "PMS owns · never commands" },
  { label: "Reverse-power protection", authority: "PMS owns · never commands" },
  { label: "Point-of-common-coupling control", authority: "PMS owns · grid-code compliance" },
] as const;
```

---

## 9. Open items

- **GP-5 — Export-side parameters are unvalidated against a real interconnection agreement.**
  Unlike the inbound fields (traceable to §24.1/§28.5), `export_mode`, `p_export_max_mw`,
  `export_ramp_rate_limit_mw_per_min`, and `power_factor_min` are drafted from general DC/microgrid
  interconnection practice, not from a design-partner agreement or PX-4's electrical digital twin.
  Needs validation at the first site with actual export capability before this schema is treated as
  final.
- **`backup_genset_export_eligible` placement is unresolved.** This may belong entirely in the
  PMS/protection layer's certification record rather than in GridSignal's config at all — GridSignal
  arguably should only *read* it, the way it reads other asset capability telemetry (§28.3), not let
  an operator set it here. Recommend resolving before implementation rather than shipping it
  editable and walking it back.
- **GP-4 enforcement is partial in this schema.** The DB constraint blocks `export_enabled = true`
  while islanded, but the full GP-4 requirement — the outbound section and the entire procurement
  surface degrading to *absent*, not just disabled — is a frontend rendering rule, not a data
  constraint, and belongs in the modal's component logic, not here.
- **GP-1/GP-2 unresolved upstream.** `price_feed_source` and `export_price_feed_source` are enums of
  UI choices, not integrations. No source, format, or update cadence is specified for either feed;
  this schema treats them as configuration pointers to be wired up once GP-1/GP-2 are closed.
