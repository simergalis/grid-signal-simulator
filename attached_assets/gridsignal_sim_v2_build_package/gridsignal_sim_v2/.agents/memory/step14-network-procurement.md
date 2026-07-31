---
name: Step 14 — Network Telemetry + Procurement design
description: Architecture decisions, TC mapping, and TRAP notes for Steps O1/O2/O3 corrections and Step 14 (TC-47, TC-50–52, TC-69–74).
---

## O1 — Hardware in EvidenceWindow (§21.4 form)

**Rule:** deidentify() now accepts `hardware_profiles: dict[str, float]` (profile_id → rated_kw_per_unit).
Fleet size is OMITTED — combining wattage × node count reconstructs per-site draw, which §21.4 forbids.
Class indices (A, B, C …) are randomised per call via `random.Random()` (seeded from os.urandom) — NOT stable across runs.
`hardware_profile_ids: frozenset[str]` kept for backward compat (PII check only, no class entries generated).

**How to apply:** When adding hardware context to advisory calls, pass `hardware_profiles` not `hardware_profile_ids`.
The class mapping changes on every deidentify() call — do not cache or compare indices across evidence windows.

## O2 — Gate accept path

`gate.accept(proposal_id, *, reviewer_id="", accepted_at_sim_time=None)` — stores on Proposal fields.
gate.validate() is the entry point (not submit/enqueue). make_proposal() requires `created_at_sim_time`.
Accepting proposals does NOT alter dispatch — TC-48 proves this; the O2 test makes it concrete.

## O3 — temperature=0.0 docstring

Both Mistral and Anthropic backend methods now have explicit comments:
"temperature=0.0 reduces variance but does NOT make a hosted model deterministic or reproducible.
TC-48 holds because proposals are never actioned (architectural guarantee), not because model output is reproducible."

## Step 14 — Core files

- core/ingest.py       — shared §17.1-17.2: Deduplicator (900s window), Quarantine (TEXT not JSON), BaseIngestor
- core/network_telemetry.py — NetworkTelemetry + ClockClassModel + NetworkTelemetryIngestor + TC-74 enforcement
- core/procurement.py  — GridCapacity, NonFirmImportEffect, ReservationProposal, SyntheticPriceCurve
- core/corroboration.py — FabricCorroborator, CorroborationRecord, FabricFinding

## TC mapping

TC-47: NonFirmImportEffect.apply() — reserve_gap returned unchanged always.
TC-50: FabricCorroborator.ingest_telemetry() → FabricFinding (no SimulationState write).
TC-51: apply_checkpoint_start() → AUTHORITATIVE_START; fabric cannot override via try_corroborate_from_fabric().
TC-52: ReservationProposal.requires_confirmation is a property always returning True (not a field).
       "reservation" added to VALID_PROPOSAL_KINDS in advisory_gate.py.
TC-69: ClockClassModel.correlation_window_ms() = max(bound_a, bound_b) — looser wins.
TC-70: PTP + |skew| > PTP_SKEW_MAX_MS (2.0 ms) → effective_discipline = NTP.
TC-71: NetworkTelemetryIngestor(capability=BASELINE) — optical_monitoring_enabled=False, ingestion continues.
TC-72: optical_power outside [-40, +10] dBm → QUARANTINED with reason string containing "optical_power".
TC-73: FabricCorroborator.reconciliation_count never incremented by ingest_telemetry(); only advance_reconciliation_count().
TC-74: assert_not_in_dispatch_path() raises NetworkTelemetryDispatchError (TypeError subclass); non-conforming use not misconfiguration.

## TRAP: ReservationProposal.requires_confirmation

It is a @property returning True, not a dataclass field. Assigning to it raises AttributeError.
Do not try to unset it via tier logic or advisory gate.

## P1 correction (HardwareClassMap)

Old behavior: per-call random shuffle — each deidentify() call reshuffled class indices.
New behavior: HardwareClassMap created once at AgentRegistry init; passed through run_all() → maybe_run() → deidentify(hardware_class_map=).

Within session: stable (required for CalibrationAgent and reviewer correlation).
Across sessions: different RNG seed → different mapping (§21.4 unlinkability).

Reviewer resolution: `registry.hardware_class_map.resolve("profile_B")` → rated_kw_per_unit.
The rated_kw_per_unit is already on the wire entry — power reasoning needs no further resolution.
For SKU-level resolution, the operator reads the session map (stored alongside advisory session record).

## P2 clarification (accepted reservation is inert)

Accepting a ReservationProposal today: records reviewer_id + accepted_at_sim_time on the Proposal dataclass only.
No path from accepted proposal to GridCapacity or control plane.
ProcurementPage.tsx comment updated — "commits money" was wrong. Now: "records authorization intent only, pending the production effect path."
TC-52 governance gate (named reviewer + checkbox) is in place so the effect path can be wired without architectural change.

## TRAP: gate API

gate.validate(proposal) is the entry point — stores proposal AND validates bounds.
gate.accept(id) transitions to ACCEPTED.
There is no gate.submit() or gate.enqueue().
make_proposal() requires `created_at_sim_time` (positional, not keyword-only).

## Frontend additions (Step 15)

- ThermalCoolingPage.tsx — §19.6, read-only. Thermal headroom in MW + time-to-limit (both required). Per-zone utilisation bars. TC-55 inlet comfort band reference line (no dispatch interlock here).
- ScenarioPlannerPage.tsx — §19.1 Page 9, §18.5 FR-4.4. §21.2 cost model mirrors core/cost_model.py (client-side). Three cost streams: grid import, on-site gen (amortised capital vs duty cycle), storage RT. Commits nothing.

## Step 15 key decisions

TC-58: `reserve_contribution_mw_per_s(record)` → 0.0 for MAINTENANCE/FAILED; `effective_ramp_mw_per_s` for OPERATIONAL/DEGRADED.
TC-59: `validate_window()` iterates ALL ticks with sim_time in [start, end]. Empty forecast → vacuous accept.
TC-60: `proposed <= effective` → LOWER (no confirmation). `proposed > effective` → RAISE (requires_confirmation always True).
TC-75: `headroom_at_upper_bound = available - forecast_upper_bound`. Must be >= threshold. "No warning at current demand" is not sufficient.
TC-76: `gridSignal_connected=False` → returns baseline policy (adaptive_active=False). `baseline_ramp_cap_mw=0` raises ValueError at construction.
Cost model: duty_fraction = min(1.0, gen_mwh / (rated_mw × hours)). Capital = capital_per_mw_year × rated_mw × (hours/8760).

## Frontend additions (Step 14)

- NetworkTelemetryPage.tsx — §19.9, read-only, no controls (TC-74 by design)
- ProcurementPage.tsx — §19.8, authorization dialog with reviewer ID + checkbox (TC-52)
- App.tsx — four-tab nav: Overview / Proposals & Learning / Grid & Procurement / Network Telemetry
