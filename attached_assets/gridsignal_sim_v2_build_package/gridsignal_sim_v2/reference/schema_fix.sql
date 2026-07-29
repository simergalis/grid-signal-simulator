-- ============================================================================
-- A-8 + A-3 + C-5 remediation. Tier 1 (external PostgreSQL).
-- A-3: dedupe key adopts the v2.5 §17.1 tuple (site_id, job_id, event_type, event_id)
-- A-8: partitioned-table PK must include the partition key
-- C-5: control_event immutability; quarantine must accept unparseable payloads;
--      one clock basis per table
-- ============================================================================

CREATE TABLE workload_signal (
    -- §17.1 dedupe tuple, + partition key per A-8
    site_id             TEXT NOT NULL,
    job_id              TEXT NOT NULL,
    event_type          TEXT NOT NULL
        CHECK (event_type IN ('queued','starting','running','scale',
                              'checkpoint_start','checkpoint_end','job_end','cancelled')),
    event_id            TEXT NOT NULL,
    source_ts           TIMESTAMPTZ NOT NULL,
    sim_ts_s            DOUBLE PRECISION NOT NULL,
    ingest_ts           TIMESTAMPTZ NOT NULL,
    hardware_profile_id TEXT NOT NULL,
    counting_unit       TEXT NOT NULL              -- A-4, v2.5 §5.2
        CHECK (counting_unit IN ('chassis','cabinet','package','die','accelerator')),
    node_count          INTEGER NOT NULL CHECK (node_count >= 0),
    workload_class      TEXT NOT NULL
        CHECK (workload_class IN ('training','inference','other')),
    queue_depth         DOUBLE PRECISION,
    skew_flagged        BOOLEAN NOT NULL DEFAULT FALSE,
    clock_class         TEXT NOT NULL DEFAULT 'ntp'   -- A-2, v2.5 §11.4 / TC-69,70
        CHECK (clock_class IN ('ptp','ntp','unqualified')),
    scenario_run_id     UUID NOT NULL,
    PRIMARY KEY (site_id, job_id, event_type, event_id, source_ts)
) PARTITION BY RANGE (source_ts);

CREATE TABLE forecast (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY,
    issued_at           TIMESTAMPTZ NOT NULL,
    site_id             TEXT NOT NULL,
    sim_ts_s            DOUBLE PRECISION NOT NULL,
    p_compute_mw        DOUBLE PRECISION NOT NULL,
    p_cooling_mw        DOUBLE PRECISION NOT NULL,
    p_total_mw          DOUBLE PRECISION NOT NULL,
    p_renewable_mw      DOUBLE PRECISION NOT NULL,
    p_dispatch_req_mw   DOUBLE PRECISION NOT NULL,
    confidence_pct      DOUBLE PRECISION NOT NULL,
    band_lower_mw       DOUBLE PRECISION NOT NULL,   -- B-7: TC-17 sizes off this
    band_upper_mw       DOUBLE PRECISION NOT NULL,
    quality_tags        TEXT[] NOT NULL DEFAULT '{}',
    applied_params      JSONB NOT NULL,
    scenario_run_id     UUID NOT NULL,
    PRIMARY KEY (id, issued_at)                      -- A-8
) PARTITION BY RANGE (issued_at);

-- C-5: append-only. No acknowledged_at column; acks live in their own table.
CREATE TABLE control_event (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY,
    issued_at           TIMESTAMPTZ NOT NULL,
    command_id          TEXT NOT NULL,
    site_id             TEXT NOT NULL,
    asset_id            TEXT,
    action              TEXT NOT NULL,
    target_value        DOUBLE PRECISION,
    sim_ts_s            DOUBLE PRECISION NOT NULL,
    operating_tier      TEXT NOT NULL,
    authorized_by       TEXT,
    source_forecast_id  BIGINT,
    expires_at          TIMESTAMPTZ,
    scenario_run_id     UUID NOT NULL,
    PRIMARY KEY (id, issued_at),
    UNIQUE (command_id, issued_at)
) PARTITION BY RANGE (issued_at);

CREATE TABLE control_event_ack (
    command_id          TEXT PRIMARY KEY,
    acknowledged_at     TIMESTAMPTZ NOT NULL,
    acknowledged_by     TEXT NOT NULL,
    outcome             TEXT NOT NULL
        CHECK (outcome IN ('accepted','rejected','expired','superseded'))
);

-- C-5: raw_payload must accept input that is not valid JSON.
CREATE TABLE quarantine (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_payload         TEXT NOT NULL,
    parsed_payload      JSONB,
    failure_kind        TEXT NOT NULL CHECK (failure_kind IN ('schema','domain','unparseable')),
    field_name          TEXT,
    rule_violated       TEXT NOT NULL,
    affected_job_id     TEXT,
    corrected_by_event  TEXT,                        -- B-8: recovery path
    cleared_at          TIMESTAMPTZ,
    scenario_run_id     UUID
);

-- C-5: one clock basis. Both expiry and suppression in simulated seconds.
CREATE TABLE recommendation (
    recommendation_id   TEXT PRIMARY KEY,
    originating_agent   TEXT NOT NULL,
    kind                TEXT NOT NULL,
    state               TEXT NOT NULL DEFAULT 'proposed'
        CHECK (state IN ('proposed','under_review','applied','rejected')),
    parameter           TEXT,
    current_value       DOUBLE PRECISION,
    proposed_value      DOUBLE PRECISION,
    observation_count   INTEGER NOT NULL,
    window_start_sim_s  DOUBLE PRECISION NOT NULL,
    window_end_sim_s    DOUBLE PRECISION NOT NULL,
    measured_improvement DOUBLE PRECISION,
    evidence_digest     JSONB NOT NULL,
    estimated_impact    JSONB NOT NULL,
    reversibility       TEXT NOT NULL CHECK (reversibility IN ('full','partial','none')),
    expires_at_sim_s    DOUBLE PRECISION NOT NULL,
    suppressed_until_sim_s DOUBLE PRECISION,
    model_vendor        TEXT NOT NULL,
    model_id            TEXT NOT NULL,
    prompt_digest       TEXT NOT NULL,
    generated_by        TEXT NOT NULL CHECK (generated_by IN ('model','fallback')),
    created_at_sim_s    DOUBLE PRECISION NOT NULL,
    created_at_wall     TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewer_id         TEXT,
    reviewed_at         TIMESTAMPTZ,
    reject_reason       TEXT,
    CHECK (state IN ('proposed','under_review') OR reviewer_id IS NOT NULL)  -- A-5
);

-- A-5: minimal principal model. Makes the gate a door.
CREATE TABLE principal (
    principal_id        TEXT PRIMARY KEY,
    display_name        TEXT NOT NULL,
    role                TEXT NOT NULL CHECK (role IN ('viewer','operator','approver')),
    active              BOOLEAN NOT NULL DEFAULT TRUE
);

-- A-2: NetworkTelemetry, dispatch-path ineligible BY CONTRACT (TC-74).
CREATE TABLE network_telemetry (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY,
    observed_at         TIMESTAMPTZ NOT NULL,
    site_id             TEXT NOT NULL,
    switch_id           TEXT NOT NULL,
    interface_id        TEXT NOT NULL,
    sim_ts_s            DOUBLE PRECISION NOT NULL,
    throughput_rx_bps   DOUBLE PRECISION,
    throughput_tx_bps   DOUBLE PRECISION,
    error_counters      JSONB,
    optical_power_tx_dbm DOUBLE PRECISION,
    optical_power_rx_dbm DOUBLE PRECISION,
    sample_interval_ms  INTEGER NOT NULL,            -- TC-72
    capability_tier     TEXT NOT NULL                -- §25.3, TC-71
        CHECK (capability_tier IN ('baseline','enhanced')),
    clock_class         TEXT NOT NULL CHECK (clock_class IN ('ptp','ntp','unqualified')),
    clock_class_demoted BOOLEAN NOT NULL DEFAULT FALSE,   -- TC-70
    scenario_run_id     UUID NOT NULL,
    PRIMARY KEY (id, observed_at)
) PARTITION BY RANGE (observed_at);

CREATE TABLE reservation (                            -- B-4
    reservation_id      TEXT PRIMARY KEY,
    site_id             TEXT NOT NULL,
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ NOT NULL,
    capacity_mw         DOUBLE PRECISION NOT NULL,
    price_per_mwh       NUMERIC(12,4) NOT NULL,
    firmness            TEXT NOT NULL CHECK (firmness IN ('firm','reserved','spot')),
    state               TEXT NOT NULL
        CHECK (state IN ('proposed','authorized','active','expired','cancelled')),
    authorized_by       TEXT REFERENCES principal(principal_id),
    recommendation_id   TEXT REFERENCES recommendation(recommendation_id)
);

CREATE TABLE asset_health (                           -- B-5
    asset_id            TEXT NOT NULL,
    observed_at_sim_s   DOUBLE PRECISION NOT NULL,
    runtime_hours       DOUBLE PRECISION NOT NULL,
    starts_count        INTEGER NOT NULL,
    measured_ramp_mw_s  DOUBLE PRECISION,
    configured_ramp_mw_s DOUBLE PRECISION NOT NULL,
    rerated_ramp_mw_s   DOUBLE PRECISION,            -- TC-58
    availability_state  TEXT NOT NULL
        CHECK (availability_state IN ('available','degraded','maintenance','out_of_service')),
    PRIMARY KEY (asset_id, observed_at_sim_s)
);
