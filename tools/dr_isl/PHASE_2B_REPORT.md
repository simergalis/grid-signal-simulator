# DR-2026-10-20-ISLAND-COLLAPSE — resumed Phase 2b

## Status and evidence qualification

Fixes implemented, tested and locally committed as `1713cd0ff01ebc0f8e11f581a149713677db2a45`. No push, publish or deployment was performed. Phase 3 and IMPL-ISL-12 were not started.

The original historical Phase-2 17-failure file did not survive /tmp loss. Section 2b.5 explicitly distinguishes the real-package full-suite result from a newly reconstructed 17-test HEAD control. It is not represented as reading the lost historical list or rerunning the entire historical suite.

Package prefix P used below: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`.

Earlier report preserved byte-for-byte as `tools/dr_isl/PHASE_2B_STOP1_REPORT.md:1–243`; SHA-256 `9f3ee62da9520c10222a00dbb2e91161ad64477678eeed77d68e6644dbfadda4`.

## 2b.0 — pre-change gate

### (a) Literal history 86ab0ef..starting HEAD

```text
dca40d0079f53e08c25967ca390dec462668f058 | 2026-10-21T08:59:47Z | Replit Agent <agent@replit.com> | Add phase 2b report to dr_isl tools

 tools/dr_isl/PHASE_2B_REPORT.md | 243 ++++++++++++++++++++++++++++++++++++++++
 1 file changed, 243 insertions(+)
94dcee7dd65c486848e32225139fb015e5990f3b | 2026-10-21T08:39:52Z | Replit Agent <agent@replit.com> | Add phase 1c report to tools dr_isl

 tools/dr_isl/PHASE_1C_REPORT.md | 2072 +++++++++++++++++++++++++++++++++++++++
 1 file changed, 2072 insertions(+)
```

Starting HEAD was dca40d0079f53e08c25967ca390dec462668f058, not 94dcee7: the intervening commit added only the prior stop report. The two commits listed above touch reports only; no application code, tests, scenarios or runner.

### (b) Direct-step study-harness baseline

Runner reconstruction: `/tmp/DR-ISL-phase2b/harness_gate.py:1–99`. The original Phase-1b /tmp runner was absent. This reconstruction calls `P/study_harness/executor.py:249–306` for expansion/probe and follows `:321–354` for arm preparation, demand replay and direct ctx.step(). Configured non-null kube seeds are preserved on this harness path. No RunManager-vs-harness investigation was performed.

```json
{
  "balance_failures": [],
  "collector_error": null,
  "dispatch_curtailment_mwh": 4.79477329394151,
  "exact_match": true,
  "expected": 4.79477329394151,
  "mode": "baseline",
  "physical_hash": "3aa4fdbb6691f70e407acc23b53a99ebc3c6241ce6126328ad9ba8e228fe760f",
  "ticks": 1440
}
```

```json
{
  "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
    "gt-hot-01": 9.233069128,
    "gt-hot-02": 7.435268298,
    "gt-spin-01": 16.83696342,
    "gt-spin-02": 16.810284673
  },
  "dispatch_curtailment_attributable_fuel_mmbtu": 50.315585518,
  "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
    "hot_standby_fuel_mmbtu": 0.0,
    "load_fuel_mmbtu": 114.574329409,
    "no_load_fuel_mmbtu": 1.47,
    "start_fuel_mmbtu": 0.0
  },
  "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
    "gt-hot-01": 18.101597222,
    "gt-hot-02": 14.117013889,
    "gt-spin-01": 41.971458333,
    "gt-spin-02": 41.854259965
  },
  "dispatch_curtailment_interval_exposure_fuel_mmbtu": 116.044329409,
  "dispatch_curtailment_mwh": 4.794773294
}
```

```json
{
  "balance_failures": [],
  "collector_error": null,
  "dispatch_curtailment_mwh": 0.3700526648755099,
  "exact_match": true,
  "expected": 0.3700526648755099,
  "mode": "informed",
  "physical_hash": "79ca32b9c8a465f45fc91c7e34137bd22fcacaec0b43fa99e15e6b57ea3bc86e",
  "ticks": 1440
}
```

```json
{
  "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
    "gt-hot-01": 0.664865971,
    "gt-hot-02": 0.566457396,
    "gt-spin-01": 1.149536383,
    "gt-spin-02": 1.080303822
  },
  "dispatch_curtailment_attributable_fuel_mmbtu": 3.461163572,
  "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
    "hot_standby_fuel_mmbtu": 0.0,
    "load_fuel_mmbtu": 17.81744453,
    "no_load_fuel_mmbtu": 0.166666667,
    "start_fuel_mmbtu": 0.0
  },
  "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
    "gt-hot-01": 3.594157223,
    "gt-hot-02": 3.080972222,
    "gt-spin-01": 5.897152778,
    "gt-spin-02": 5.411828974
  },
  "dispatch_curtailment_interval_exposure_fuel_mmbtu": 17.984111197,
  "dispatch_curtailment_mwh": 0.370052665
}
```

MetricsCollector.finalize rounds report metrics to nine decimals (`P/study_harness/metrics.py:504–519`). Exact gate equality above uses the same collector's unrounded curtailed_mwh accumulator, not the rounded display.

### (c) Catalogue baseline

```json
[
  {
    "failing_tick_count": 24,
    "failing_ticks": [
      61,
      62,
      63,
      64,
      65,
      66,
      67,
      68,
      69,
      70,
      71,
      72,
      211,
      212,
      213,
      214,
      215,
      216,
      217,
      218,
      219,
      220,
      221,
      222
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "physical_sha256": "a80a43bde260f51fb5f78a5f474b64a1c328452c6422e93446c2ce6e20a12716",
    "repetition": 1,
    "scenario_id": "scenario-equinix-sj-1",
    "spec_island_mode": false,
    "tick_count": 720,
    "tolerances_mw": [
      1.9913e-14
    ],
    "verification_modes": [
      "grid_tied_provisional"
    ]
  },
  {
    "failing_tick_count": 0,
    "failing_ticks": [],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "physical_sha256": "fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a",
    "repetition": 1,
    "scenario_id": "demo-islanded-ramp",
    "spec_island_mode": true,
    "tick_count": 2160,
    "tolerances_mw": [
      1.9913e-14
    ],
    "verification_modes": [
      "islanded_verified"
    ]
  },
  {
    "failing_tick_count": 0,
    "failing_ticks": [],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "physical_sha256": "51dfe89b51138d85930b01684c95c58d60d7dcd1ed0c36801657c9d41840ef52",
    "repetition": 1,
    "scenario_id": "S10_mit_supercloud_2021-08-11",
    "spec_island_mode": true,
    "tick_count": 17280,
    "tolerances_mw": [
      1.9913e-14
    ],
    "verification_modes": [
      "islanded_verified"
    ]
  },
  {
    "failing_tick_count": 0,
    "failing_ticks": [],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "physical_sha256": "006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a",
    "repetition": 1,
    "scenario_id": "scenario-turbine-01",
    "spec_island_mode": true,
    "tick_count": 720,
    "tolerances_mw": [
      1.9913e-14
    ],
    "verification_modes": [
      "islanded_verified"
    ]
  },
  {
    "failing_tick_count": 0,
    "failing_ticks": [],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "physical_sha256": "4e9c1a040eeaa4952600225cef71fa7ab8088419a916184bad09ba45bc8bc518",
    "repetition": 1,
    "scenario_id": "scenario-hybrid-ai-100mw-addendum-i",
    "spec_island_mode": true,
    "tick_count": 120,
    "tolerances_mw": [
      1.9913e-14
    ],
    "verification_modes": [
      "islanded_verified"
    ]
  },
  {
    "failing_tick_count": 0,
    "failing_ticks": [],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "physical_sha256": "565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b",
    "repetition": 1,
    "scenario_id": "scenario-100mw-fuel-cell-bess-diesel",
    "spec_island_mode": true,
    "tick_count": 252,
    "tolerances_mw": [
      1.9913e-14
    ],
    "verification_modes": [
      "islanded_verified"
    ]
  }
]
```

SJ-1 exact required hash equality passed. All six executions used `tools/dr_isl/baseline_runner.py` unchanged; runner file SHA-256: 12320f7c74c42406cc6eca862b9621621f733c2d9ad94e3ecb0c80652af6593a

## 2b.1 and 2b.2 — implementation and full diff

`P/core/simulation_core.py:3494–3508`: the shared shortfall producer now uses achieved public generation including permitted import for both modes; unserved is max(explicit shed, physical shortfall), bounded by demand. The existing served=demand−unserved producer remains shared.

`P/core/simulation_core.py:3503–3508`: one reconciliation caps the existing sink at non-negative achieved surplus after served-load reconciliation. The same value reaches physical ledger `:3563` and TickResult telemetry (literal hunk below; all other references preserved).

No policy/tuning constant was introduced. Zero in the reconciliation is the non-negative mathematical boundary, not a new configurable parameter. No scenario JSON, requested-demand, cap, dispatch, cost, reserve, commitment, frequency or protection edit appears in the literal commit diff.

```diff
commit 1713cd0ff01ebc0f8e11f581a149713677db2a45
Author:     Lloyd Spencer <146573701+simergalis@users.noreply.github.com>
AuthorDate: Wed Oct 21 10:50:47 2026 +0000
Commit:     Lloyd Spencer <146573701+simergalis@users.noreply.github.com>
CommitDate: Wed Oct 21 10:50:47 2026 +0000

    IMPL-ISL-10 + D7 (IMPL-ISL-11): reconcile curtailment after trips; capped grid-tied shortfall counts as unserved

diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
index 7e811a7..d253eb5 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -3485,21 +3485,27 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     _compute_inlet_temp_c = _T_AMBIENT_BASE_C + _cooling_fraction * _T_RISE_MAX_C
 
     # ── Phase 6: Load-side served/shed producers ───────────────────────────────
-    # The served/unserved split includes explicit UFLS/curtailment shedding and,
-    # for an islanded site, any remaining physical supply deficit. A power
+    # The served/unserved split includes explicit UFLS/curtailment shedding and
+    # any remaining physical supply deficit, including a capped grid import. A power
     # ceiling is not merely telemetry: demand above deliverable generation is
     # electrically unserved.
     # Per-subsystem shed is proportional to demand fraction because stage
     # definitions specify a block fraction of total demand only.
     _cumulative_shed_mw = state._cumulative_shed_mw  # monotonic run total
-    _islanded_supply_shortfall_mw = (
-        max(0.0, p_demand_mw - _p_gen_mw) if _islanded else 0.0
-    )
+    # DR D7 (IMPL-ISL-11), 78555831 / c0737fc: permitted import is already
+    # included in _p_generation_mw; use one physical shortfall rule in both modes.
+    _supply_shortfall_mw = max(0.0, p_demand_mw - _p_generation_mw)
     _p_unserved_mw = min(
         p_demand_mw,
-        max(_cumulative_shed_mw, _islanded_supply_shortfall_mw),
+        max(_cumulative_shed_mw, _supply_shortfall_mw),
     )
     _p_served_mw = p_demand_mw - _p_unserved_mw
+    # DR IMPL-ISL-10, 72aa49a / b74830d: the pre-trip surplus sink cannot
+    # exceed achieved surplus after supply and served-load reconciliation.
+    _p_dispatch_curtailed_mw = min(
+        _p_dispatch_curtailed_mw,
+        max(0.0, _p_generation_mw - _p_served_mw),
+    )
     # p_imbalance is the measured generation-versus-served-load channel.  An
     # explicit curtailment sink closes the physical ledger, but it must not
     # erase the surplus from the frequency/imbalance signal on the same tick.
@@ -3522,8 +3528,8 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     # _grid_exchange_mw is negative on import (balance_residual < 0 when local gen
     # < demand), so we pass −_grid_exchange_mw here to match the convention.
     #
-    # p_unserved_mw contains deliberate UFLS shed or an islanded physical
-    # generation deficit, whichever is larger.  In both cases it reduces served
+    # p_unserved_mw contains deliberate UFLS shed or a physical supply
+    # deficit after permitted import, whichever is larger. Both reduce served
     # load for D4: an anchor-reserved MW above the BESS bridge ceiling cannot be
     # reported as electrically served.
     # p_losses_mw defaults to 0.0 — the model does not represent losses.
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2b.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2b.py
new file mode 100644
index 0000000..b217212
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2b.py
@@ -0,0 +1,53 @@
+"""TC-ISL-15/16 — D7 and IMPL-ISL-10 accounting regressions."""
+import pytest
+
+from runtime.scenario_factory import build_run_context_from_spec
+from tests.test_forecast_path import _run_tick, _starting_signal
+from tests.test_grid_import_limit_scenario import _grid_only_tick
+from tests.test_addendum_g_stage3_option_c import _factory_tick
+
+
+def test_tc_isl_15a_capped_grid_shortfall_is_unserved():
+    tick = _grid_only_tick(10.0)
+    assert tick.p_demand_mw > 10.0
+    assert tick.grid_exchange_mw == pytest.approx(-10.0)
+    assert tick.p_unserved_mw == pytest.approx(tick.p_demand_mw - 10.0)
+    assert tick.p_served_mw == pytest.approx(10.0)
+    assert tick.physical_balance.passed is True
+
+
+def test_tc_isl_15b_uncapped_grid_is_unchanged():
+    tick = _grid_only_tick(None)
+    assert tick.p_unserved_mw == 0.0
+    assert tick.p_served_mw == tick.p_demand_mw
+    assert tick.p_generation_mw == pytest.approx(tick.p_demand_mw)
+    assert tick.physical_balance.passed is True
+
+
+def test_tc_isl_15c_islanded_shortfall_is_unchanged():
+    spec = {
+        "name": "tc-isl-15c", "island_mode": True,
+        "frequency_nominal_hz": 60.0, "power_factor": 0.85,
+        "turbine_units": [], "bess_units": [], "solar_rated_mw": 0.0,
+        "fuel_cell_enabled": False, "pue_base": 1.03,
+    }
+    state = build_run_context_from_spec("tc-isl-15c", spec).sim_state
+    state.apply_workload_signal(
+        _starting_signal(nodes=2000, ramp_s=1.0, timestamp=0.0), dt_lead_seconds=0.0
+    )
+    tick = _run_tick(state, sim_time=5.0, dt=5.0)
+    assert tick.p_demand_mw > 0.0
+    assert tick.p_generation_mw == 0.0
+    assert tick.p_unserved_mw == tick.p_demand_mw
+    assert tick.p_served_mw == 0.0
+    assert tick.physical_balance.passed is True
+
+
+def test_tc_isl_16_fc_rocof_trip_reconciles_pretrip_surplus():
+    # The unchanged Stage-3 fixture produces pre-trip FC output at its stable floor.
+    tick = _factory_tick(grid_forming=True, min_stable_frac=.5)
+    assert tick.fuel_cell_ride_through_trips[0]["reason"] == "rocof"
+    assert tick.fuel_cell_output_mw == 0.0
+    assert tick.p_dispatch_curtailed_mw == 0.0
+    assert tick.physical_balance.terms.p_curtailment_mw == 0.0
+    assert tick.physical_balance.passed is True
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_grid_import_limit_scenario.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_grid_import_limit_scenario.py
index 7828980..3350521 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_grid_import_limit_scenario.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_grid_import_limit_scenario.py
@@ -317,10 +317,19 @@ def test_sj1_three_overpeak_bursts_respect_supply_limits_and_recover() -> None:
             if start_s <= tick.sim_time_seconds < end_s
         ]
         assert peak_ticks
-        assert all(
-            tick.p_unserved_mw == pytest.approx(0.0, abs=1e-6)
-            for tick in peak_ticks
-        )
+        if start_s < 1800.0:
+            # DR D7 / 78555831: capped-grid physical shortfall is unserved.
+            assert all(
+                tick.p_unserved_mw == pytest.approx(
+                    max(0.0, tick.p_demand_mw - tick.p_generation_mw), abs=1e-6
+                )
+                for tick in peak_ticks
+            )
+        else:
+            assert all(
+                tick.p_unserved_mw == pytest.approx(0.0, abs=1e-6)
+                for tick in peak_ticks
+            )
         assert min(tick.grid_exchange_mw for tick in peak_ticks) >= -5.0 - 1e-6
 
         recovery_ticks = [
@@ -718,17 +727,10 @@ def test_grid_import_is_physically_capped_and_d4_remains_balanced() -> None:
     assert tick.p_demand_mw > 10.0
     assert tick.grid_exchange_mw == pytest.approx(-10.0, abs=1e-9)
     assert tick.frequency_forcing_mw < 0.0
-    # Shortfall is reported through p_imbalance_mw. p_unserved_mw remains
-    # explicit shed only and is zero until protection actually sheds load.
-    assert tick.d4_balance_defect_mw == pytest.approx(
-        tick.frequency_forcing_mw,
-        abs=1e-9,
-    )
-    assert tick.p_unserved_mw == pytest.approx(0.0, abs=1e-9)
-    assert tick.p_imbalance_mw == pytest.approx(
-        tick.frequency_forcing_mw,
-        abs=1e-9,
-    )
+    # DR D7 / 78555831: capped-grid shortfall reduces served load for D4.
+    assert tick.d4_balance_defect_mw == pytest.approx(0.0, abs=1e-9)
+    assert tick.p_unserved_mw == pytest.approx(tick.p_demand_mw - 10.0, abs=1e-9)
+    assert tick.p_imbalance_mw == pytest.approx(0.0, abs=1e-9)
     assert tick.p_generation_mw == pytest.approx(10.0, abs=1e-9)
 
 
diff --git a/tools/dr_isl/PHASE_2B_REPORT.md b/tools/dr_isl/PHASE_2B_STOP1_REPORT.md
similarity index 100%
rename from tools/dr_isl/PHASE_2B_REPORT.md
rename to tools/dr_isl/PHASE_2B_STOP1_REPORT.md
```

### Downstream consumers

# Downstream consumer inventory

Paths below are relative to the package root:
`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`.

“Changes” means a new capped-grid deficit tick such as SJ-1 ticks 61–72 and
211–222; unchanged physical scenario hashes establish no changes for the
other verified scenarios. This is not a claim that all possible inputs were tested.

| Consumer and source | Effect |
|---|---|
| `core/simulation_core.py:3494–3512` | One shared shortfall/served/unserved calculation; imbalance changes from negative shortfall to zero when all achieved supply serves load. |
| `core/simulation_core.py:3537–3565`, `core/power_balance.py:133–176` | D4 and physical ledger use corrected served/unserved; SJ-1 closes instead of failing. The balance evaluator and tolerance are unchanged. |
| `core/simulation_core.py:3588–3591` | Compute and cooling served/unserved allocations change proportionally; requested compute/cooling demand is not changed. |
| `core/simulation_core.py:3962–3968`, `core/models.py:1490–1496` | TickResult carries revised total and component accounting. No schema field added. |
| `runtime/turbine_commitment.py:36–77,1424–1450` | Unserved energy, peak and interval summaries increase for affected capped-grid ticks; these are recorded outcomes, not a dispatch-policy edit. |
| `runtime/run_manager.py:1957–1959` | Completed-run commitment unserved summary fields can change; sourced from the above summaries. |
| `study_harness/metrics.py:275–307,500–533` | Served/unserved MWh, peaks, intervals, per-day totals and energy closure consume corrected load accounting. Uneven study-arm metrics/hashes remain identical in measured runs. |
| `study_harness/executor.py:161–162` | Compact study ticks retain revised served/unserved values when the study input has a capped-grid deficit. |
| `runtime/run_manager.py:417–428,830–832` | UI/API tick payload has revised rounded served/unserved/component values and physical balance. |
| `runtime/run_manager.py:258–263,1100` | WebSocket/latest-REST cache and in-memory tick dictionaries use that same payload. |
| `runtime/persistence.py:92–126,1000–1003` | Full tick JSON persists revised accounting and authoritative balance. No database schema/migration change. Existing historical stored rows are not rewritten. |
| `api/routes/export.py:122–144` | CSV expansion of persisted tick JSON exports revised fields for newly recorded runs. Existing persisted runs retain old values. |
| `api/routes/ai.py:1800–1801` | Read-only AI formatted served/unserved numbers change; the existing “Explicitly shed load (UFLS or curtailment)” label is unchanged by this limited patch. |
| `run_and_monitor.py:55–60`, `monitor_live.py:58–67,130–131,214–215`, `monitor_extended.py:88–97` | Monitoring consumers print revised totals/components. |
| `runtime/run_manager.py:3158–3176` | Physical-balance error emission no longer emits the 24 SJ-1 violations, because the authoritative balance now passes. |
| `core/power_balance.py:104–109` | Balance breakdown's unserved and served-plus-unserved identity reflect corrected labels. |

Literal field-name search evidence is in
`/tmp/DR-ISL-phase2b/consumers_all.txt` and `consumer_search.txt`.
No frontend implementation file was present under the package's
`frontend/src` at this checkout (the directory contains only empty
`subsystem` descendants); no frontend page implementation is claimed audited.
UI payload wiring above is backend evidence, not a browser test.
No direct served/unserved alert-rule field consumer was found in the
runtime/core field-name search; physical-balance error emission is listed
separately. No claim is made that indirect generic alert behavior cannot change.

### Literal complete direct field-name consumer search

```text
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py:161:        "p_served_mw",
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py:162:        "p_unserved_mw",
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/run_and_monitor.py:55:    p_served  = g("p_served_mw")
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/run_and_monitor.py:58:    p_unserv  = g("p_unserved_mw")  # explicit UFLS/curtailment shed only
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/run_and_monitor.py:59:    p_comp_u  = g("p_compute_unserved_mw")
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/run_and_monitor.py:60:    p_cool_u  = g("p_cooling_unserved_mw")
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/metrics.py:275:        unserved = max(0.0, _number(_get(tick, "p_unserved_mw")))
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/metrics.py:276:        served = max(0.0, _number(_get(tick, "p_served_mw")))
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/monitor_live.py:58:    p_served = t.get("p_served_mw")
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/monitor_live.py:59:    p_unserv = t.get("p_unserved_mw")  # explicit UFLS/curtailment shed only
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/monitor_live.py:66:    p_comp_u = t.get("p_compute_unserved_mw")
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/monitor_live.py:67:    p_cool_u = t.get("p_cooling_unserved_mw")
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/monitor_live.py:130:        ("p_served_mw",    p_served),
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/monitor_live.py:131:        ("p_unserved_mw",  p_unserv),
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/monitor_live.py:214:        f" {mw(t.get('p_served_mw'))}"
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/monitor_live.py:215:        f" {mw(t.get('p_unserved_mw'))}"
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/export.py:23:                 contingency_coverage, island_collapsed, p_served_mw, p_imbalance_mw …
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3498:    _p_unserved_mw = min(
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3502:    _p_served_mw = p_demand_mw - _p_unserved_mw
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3507:        max(0.0, _p_generation_mw - _p_served_mw),
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3512:    _p_imbalance_mw = _p_generation_mw - _p_served_mw
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3531:    # p_unserved_mw contains deliberate UFLS shed or a physical supply
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3539:        p_unserved_mw=_p_unserved_mw,
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3554:            p_unserved_mw=_p_unserved_mw,
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3555:            p_served_mw=_p_served_mw,
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3588:    _p_compute_served_mw   = p_compute_demand_mw - _p_unserved_mw * _compute_demand_frac
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3589:    _p_compute_unserved_mw = _p_unserved_mw * _compute_demand_frac
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3590:    _p_cooling_served_mw   = p_cooling_demand_mw - _p_unserved_mw * _cooling_demand_frac
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3591:    _p_cooling_unserved_mw = _p_unserved_mw * _cooling_demand_frac
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3962:        p_served_mw=_p_served_mw,
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3963:        p_unserved_mw=_p_unserved_mw,
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3966:        p_compute_unserved_mw=_p_compute_unserved_mw,
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3968:        p_cooling_unserved_mw=_p_cooling_unserved_mw,
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/monitor_extended.py:88:    p_served = t.get("p_served_mw")
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/monitor_extended.py:89:    p_unserv = t.get("p_unserved_mw")  # explicit UFLS/curtailment shed only
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/monitor_extended.py:96:    p_comp_u = t.get("p_compute_unserved_mw")
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/monitor_extended.py:97:    p_cool_u = t.get("p_cooling_unserved_mw")
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/ai.py:1800:        _fmt("p_served_mw",            "Served load")
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/ai.py:1801:        _fmt("p_unserved_mw",          "Explicitly shed load (UFLS or curtailment)")
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py:1483:    # p_served_mw:   demand actually served = p_demand - cumulative_shed_mw.
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py:1485:    # p_unserved_mw: load shed so far = p_demand - p_served_mw = cumulative_shed_mw.
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py:1486:    # p_imbalance_mw: generation vs served = p_generation - p_served_mw.
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py:1490:    p_served_mw:           Optional[float] = None
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py:1491:    p_unserved_mw:         Optional[float] = None
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py:1494:    p_compute_unserved_mw: Optional[float] = None
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py:1496:    p_cooling_unserved_mw: Optional[float] = None
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py:40:    p_unserved_mw: float = 0.0      # load shed by UFLS or curtailment
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py:48:    p_served_mw: float | None = None
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py:104:            "unserved_load_mw": t.p_unserved_mw,
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py:109:                self.served_mw + t.p_unserved_mw + t.p_losses_mw
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py:140:    if terms.p_served_mw is not None:
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py:141:        return terms.p_served_mw
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_balance.py:142:    return terms.p_demand_mw - terms.p_unserved_mw
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py:39:    The simulator reports ``p_unserved_mw`` at interval end.  Energy is therefore
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py:50:            tick.get("p_unserved_mw", 0.0)
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py:52:            else getattr(tick, "p_unserved_mw", 0.0)
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py:1427:        unserved_mw = max(0.0, float(getattr(result, "p_unserved_mw", 0.0) or 0.0))
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py:412:        # p_served_mw / p_unserved_mw / p_generation_mw / p_imbalance_mw:
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py:417:        # Phase 6: p_compute_served_mw / p_compute_unserved_mw — wired from evaluate_tick().
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py:419:        "p_compute_unserved_mw": round(tick.p_compute_unserved_mw, 4) if tick.p_compute_unserved_mw is not None else None,
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py:421:        # Phase 6: p_cooling_served_mw / p_cooling_unserved_mw — wired from evaluate_tick().
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py:423:        "p_cooling_unserved_mw": round(tick.p_cooling_unserved_mw, 4) if tick.p_cooling_unserved_mw is not None else None,
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py:425:        # Phase 6: p_unserved_mw is explicit UFLS/curtailment shed. p_served_mw
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py:427:        "p_served_mw":           round(tick.p_served_mw, 4) if tick.p_served_mw is not None else None,
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py:428:        "p_unserved_mw":         round(tick.p_unserved_mw, 4) if tick.p_unserved_mw is not None else None,
```

## 2b.3 — tests

TC-ID collision search before addition found no TC-ISL-15 or TC-ISL-16 in the tests. IDs used: TC-ISL-15a/b/c and TC-ISL-16.

New tests: `P/tests/test_dr_isl_phase2b.py:10–53`. Only the two authorized old tests were edited, at `P/tests/test_grid_import_limit_scenario.py:314–345,724–734` (exact changed hunks are above). Addendum G tests were not edited.

Initial targeted execution: 80 passed and one new-fixture failure (missing required frequency_nominal_hz). The fixture was corrected, not production logic. Its isolated rerun passed, and the final real-package full suite includes all four new tests passing. The first target output is retained without relabeling it as an all-pass run:

```text
..F..................................................................... [ 88%]
.........                                                                [100%]
=================================== FAILURES ===================================
_______________ test_tc_isl_15c_islanded_shortfall_is_unchanged ________________

    def test_tc_isl_15c_islanded_shortfall_is_unchanged():
        spec = {
            "name": "tc-isl-15c", "island_mode": True,
            "turbine_units": [], "bess_units": [], "solar_rated_mw": 0.0,
            "fuel_cell_enabled": False, "pue_base": 1.03,
        }
>       state = build_run_context_from_spec("tc-isl-15c", spec).sim_state
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_dr_isl_phase2b.py:33: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

run_id = 'tc-isl-15c'
spec_data = {'name': 'tc-isl-15c', 'island_mode': True, 'turbine_units': [], 'bess_units': [], ...}
playback_speed = 0.0

    def build_run_context_from_spec(
        run_id: str,
        spec_data: dict,
        playback_speed: float = 0.0,
    ) -> RunContext:
        """Build a RunContext from a scenario spec dictionary (JSON-round-trip safe).
    
        ``spec_data`` is the plain-Python form of a serialised ScenarioSpec —
        i.e. ``json.loads(record.spec_json)`` or ``spec.model_dump()``.
        All dicts, lists, and scalars; no Pydantic models.
    
        Design constraints:
        - This function must NOT import from api/ (runtime/ → api/ is forbidden
          by §21.1 plane-separation).  The caller (api/routes/runs.py) is
          responsible for validating the spec via Pydantic and serialising it;
          this function only reads a plain dict.
        - WorkloadClass is read from each scripted event, defaulting to TRAINING
          for backward compatibility with existing scenario specs.
        - An empty workload_events list is valid (idle run or TC-33 compute
          where the job starts at t>0).
        - SOLAR_STEP events are forwarded with event_type=WorkloadEventType.SOLAR_STEP;
          SimulationState.apply_workload_signal's early-return handles them.
    
        Step 9 will swap ScenarioRecord.spec_json reads from in-memory to
        SQLAlchemy while calling this function identically.
        """
        spec_data = expand_phase2b_reference_spec(spec_data)
        validate_fuel_cell_source_consistency(spec_data)
    
        # ── Site configuration ────────────────────────────────────────────────
        island = (
            IslandMode.ISLANDED
            if spec_data.get("island_mode", True)
            else IslandMode.GRID_TIE
        )
        # A1: frequency_nominal_hz and power_factor are REQUIRED on SiteConfig (no default).
        # ScenarioSpec guarantees both via schema defaults (60.0 / 0.85), so these
        # raises fire only when a raw dict without the fields is passed directly.
        _freq_raw = spec_data.get("frequency_nominal_hz")
        if _freq_raw is None:
>           raise ValueError(
                f"scenario spec for run '{run_id}' is missing 'frequency_nominal_hz'. "
                "Set it explicitly: 60.0 for WECC/ERCOT (North America), 50.0 for EU/APAC."
            )
E           ValueError: scenario spec for run 'tc-isl-15c' is missing 'frequency_nominal_hz'. Set it explicitly: 60.0 for WECC/ERCOT (North America), 50.0 for EU/APAC.

runtime/scenario_factory.py:647: ValueError
=========================== short test summary info ============================
FAILED tests/test_dr_isl_phase2b.py::test_tc_isl_15c_islanded_shortfall_is_unchanged
1 failed, 80 passed in 17.18s
```

Final full-suite failing-node set below excludes every new TC test, both authorized stale-test updates and both unchanged Stage-3 trip tests. The unchanged Addendum G test files all passed in the targeted run.

TC-ISL-16's passing assertions: ROCOF trip reason `rocof`, FC output `0.0`, tick curtailment `0.0`, ledger curtailment `0.0`, physical_balance.passed `True`.

## 2b.4 — paired post-fix scenario runs

| Scenario | ticks rep1/rep2 | baseline physical hash | post hash (both repetitions) | identical to baseline | balance failures rep1/rep2 |

|---|---|---|---|---|---|

| scenario-equinix-sj-1 | 720/720 | a80a43bde260f51fb5f78a5f474b64a1c328452c6422e93446c2ce6e20a12716 | 328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84 | False | 0/0 |

| demo-islanded-ramp | 2160/2160 | fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a | fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a | True | 0/0 |

| S10_mit_supercloud_2021-08-11 | 17280/17280 | 51dfe89b51138d85930b01684c95c58d60d7dcd1ed0c36801657c9d41840ef52 | 51dfe89b51138d85930b01684c95c58d60d7dcd1ed0c36801657c9d41840ef52 | True | 0/0 |

| scenario-turbine-01 | 720/720 | 006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a | 006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a | True | 0/0 |

| scenario-hybrid-ai-100mw-addendum-i | 120/120 | 4e9c1a040eeaa4952600225cef71fa7ab8088419a916184bad09ba45bc8bc518 | 4e9c1a040eeaa4952600225cef71fa7ab8088419a916184bad09ba45bc8bc518 | True | 0/0 |

| scenario-100mw-fuel-cell-bess-diesel | 252/252 | 565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b | 565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b | True | 0/0 |

SJ-1 totals and permitted-delta gate:

```json
{
  "burst1_mwh": 0.1582652309055414,
  "burst2_mwh": 0.0940062955559732,
  "invalid": [],
  "repeatable": true,
  "unserved_mwh": 0.2522715264615146,
  "unserved_per_tick_mwh": {
    "211": 0.0078430743750553,
    "212": 0.007845324524200158,
    "213": 0.0078470769421162,
    "214": 0.0078484417265615,
    "215": 0.007849504621756213,
    "216": 0.007850332405366168,
    "217": 0.007850977083889828,
    "218": 0.007851479160028872,
    "219": 0.007851870177319123,
    "220": 0.007852174701890964,
    "221": 0.007757927673009392,
    "222": 0.00775811216477948,
    "61": 0.0140736586082417,
    "62": 0.013958410808099092,
    "63": 0.013837933617638458,
    "64": 0.013713383773903172,
    "65": 0.013585662144608416,
    "66": 0.013072448793219652,
    "67": 0.012937695080649646,
    "68": 0.012802026670316035,
    "69": 0.01266564589264787,
    "70": 0.012614818492450188,
    "71": 0.012544511959912451,
    "72": 0.012459035063854717
  }
}
```

Reference burst values 0.1583/0.0940 MWh agree after rounding; total is 0.2522715264615146 MWh. Exactly 24 ticks differ. No physical change occurs outside ticks 61–72 / 211–222. Requested demand, source output, SoC, PCC exchange, frequency, and curtailment remain unchanged; the accounting fields listed below change.

### Every SJ-1 changed physical field, per tick, before → after

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -10.133034197934023
    },
    "p_compute_served_mw": {
      "after": 51.63211968915246,
      "before": 61.48503936
    },
    "p_compute_unserved_mw": {
      "after": 9.85291967084754,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.4678803108475549,
      "before": 1.7479948379340389
    },
    "p_cooling_unserved_mw": {
      "after": 0.2801145270864839,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -10.133034197934023
    },
    "p_served_mw": {
      "after": 53.100000000000016,
      "before": 63.23303419793404
    },
    "p_unserved_mw": {
      "after": 10.133034197934023,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -10.133034197934023
    },
    "physical_balance.served_mw": {
      "after": 53.100000000000016,
      "before": 63.23303419793404
    },
    "physical_balance.terms.p_served_mw": {
      "after": 53.100000000000016,
      "before": 63.23303419793404
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 10.133034197934023,
      "before": 0.0
    }
  },
  "tick": 61
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -10.050055781831347
    },
    "p_compute_served_mw": {
      "after": 51.71543413708103,
      "before": 61.48503936
    },
    "p_compute_unserved_mw": {
      "after": 9.76960522291897,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.4845658629189846,
      "before": 1.7650164218313602
    },
    "p_cooling_unserved_mw": {
      "after": 0.2804505589123756,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -10.050055781831347
    },
    "p_served_mw": {
      "after": 53.20000000000002,
      "before": 63.250055781831364
    },
    "p_unserved_mw": {
      "after": 10.050055781831347,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -10.050055781831347
    },
    "physical_balance.served_mw": {
      "after": 53.20000000000002,
      "before": 63.250055781831364
    },
    "physical_balance.terms.p_served_mw": {
      "after": 53.20000000000002,
      "before": 63.250055781831364
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 10.050055781831347,
      "before": 0.0
    }
  },
  "tick": 62
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -9.96331220469969
    },
    "p_compute_served_mw": {
      "after": 51.80178659132153,
      "before": 61.48503936
    },
    "p_compute_unserved_mw": {
      "after": 9.68325276867847,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.498213408678488,
      "before": 1.7782728446997094
    },
    "p_cooling_unserved_mw": {
      "after": 0.28005943602122135,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -9.96331220469969
    },
    "p_served_mw": {
      "after": 53.30000000000002,
      "before": 63.26331220469971
    },
    "p_unserved_mw": {
      "after": 9.96331220469969,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -9.96331220469969
    },
    "physical_balance.served_mw": {
      "after": 53.30000000000002,
      "before": 63.26331220469971
    },
    "physical_balance.terms.p_served_mw": {
      "after": 53.30000000000002,
      "before": 63.26331220469971
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 9.96331220469969,
      "before": 0.0
    }
  },
  "tick": 63
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -9.873636317210284
    },
    "p_compute_served_mw": {
      "after": 51.890507530874274,
      "before": 61.48503936
    },
    "p_compute_unserved_mw": {
      "after": 9.594531829125726,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.5094924691257476,
      "before": 1.7885969572103058
    },
    "p_cooling_unserved_mw": {
      "after": 0.27910448808455807,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -9.873636317210284
    },
    "p_served_mw": {
      "after": 53.40000000000002,
      "before": 63.273636317210304
    },
    "p_unserved_mw": {
      "after": 9.873636317210284,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -9.873636317210284
    },
    "physical_balance.served_mw": {
      "after": 53.40000000000002,
      "before": 63.273636317210304
    },
    "physical_balance.terms.p_served_mw": {
      "after": 53.40000000000002,
      "before": 63.273636317210304
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 9.873636317210284,
      "before": 0.0
    }
  },
  "tick": 64
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -9.781676744118059
    },
    "p_compute_served_mw": {
      "after": 51.98107532866139,
      "before": 61.48503936
    },
    "p_compute_unserved_mw": {
      "after": 9.503964031338613,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.5189246713386315,
      "before": 1.7966373841180754
    },
    "p_cooling_unserved_mw": {
      "after": 0.277712712779444,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -9.781676744118059
    },
    "p_served_mw": {
      "after": 53.50000000000002,
      "before": 63.28167674411808
    },
    "p_unserved_mw": {
      "after": 9.781676744118059,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -9.781676744118059
    },
    "physical_balance.served_mw": {
      "after": 53.50000000000002,
      "before": 63.28167674411808
    },
    "physical_balance.terms.p_served_mw": {
      "after": 53.50000000000002,
      "before": 63.28167674411808
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 9.781676744118059,
      "before": 0.0
    }
  },
  "tick": 65
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -9.412163131118149
    },
    "p_compute_served_mw": {
      "after": 52.300983586905154,
      "before": 61.48503936
    },
    "p_compute_unserved_mw": {
      "after": 9.18405577309485,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.2990164130948723,
      "before": 1.5271237711181724
    },
    "p_cooling_unserved_mw": {
      "after": 0.22810735802330026,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -9.412163131118149
    },
    "p_served_mw": {
      "after": 53.60000000000002,
      "before": 63.01216313111817
    },
    "p_unserved_mw": {
      "after": 9.412163131118149,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -9.412163131118149
    },
    "physical_balance.served_mw": {
      "after": 53.60000000000002,
      "before": 63.01216313111817
    },
    "physical_balance.terms.p_served_mw": {
      "after": 53.60000000000002,
      "before": 63.01216313111817
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 9.412163131118149,
      "before": 0.0
    }
  },
  "tick": 66
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -9.315140458067745
    },
    "p_compute_served_mw": {
      "after": 52.39608433197235,
      "before": 61.48503936
    },
    "p_compute_unserved_mw": {
      "after": 9.088955028027652,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.303915668027674,
      "before": 1.5301010980677672
    },
    "p_cooling_unserved_mw": {
      "after": 0.22618543004009328,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -9.315140458067745
    },
    "p_served_mw": {
      "after": 53.700000000000024,
      "before": 63.01514045806777
    },
    "p_unserved_mw": {
      "after": 9.315140458067745,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -9.315140458067745
    },
    "physical_balance.served_mw": {
      "after": 53.700000000000024,
      "before": 63.01514045806777
    },
    "physical_balance.terms.p_served_mw": {
      "after": 53.700000000000024,
      "before": 63.01514045806777
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 9.315140458067745,
      "before": 0.0
    }
  },
  "tick": 67
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -9.217459202627545
    },
    "p_compute_served_mw": {
      "after": 52.4917246652508,
      "before": 61.48503936
    },
    "p_compute_unserved_mw": {
      "after": 8.993314694749202,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.3082753347492273,
      "before": 1.532419842627571
    },
    "p_cooling_unserved_mw": {
      "after": 0.2241445078783437,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -9.217459202627545
    },
    "p_served_mw": {
      "after": 53.800000000000026,
      "before": 63.01745920262757
    },
    "p_unserved_mw": {
      "after": 9.217459202627545,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -9.217459202627545
    },
    "physical_balance.served_mw": {
      "after": 53.800000000000026,
      "before": 63.01745920262757
    },
    "physical_balance.terms.p_served_mw": {
      "after": 53.800000000000026,
      "before": 63.01745920262757
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 9.217459202627545,
      "before": 0.0
    }
  },
  "tick": 68
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -9.119265042706466
    },
    "p_compute_served_mw": {
      "after": 52.587785961295516,
      "before": 61.48503936
    },
    "p_compute_unserved_mw": {
      "after": 8.897253398704486,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.3122140387045094,
      "before": 1.5342256827064888
    },
    "p_cooling_unserved_mw": {
      "after": 0.2220116440019795,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -9.119265042706466
    },
    "p_served_mw": {
      "after": 53.90000000000003,
      "before": 63.01926504270649
    },
    "p_unserved_mw": {
      "after": 9.119265042706466,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -9.119265042706466
    },
    "physical_balance.served_mw": {
      "after": 53.90000000000003,
      "before": 63.01926504270649
    },
    "physical_balance.terms.p_served_mw": {
      "after": 53.90000000000003,
      "before": 63.01926504270649
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 9.119265042706466,
      "before": 0.0
    }
  },
  "tick": 69
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -9.082669314564136
    },
    "p_compute_served_mw": {
      "after": 52.63239747962686,
      "before": 61.48503936
    },
    "p_compute_unserved_mw": {
      "after": 8.852641880373138,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.3676025203731652,
      "before": 1.5976299545641637
    },
    "p_cooling_unserved_mw": {
      "after": 0.23002743419099841,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -9.082669314564136
    },
    "p_served_mw": {
      "after": 54.00000000000003,
      "before": 63.082669314564164
    },
    "p_unserved_mw": {
      "after": 9.082669314564136,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -9.082669314564136
    },
    "physical_balance.served_mw": {
      "after": 54.00000000000003,
      "before": 63.082669314564164
    },
    "physical_balance.terms.p_served_mw": {
      "after": 54.00000000000003,
      "before": 63.082669314564164
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 9.082669314564136,
      "before": 0.0
    }
  },
  "tick": 70
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -9.032048611136965
    },
    "p_compute_served_mw": {
      "after": 52.68862174685092,
      "before": 61.48503936
    },
    "p_compute_unserved_mw": {
      "after": 8.796417613149083,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.4113782531491126,
      "before": 1.6470092511369934
    },
    "p_cooling_unserved_mw": {
      "after": 0.23563099798788079,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -9.032048611136965
    },
    "p_served_mw": {
      "after": 54.10000000000003,
      "before": 63.132048611136995
    },
    "p_unserved_mw": {
      "after": 9.032048611136965,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -9.032048611136965
    },
    "physical_balance.served_mw": {
      "after": 54.10000000000003,
      "before": 63.132048611136995
    },
    "physical_balance.terms.p_served_mw": {
      "after": 54.10000000000003,
      "before": 63.132048611136995
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 9.032048611136965,
      "before": 0.0
    }
  },
  "tick": 71
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -8.970505245975396
    },
    "p_compute_served_mw": {
      "after": 52.7538781007979,
      "before": 61.48503936
    },
    "p_compute_unserved_mw": {
      "after": 8.731161259202102,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.4461218992021327,
      "before": 1.6854658859754283
    },
    "p_cooling_unserved_mw": {
      "after": 0.23934398677329569,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -8.970505245975396
    },
    "p_served_mw": {
      "after": 54.20000000000003,
      "before": 63.17050524597543
    },
    "p_unserved_mw": {
      "after": 8.970505245975396,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -8.970505245975396
    },
    "physical_balance.served_mw": {
      "after": 54.20000000000003,
      "before": 63.17050524597543
    },
    "physical_balance.terms.p_served_mw": {
      "after": 54.20000000000003,
      "before": 63.17050524597543
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 8.970505245975396,
      "before": 0.0
    }
  },
  "tick": 72
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -5.647013550039816
    },
    "p_compute_served_mw": {
      "after": 57.65684334597857,
      "before": 63.17530056
    },
    "p_compute_unserved_mw": {
      "after": 5.518457214021423,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.3431566540214286,
      "before": 1.471712990039821
    },
    "p_cooling_unserved_mw": {
      "after": 0.12855633601839234,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -5.647013550039816
    },
    "p_served_mw": {
      "after": 59.0,
      "before": 64.64701355003982
    },
    "p_unserved_mw": {
      "after": 5.647013550039816,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -5.647013550039816
    },
    "physical_balance.served_mw": {
      "after": 59.0,
      "before": 64.64701355003982
    },
    "physical_balance.terms.p_served_mw": {
      "after": 59.0,
      "before": 64.64701355003982
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 5.647013550039816,
      "before": 0.0
    }
  },
  "tick": 211
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -5.648633657424114
    },
    "p_compute_served_mw": {
      "after": 57.655398454224866,
      "before": 63.17530056
    },
    "p_compute_unserved_mw": {
      "after": 5.519902105775132,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.344601545775139,
      "before": 1.473333097424121
    },
    "p_cooling_unserved_mw": {
      "after": 0.12873155164898203,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -5.648633657424114
    },
    "p_served_mw": {
      "after": 59.0,
      "before": 64.64863365742411
    },
    "p_unserved_mw": {
      "after": 5.648633657424114,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -5.648633657424114
    },
    "physical_balance.served_mw": {
      "after": 59.0,
      "before": 64.64863365742411
    },
    "physical_balance.terms.p_served_mw": {
      "after": 59.0,
      "before": 64.64863365742411
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 5.648633657424114,
      "before": 0.0
    }
  },
  "tick": 212
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -5.649895398323665
    },
    "p_compute_served_mw": {
      "after": 57.65427322155648,
      "before": 63.17530056
    },
    "p_compute_unserved_mw": {
      "after": 5.521027338443513,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.345726778443521,
      "before": 1.474594838323673
    },
    "p_cooling_unserved_mw": {
      "after": 0.12886805988015218,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -5.649895398323665
    },
    "p_served_mw": {
      "after": 59.0,
      "before": 64.64989539832366
    },
    "p_unserved_mw": {
      "after": 5.649895398323665,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -5.649895398323665
    },
    "physical_balance.served_mw": {
      "after": 59.0,
      "before": 64.64989539832366
    },
    "physical_balance.terms.p_served_mw": {
      "after": 59.0,
      "before": 64.64989539832366
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 5.649895398323665,
      "before": 0.0
    }
  },
  "tick": 213
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -5.65087804312428
    },
    "p_compute_served_mw": {
      "after": 57.653396919895485,
      "before": 63.17530056
    },
    "p_compute_unserved_mw": {
      "after": 5.521903640104514,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.346603080104513,
      "before": 1.4755774831242778
    },
    "p_cooling_unserved_mw": {
      "after": 0.12897440301976473,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -5.65087804312428
    },
    "p_served_mw": {
      "after": 59.0,
      "before": 64.65087804312428
    },
    "p_unserved_mw": {
      "after": 5.65087804312428,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -5.65087804312428
    },
    "physical_balance.served_mw": {
      "after": 59.0,
      "before": 64.65087804312428
    },
    "physical_balance.terms.p_served_mw": {
      "after": 59.0,
      "before": 64.65087804312428
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 5.65087804312428,
      "before": 0.0
    }
  },
  "tick": 214
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -5.651643327664473
    },
    "p_compute_served_mw": {
      "after": 57.65271447392688,
      "before": 63.17530056
    },
    "p_compute_unserved_mw": {
      "after": 5.522586086073116,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.3472855260731134,
      "before": 1.4763427676644698
    },
    "p_cooling_unserved_mw": {
      "after": 0.12905724159135645,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -5.651643327664473
    },
    "p_served_mw": {
      "after": 59.0,
      "before": 64.65164332766447
    },
    "p_unserved_mw": {
      "after": 5.651643327664473,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -5.651643327664473
    },
    "physical_balance.served_mw": {
      "after": 59.0,
      "before": 64.65164332766447
    },
    "physical_balance.terms.p_served_mw": {
      "after": 59.0,
      "before": 64.65164332766447
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 5.651643327664473,
      "before": 0.0
    }
  },
  "tick": 215
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -5.65223933186364
    },
    "p_compute_served_mw": {
      "after": 57.65218299566294,
      "before": 63.17530056
    },
    "p_compute_unserved_mw": {
      "after": 5.5231175643370545,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.3478170043370583,
      "before": 1.4769387718636438
    },
    "p_cooling_unserved_mw": {
      "after": 0.12912176752658555,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -5.65223933186364
    },
    "p_served_mw": {
      "after": 59.0,
      "before": 64.65223933186364
    },
    "p_unserved_mw": {
      "after": 5.65223933186364,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -5.65223933186364
    },
    "physical_balance.served_mw": {
      "after": 59.0,
      "before": 64.65223933186364
    },
    "physical_balance.terms.p_served_mw": {
      "after": 59.0,
      "before": 64.65223933186364
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 5.65223933186364,
      "before": 0.0
    }
  },
  "tick": 216
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -5.652703500400676
    },
    "p_compute_served_mw": {
      "after": 57.651769086762165,
      "before": 63.17530056
    },
    "p_compute_unserved_mw": {
      "after": 5.5235314732378304,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.348230913237829,
      "before": 1.4774029404006743
    },
    "p_cooling_unserved_mw": {
      "after": 0.12917202716284537,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -5.652703500400676
    },
    "p_served_mw": {
      "after": 59.0,
      "before": 64.65270350040068
    },
    "p_unserved_mw": {
      "after": 5.652703500400676,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -5.652703500400676
    },
    "physical_balance.served_mw": {
      "after": 59.0,
      "before": 64.65270350040068
    },
    "physical_balance.terms.p_served_mw": {
      "after": 59.0,
      "before": 64.65270350040068
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 5.652703500400676,
      "before": 0.0
    }
  },
  "tick": 217
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -5.653064995220788
    },
    "p_compute_served_mw": {
      "after": 57.65144673830279,
      "before": 63.17530056
    },
    "p_compute_unserved_mw": {
      "after": 5.523853821697207,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.3485532616972091,
      "before": 1.4777644352207906
    },
    "p_cooling_unserved_mw": {
      "after": 0.12921117352358155,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -5.653064995220788
    },
    "p_served_mw": {
      "after": 59.0,
      "before": 64.65306499522079
    },
    "p_unserved_mw": {
      "after": 5.653064995220788,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -5.653064995220788
    },
    "physical_balance.served_mw": {
      "after": 59.0,
      "before": 64.65306499522079
    },
    "physical_balance.terms.p_served_mw": {
      "after": 59.0,
      "before": 64.65306499522079
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 5.653064995220788,
      "before": 0.0
    }
  },
  "tick": 218
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -5.653346527669768
    },
    "p_compute_served_mw": {
      "after": 57.65119569556704,
      "before": 63.17530056
    },
    "p_compute_unserved_mw": {
      "after": 5.524104864432953,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.3488043044329583,
      "before": 1.4780459676697737
    },
    "p_cooling_unserved_mw": {
      "after": 0.1292416632368153,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -5.653346527669768
    },
    "p_served_mw": {
      "after": 59.0,
      "before": 64.65334652766977
    },
    "p_unserved_mw": {
      "after": 5.653346527669768,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -5.653346527669768
    },
    "physical_balance.served_mw": {
      "after": 59.0,
      "before": 64.65334652766977
    },
    "physical_balance.terms.p_served_mw": {
      "after": 59.0,
      "before": 64.65334652766977
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 5.653346527669768,
      "before": 0.0
    }
  },
  "tick": 219
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -5.653565785361494
    },
    "p_compute_served_mw": {
      "after": 57.65100018480225,
      "before": 63.17530056
    },
    "p_compute_unserved_mw": {
      "after": 5.524300375197749,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.3489998151977556,
      "before": 1.4782652253615014
    },
    "p_cooling_unserved_mw": {
      "after": 0.1292654101637459,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -5.653565785361494
    },
    "p_served_mw": {
      "after": 59.0,
      "before": 64.6535657853615
    },
    "p_unserved_mw": {
      "after": 5.653565785361494,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -5.653565785361494
    },
    "physical_balance.served_mw": {
      "after": 59.0,
      "before": 64.6535657853615
    },
    "physical_balance.terms.p_served_mw": {
      "after": 59.0,
      "before": 64.6535657853615
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 5.653565785361494,
      "before": 0.0
    }
  },
  "tick": 220
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -5.585707924566762
    },
    "p_compute_served_mw": {
      "after": 57.711571999696446,
      "before": 63.17530056
    },
    "p_compute_unserved_mw": {
      "after": 5.4637285603035535,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.2884280003035624,
      "before": 1.4104073645667712
    },
    "p_cooling_unserved_mw": {
      "after": 0.12197936426320873,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -5.585707924566762
    },
    "p_served_mw": {
      "after": 59.0,
      "before": 64.58570792456676
    },
    "p_unserved_mw": {
      "after": 5.585707924566762,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -5.585707924566762
    },
    "physical_balance.served_mw": {
      "after": 59.0,
      "before": 64.58570792456676
    },
    "physical_balance.terms.p_served_mw": {
      "after": 59.0,
      "before": 64.58570792456676
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 5.585707924566762,
      "before": 0.0
    }
  },
  "tick": 221
}
```

```json
{
  "changed_physical_fields": {
    "d4_balance_defect_mw": {
      "after": 0.0,
      "before": -5.5858407586412255
    },
    "p_compute_served_mw": {
      "after": 57.71145330397053,
      "before": 63.17530056
    },
    "p_compute_unserved_mw": {
      "after": 5.463847256029465,
      "before": 0.0
    },
    "p_cooling_served_mw": {
      "after": 1.2885466960294718,
      "before": 1.410540198641233
    },
    "p_cooling_unserved_mw": {
      "after": 0.12199350261176117,
      "before": 0.0
    },
    "p_imbalance_mw": {
      "after": 0.0,
      "before": -5.5858407586412255
    },
    "p_served_mw": {
      "after": 59.0,
      "before": 64.58584075864123
    },
    "p_unserved_mw": {
      "after": 5.5858407586412255,
      "before": 0.0
    },
    "physical_balance.closes": {
      "after": true,
      "before": false
    },
    "physical_balance.defect_mw": {
      "after": 0.0,
      "before": -5.5858407586412255
    },
    "physical_balance.served_mw": {
      "after": 59.0,
      "before": 64.58584075864123
    },
    "physical_balance.terms.p_served_mw": {
      "after": 59.0,
      "before": 64.58584075864123
    },
    "physical_balance.terms.p_unserved_mw": {
      "after": 5.5858407586412255,
      "before": 0.0
    }
  },
  "tick": 222
}
```

### Direct-step study arms — two post-fix repetitions each

```json
{
  "all_curtailment_metrics_unchanged": true,
  "balance_failure_count": 0,
  "baseline_hash": "3aa4fdbb6691f70e407acc23b53a99ebc3c6241ce6126328ad9ba8e228fe760f",
  "curtailment_metrics": {
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-hot-01": 9.233069128,
      "gt-hot-02": 7.435268298,
      "gt-spin-01": 16.83696342,
      "gt-spin-02": 16.810284673
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 50.315585518,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "hot_standby_fuel_mmbtu": 0.0,
      "load_fuel_mmbtu": 114.574329409,
      "no_load_fuel_mmbtu": 1.47,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-hot-01": 18.101597222,
      "gt-hot-02": 14.117013889,
      "gt-spin-01": 41.971458333,
      "gt-spin-02": 41.854259965
    },
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 116.044329409,
    "dispatch_curtailment_mwh": 4.794773294
  },
  "dispatch_curtailment_mwh_raw": 4.79477329394151,
  "exact_expected_match": true,
  "hash_identical": true,
  "mode": "baseline",
  "physical_hash": "3aa4fdbb6691f70e407acc23b53a99ebc3c6241ce6126328ad9ba8e228fe760f",
  "repetition": 1,
  "ticks": 1440
}
```

```json
{
  "all_curtailment_metrics_unchanged": true,
  "balance_failure_count": 0,
  "baseline_hash": "79ca32b9c8a465f45fc91c7e34137bd22fcacaec0b43fa99e15e6b57ea3bc86e",
  "curtailment_metrics": {
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-hot-01": 0.664865971,
      "gt-hot-02": 0.566457396,
      "gt-spin-01": 1.149536383,
      "gt-spin-02": 1.080303822
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 3.461163572,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "hot_standby_fuel_mmbtu": 0.0,
      "load_fuel_mmbtu": 17.81744453,
      "no_load_fuel_mmbtu": 0.166666667,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-hot-01": 3.594157223,
      "gt-hot-02": 3.080972222,
      "gt-spin-01": 5.897152778,
      "gt-spin-02": 5.411828974
    },
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 17.984111197,
    "dispatch_curtailment_mwh": 0.370052665
  },
  "dispatch_curtailment_mwh_raw": 0.3700526648755099,
  "exact_expected_match": true,
  "hash_identical": true,
  "mode": "informed",
  "physical_hash": "79ca32b9c8a465f45fc91c7e34137bd22fcacaec0b43fa99e15e6b57ea3bc86e",
  "repetition": 1,
  "ticks": 1440
}
```

```json
{
  "all_curtailment_metrics_unchanged": true,
  "balance_failure_count": 0,
  "baseline_hash": "3aa4fdbb6691f70e407acc23b53a99ebc3c6241ce6126328ad9ba8e228fe760f",
  "curtailment_metrics": {
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-hot-01": 9.233069128,
      "gt-hot-02": 7.435268298,
      "gt-spin-01": 16.83696342,
      "gt-spin-02": 16.810284673
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 50.315585518,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "hot_standby_fuel_mmbtu": 0.0,
      "load_fuel_mmbtu": 114.574329409,
      "no_load_fuel_mmbtu": 1.47,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-hot-01": 18.101597222,
      "gt-hot-02": 14.117013889,
      "gt-spin-01": 41.971458333,
      "gt-spin-02": 41.854259965
    },
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 116.044329409,
    "dispatch_curtailment_mwh": 4.794773294
  },
  "dispatch_curtailment_mwh_raw": 4.79477329394151,
  "exact_expected_match": true,
  "hash_identical": true,
  "mode": "baseline",
  "physical_hash": "3aa4fdbb6691f70e407acc23b53a99ebc3c6241ce6126328ad9ba8e228fe760f",
  "repetition": 2,
  "ticks": 1440
}
```

```json
{
  "all_curtailment_metrics_unchanged": true,
  "balance_failure_count": 0,
  "baseline_hash": "79ca32b9c8a465f45fc91c7e34137bd22fcacaec0b43fa99e15e6b57ea3bc86e",
  "curtailment_metrics": {
    "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
      "gt-hot-01": 0.664865971,
      "gt-hot-02": 0.566457396,
      "gt-spin-01": 1.149536383,
      "gt-spin-02": 1.080303822
    },
    "dispatch_curtailment_attributable_fuel_mmbtu": 3.461163572,
    "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
      "hot_standby_fuel_mmbtu": 0.0,
      "load_fuel_mmbtu": 17.81744453,
      "no_load_fuel_mmbtu": 0.166666667,
      "start_fuel_mmbtu": 0.0
    },
    "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
      "gt-hot-01": 3.594157223,
      "gt-hot-02": 3.080972222,
      "gt-spin-01": 5.897152778,
      "gt-spin-02": 5.411828974
    },
    "dispatch_curtailment_interval_exposure_fuel_mmbtu": 17.984111197,
    "dispatch_curtailment_mwh": 0.370052665
  },
  "dispatch_curtailment_mwh_raw": 0.3700526648755099,
  "exact_expected_match": true,
  "hash_identical": true,
  "mode": "informed",
  "physical_hash": "79ca32b9c8a465f45fc91c7e34137bd22fcacaec0b43fa99e15e6b57ea3bc86e",
  "repetition": 2,
  "ticks": 1440
}
```

The other five catalogue scenarios have zero changed physical fields against their 2b.0(c) baselines, not merely matching aggregate metrics.

## 2b.5 — real-package full suite and qualified set comparison

```json
{
  "exitstatus": 1,
  "failed": 15,
  "failing_node_ids": [
    "tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation",
    "tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config",
    "tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar",
    "tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment",
    "tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve",
    "tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names",
    "tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel",
    "tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited",
    "tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context",
    "tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants",
    "tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude",
    "tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait",
    "tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes",
    "tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load",
    "tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip"
  ],
  "passed": 2139,
  "skipped": 26
}
```

Literal pytest terminal summary: `15 failed, 2139 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 821.26s (0:13:41)`.

Command: `PYTHONDONTWRITEBYTECODE=1 python /tmp/DR-ISL-phase2b/suite_capture.py`; its cwd is the real package, not a snapshot. Exit code 1 reflects the 15 listed failures. No existing failing test was weakened or edited outside the two named stale tests.

### Reference limitation and HEAD control

The historical 17-ID file is unavailable. Therefore an exact archival set subtraction from that lost file cannot be certified. Instead, `/tmp/DR-ISL-phase2b/head_control.py:1–67` runs these 15 failures plus the two Stage-3 tests with the original starting-HEAD simulation_core git blob loaded in memory. Other imports and tests use the real package; no repository source is replaced. This is a selected-test control, not an isolated full-suite snapshot and not a claim to recreate all historical outcomes.

```json
{
  "added_vs_control": [],
  "failed": 17,
  "head": "dca40d0079f53e08c25967ca390dec462668f058",
  "remaining_vs_control": [
    "tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation",
    "tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config",
    "tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar",
    "tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment",
    "tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve",
    "tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names",
    "tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel",
    "tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited",
    "tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context",
    "tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants",
    "tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude",
    "tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait",
    "tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes",
    "tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load",
    "tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip"
  ],
  "removed_vs_control": [
    "tests/test_addendum_g_stage3_option_c.py::test_stage3_last_former_ride_through_trip_causes_distinct_collapse",
    "tests/test_addendum_g_stage3_option_c.py::test_stage3_nonforming_fc_trip_reconciles_accounting_with_live_bess"
  ],
  "scope": "17 selected HEAD control tests, not a historical full-suite rerun"
}
```

All 17 control tests fail on the pre-fix engine. Relative to this explicitly reconstructed control: added=[], removed=the two IMPL-ISL-10 tests, remaining=15. This supplies direct pre-fix evidence for every current failure, with the archival limitation stated above.

### Literal full-suite output

```text
....................ss.....F............s.......Fxxxx.xxx...xxx......... [  3%]
........................................................................ [  6%]
........................................................................ [  9%]
........................................................................ [ 13%]
......F................................................................. [ 16%]
........................................................................ [ 19%]
................................................................F....... [ 23%]
........F............................................................... [ 26%]
......................................................F................. [ 29%]
................F......................x.x.x............................ [ 33%]
........F.............................................FF..F............. [ 36%]
..................................................................... [ 39%]
..............................F......................................... [ 42%]
........................................................................ [ 46%]
.......................x.xxx............................................ [ 49%]
........................................................................ [ 52%]
............................F........................................... [ 56%]
........................................................................ [ 59%]
............................................xF.......................... [ 62%]
........................................................................ [ 65%]
........................................................................ [ 69%]
........................................................................ [ 72%]
........................................................................ [ 75%]
........................................................................ [ 79%]
........................................................................ [ 82%]
........................................................................ [ 85%]
........................................................................ [ 89%]
........................................................................ [ 92%]
..........xxxxx......................................................... [ 95%]
...........................................................F............ [ 98%]
.......................                                                  [100%]
DR-ISL SUITE RESULT {"exitstatus": 1, "passed": 2139, "failed": 15, "skipped": 26, "failing_node_ids": ["tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation", "tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config", "tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar", "tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment", "tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve", "tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names", "tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel", "tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited", "tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context", "tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants", "tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude", "tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait", "tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes", "tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load", "tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip"]}

=================================== FAILURES ===================================
_ TestI4DeliveryFaultMovesFrequency.test_I4_delivery_fault_causes_frequency_deviation _
tests/test_13_3_frequency.py:434: in test_I4_delivery_fault_causes_frequency_deviation
    assert tick.asset_delivery_error_mw != pytest.approx(0.0, abs=1e-6), (
E   AssertionError: I4: asset_delivery_error_mw must be non-zero (fleet under-delivers); got 0.000000000
E   assert 0.0 != 0.0 ± 1.0e-06
E    +  where 0.0 = TickResult(run_id='test', tick_index=1, sim_time_seconds=5.1, p_compute_demand_mw=0.05253, p_cooling_demand_mw=0.0, p_...sfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id='gt-1', slurm_metrics=None).asset_delivery_error_mw
E    +  and   0.0 ± 1.0e-06 = <function approx at 0x7f317b0f20c0>(0.0, abs=1e-06)
E    +    where <function approx at 0x7f317b0f20c0> = pytest.approx
__________ TestR4PMinStable.test_R4_fields_present_on_turbine_config ___________
tests/test_13_5_criteria.py:177: in test_R4_fields_present_on_turbine_config
    assert cfg_default.p_min_stable_frac == pytest.approx(0.40), (
E   AssertionError: p_min_stable_frac default must be 0.40 (CHOSEN catalogue value).  Got 0.35
E   assert 0.35 == 0.4 ± 4.0e-07
E     
E     comparison failed
E     Obtained: 0.35
E     Expected: 0.4 ± 4.0e-07
_____ test_tc173_executor_run_validates_from_truncated_record_and_sidecar ______
tests/test_artifact_truncation.py:448: in test_tc173_executor_run_validates_from_truncated_record_and_sidecar
    assert with_detail["status"] == "PASS"
E   AssertionError: assert 'FAIL' == 'PASS'
E     
E     - PASS
E     + FAIL
----------------------------- Captured stdout call -----------------------------
TC-173 sizes: untruncated_record_bytes=13703, derived_small_cap_bytes=13702, minimum_detail_truncated_record_bytes=11107
_____ test_live_diesel_is_less_aggressive_than_disabled_before_curtailment _____
tests/test_diesel_phase3.py:180: in test_live_diesel_is_less_aggressive_than_disabled_before_curtailment
    assert disabled_tiers
E   assert ()
___________ test_hybrid_covered_demand_does_not_release_bess_reserve ___________
tests/test_diesel_setpoint_gap.py:138: in test_hybrid_covered_demand_does_not_release_bess_reserve
    assert soc_480_mwh == pytest.approx(reconciled_floor_mwh)
E   assert 5.117526258383993 == 5.52 ± 5.5e-06
E     
E     comparison failed
E     Obtained: 5.117526258383993
E     Expected: 5.52 ± 5.5e-06
__________________________ test_fabric_scenario_names __________________________
tests/test_fabric_scenarios_e2e.py:102: in test_fabric_scenario_names
    assert rec.name.startswith("Regression test —"), (
E   AssertionError: Expected a regression-test display name, got '02 Regression test — Healthy training baseline'
E   assert False
E    +  where False = <built-in method startswith of str object at 0x7f31673f80d0>('Regression test —')
E    +    where <built-in method startswith of str object at 0x7f31673f80d0> = '02 Regression test — Healthy training baseline'.startswith
E    +      where '02 Regression test — Healthy training baseline' = ScenarioRecord(scenario_id='regression-test-healthy-training-baseline', name='02 Regression test — Healthy training ba...:null}', created_at=datetime.datetime(2026, 10, 21, 10, 38, 0, 529384, tzinfo=datetime.timezone.utc), last_run_id=None).name
----------------------------- Captured stderr call -----------------------------
WARNING:     api.routes.scenarios - Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING:     api.routes.scenarios - Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING:     api.routes.scenarios - Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
------------------------------ Captured log call -------------------------------
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
_ TestDispatchTruthfulness.test_B1a_islanded_delivery_fault_visible_in_delivery_channel _
tests/test_forecast_path.py:590: in test_B1a_islanded_delivery_fault_visible_in_delivery_channel
    assert tick.asset_delivery_error_mw != pytest.approx(0.0, abs=1e-6), (
E   AssertionError: B1a: delivery fault must appear in asset_delivery_error_mw; got 0.000000000  (turbine_out=0.000000, gt_setpoint=0.000000)
E   assert 0.0 != 0.0 ± 1.0e-06
E    +  where 0.0 = TickResult(run_id='test', tick_index=1, sim_time_seconds=5.1, p_compute_demand_mw=0.10506, p_cooling_demand_mw=0.0, p_...sfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id='gt-1', slurm_metrics=None).asset_delivery_error_mw
E    +  and   0.0 ± 1.0e-06 = <function approx at 0x7f317b0f20c0>(0.0, abs=1e-06)
E    +    where <function approx at 0x7f317b0f20c0> = pytest.approx
____ test_fixed_target_survives_a_step_load_and_output_remains_rate_limited ____
tests/test_fuel_cell_phase2.py:107: in test_fixed_target_survives_a_step_load_and_output_remains_rate_limited
    ctx.sim_state.apply_workload_signal(
core/simulation_core.py:475: in apply_workload_signal
    self.lead_time_observations.record_start(self.run_id, signal)
core/lead_time_observations.py:66: in record_start
    signal.workload_class.value
E   AttributeError: 'str' object has no attribute 'value'
________ test_gridley_retrieves_operator_knowledge_for_natural_variants ________
tests/test_gridley.py:265: in test_gridley_retrieves_operator_knowledge_for_natural_variants
    assert chunks[0]["source_id"] == "gridsignal-operator-benefits", question
E   AssertionError: What does GridSignal do for someone running a GPU data center?
E   assert 'behind-the-m...arket-context' == 'gridsignal-operator-benefits'
E     
E     - gridsignal-operator-benefits
E     + behind-the-meter-market-context
_____ test_gridley_uses_grounded_operator_benefits_fallback_without_claude _____
tests/test_gridley.py:285: in test_gridley_uses_grounded_operator_benefits_fallback_without_claude
    assert "does not replace or directly command" in body["reply"]
E   AssertionError: assert 'does not replace or directly command' in '**Grounded GridSignal guidance**\n\n- The financing pressure around long-lived power assets and shorter GPU contract ...heduler queue and allocation signals to provide an earlier view of power demand while the job is still waiting to run.'
----------------------------- Captured stderr call -----------------------------
INFO:     api.db - Auth tables ready (backend=postgresql)
INFO:     api.app - Email portal URL: https://560e4bb4-a12b-40d1-a7c1-4cae34d4602a-00-2sy0v7r6028gw.picard.replit.dev  (source: REPLIT_DOMAINS)
WARNING:     api.routes.scenarios - Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING:     api.routes.scenarios - Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING:     api.routes.scenarios - Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
INFO:     api.app - Restored site_location: 'San Jose, CA' (lat=37.34, lon=-121.89, tz=America/Los_Angeles)
------------------------------ Captured log call -------------------------------
INFO     api.db:db.py:239 Auth tables ready (backend=postgresql)
INFO     api.app:app.py:185 Email portal URL: https://560e4bb4-a12b-40d1-a7c1-4cae34d4602a-00-2sy0v7r6028gw.picard.replit.dev  (source: REPLIT_DOMAINS)
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
INFO     api.app:app.py:291 Restored site_location: 'San Jose, CA' (lat=37.34, lon=-121.89, tz=America/Los_Angeles)
________ test_gridley_logs_no_match_with_question_and_scenario_context _________
tests/test_gridley.py:366: in test_gridley_logs_no_match_with_question_and_scenario_context
    assert record["scenario"] == "demo-20mw"
E   AssertionError: assert '43 demo-20mw' == 'demo-20mw'
E     
E     - demo-20mw
E     + 43 demo-20mw
E     ? +++
----------------------------- Captured stderr call -----------------------------
INFO:     api.db - Auth tables ready (backend=postgresql)
INFO:     api.app - Email portal URL: https://560e4bb4-a12b-40d1-a7c1-4cae34d4602a-00-2sy0v7r6028gw.picard.replit.dev  (source: REPLIT_DOMAINS)
WARNING:     api.routes.scenarios - Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING:     api.routes.scenarios - Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING:     api.routes.scenarios - Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
INFO:     api.app - Restored site_location: 'San Jose, CA' (lat=37.34, lon=-121.89, tz=America/Los_Angeles)
WARNING:     api.routes.ai - ai: gridley Claude response failed; using deterministic fallback: 'reply'
WARNING:     api.routes.ai - ai: gridley Claude response failed; using deterministic fallback: 'reply'
------------------------------ Captured log call -------------------------------
INFO     api.db:db.py:239 Auth tables ready (backend=postgresql)
INFO     api.app:app.py:185 Email portal URL: https://560e4bb4-a12b-40d1-a7c1-4cae34d4602a-00-2sy0v7r6028gw.picard.replit.dev  (source: REPLIT_DOMAINS)
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
INFO     api.app:app.py:291 Restored site_location: 'San Jose, CA' (lat=37.34, lon=-121.89, tz=America/Los_Angeles)
WARNING  api.routes.ai:ai.py:1488 ai: gridley Claude response failed; using deterministic fallback: 'reply'
WARNING  api.routes.ai:ai.py:1488 ai: gridley Claude response failed; using deterministic fallback: 'reply'
___ test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait ___
tests/test_kubernetes_scheduler_demo_scenario.py:20: in test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait
    assert spec["name"] == "Kubernetes Scheduler - Resource Queue Demo"
E   AssertionError: assert '24 Kubernete...ce Queue Demo' == 'Kubernetes S...ce Queue Demo'
E     
E     - Kubernetes Scheduler - Resource Queue Demo
E     + 24 Kubernetes Scheduler - Resource Queue Demo
E     ? +++
----------------------------- Captured stderr call -----------------------------
WARNING:     api.routes.scenarios - Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING:     api.routes.scenarios - Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING:     api.routes.scenarios - Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
------------------------------ Captured log call -------------------------------
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
______________ TestApiStaticLayer.test_api_gate_clean_api_passes _______________
tests/test_plane_separation.py:496: in test_api_gate_clean_api_passes
    assert not all_violations, (
E   AssertionError: api/ core-import violations found — build fails:
E       api/routes/ingest.py:17: from core.models import ... — forbidden in api/ (top-level package 'core' is in forbidden list)
E       api/routes/ingest.py:18: from core.slurm_scheduler import ... — forbidden in api/ (top-level package 'core' is in forbidden list)
E   assert not ["api/routes/ingest.py:17: from core.models import ... — forbidden in api/ (top-level package 'core' is in forbidden l...ngest.py:18: from core.slurm_scheduler import ... — forbidden in api/ (top-level package 'core' is in forbidden list)"]
_ test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load __
tests/test_scenario_fc100_islanded_v2.py:173: in test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load
    assert all(t.bess_output_mw == pytest.approx(0.0, abs=1e-9) for t in baseline)
E   assert False
E    +  where False = all(<generator object test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load.<locals>.<genexpr> at 0x7f315fd42110>)
----------------------------- Captured stderr call -----------------------------
WARNING:     api.routes.scenarios - Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING:     api.routes.scenarios - Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING:     api.routes.scenarios - Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
------------------------------ Captured log call -------------------------------
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
WARNING  core.dispatch:dispatch.py:1304 CurtailmentLadder.generate_candidates: dead-man expiry sim_time=600.0, activated_at=295.0, MAX_HOLD_S=300s (TC-46).
WARNING  core.dispatch:dispatch.py:1304 CurtailmentLadder.generate_candidates: dead-man expiry sim_time=1030.0, activated_at=725.0, MAX_HOLD_S=300s (TC-46).
__________ test_tc84f_demo_20mw_contingency_state_changes_after_trip ___________
tests/test_unit_trip.py:407: in test_tc84f_demo_20mw_contingency_state_changes_after_trip
    assert turbine1_offline_seen, (
E   AssertionError: turbine-1 was never set OFFLINE after the UNIT_TRIP event at t=120 s
E   assert False
----------------------------- Captured stderr call -----------------------------
WARNING:     api.routes.scenarios - Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING:     api.routes.scenarios - Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING:     api.routes.scenarios - Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
------------------------------ Captured log call -------------------------------
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
WARNING  core.simulation_core:simulation_core.py:2065 Commitment engine: clearing stale pending-start register for 'turbine-1' at sim_time=120.0 — unit is OFFLINE, start did not take
=============================== warnings summary ===============================
../../../../.pythonlibs/lib/python3.13/site-packages/fastapi/testclient.py:1
  /home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

tests/test_13_2_balance_decomp.py: 7 warnings
tests/test_13_3_frequency.py: 2 warnings
tests/test_aggregate_sources.py: 2 warnings
tests/test_forecast_path.py: 3 warnings
tests/test_frequency_mode_guard.py: 3 warnings
tests/test_physical_balance_invariant.py: 1 warning
  <string>:11: UserWarning: BessConfig 'bess-1': C-rate 500.00 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=5.0, usable_mwh=0.01

tests/test_13_4_criteria.py::TestB2BessLagTracksSetpoint::test_B2c_output_converges_to_setpoint_at_steady_state
  <string>:11: UserWarning: BessConfig 'b-conv': C-rate 0.20 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=10.0, usable_mwh=50.0

tests/test_13_6_step_scheduler.py::TestTC136Structural::test_gpu_modules_have_load_config
tests/test_13_6_step_scheduler.py::TestTC136Behavioral::test_settled_power_below_peak_ceiling
  /home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/_pytest/fixtures.py:1313: PytestRemovedIn10Warning: Class-scoped fixture defined as instance method is deprecated.
  Instance attributes set in this fixture will NOT be visible to test methods,
  as each test gets a new instance while the fixture runs only once per class.
  Use @classmethod decorator and set attributes on cls instead.
  See https://docs.pytest.org/en/stable/deprecations.html#class-scoped-fixture-as-instance-method
    fixturefunc = resolve_fixture_function(fixturedef, request)

tests/test_addendum_h_phase2a_commitment.py::test_tc131_preload_is_bounded_by_bess_charge_power
  <string>:11: UserWarning: BessConfig 'bess-0': C-rate 0.04 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=5.0, usable_mwh=120.0

tests/test_aggregate_sources.py::TestFuelCellAggregate::test_FC11_all_three_sources_follow_cost_order_at_capacity
  <string>:11: UserWarning: BessConfig 'bess-0': C-rate 0.20 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=1.0, usable_mwh=5.0

tests/test_aggregate_sources.py::TestFuelCellAggregate::test_FC12_energy_limited_bess_does_not_skip_turbine
  <string>:11: UserWarning: BessConfig 'bess-0': C-rate 5.00 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=5.0, usable_mwh=1.0

tests/test_api.py::test_post_run_rejects_disabled_declared_fuel_cell_module_array
  /home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/fastapi/routing.py:352: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.
    return await dependant.call(**values)

tests/test_auth.py::test_admin_endpoint_with_operator_session_returns_403
tests/test_auth.py::test_deactivated_user_returns_401
tests/test_bootstrap.py::test_bootstrap_one_time_code_is_usable_for_login
  /home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/starlette/testclient.py:454: DeprecationWarning: Setting per-request cookies=<...> is being deprecated, because the expected behaviour on cookie persistence is ambiguous. Set cookies directly on the client instance instead.
    return super().request(

tests/test_auth.py::test_change_password_first_time_set_succeeds
tests/test_auth.py::test_change_password_correct_current_password_succeeds
tests/test_auth.py::test_change_password_wrong_current_password_returns_401
  /home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/httpx/_client.py:1859: DeprecationWarning: Setting per-request cookies=<...> is being deprecated, because the expected behaviour on cookie persistence is ambiguous. Set cookies directly on the client instance instead.
    return await self.request(

tests/test_auth.py::test_change_password_first_time_set_succeeds
tests/test_auth.py::test_change_password_correct_current_password_succeeds
  /home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/httpx/_client.py:1768: DeprecationWarning: Setting per-request cookies=<...> is being deprecated, because the expected behaviour on cookie persistence is ambiguous. Set cookies directly on the client instance instead.
    return await self.request(

tests/test_f2_bridging_basis.py::test_bridging_basis_no_load_when_net_demand_zero
tests/test_f2_bridging_basis.py::test_bridging_basis_in_tick_payload
tests/test_step7_payload.py::test_p_renewable_mw_exposed_in_tick_result
tests/test_step7_payload.py::test_p_renewable_mw_absent_when_no_solar
tests/test_step7_payload.py::test_bess_bridging_seconds_in_tick_payload
tests/test_step7_payload.py::test_dt_lead_next_s_zero_when_no_ramp
tests/test_step7_payload.py::test_dt_lead_next_s_in_tick_payload
tests/test_step7_payload.py::test_turbine_ramp_credit_zero_in_payload_when_no_ramp
tests/test_turbine_payload_p0.py::test_tc_p0_6_sync_relay_state_from_factory
  <string>:11: UserWarning: BessConfig 'bess-0': C-rate 5.00 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=10.0, usable_mwh=2.0

tests/test_fc_bess_physical_dispatch.py::test_fc_achieved_output_equal_to_demand_does_not_dispatch_bess
tests/test_fc_bess_physical_dispatch.py::test_fixed_fc_surplus_is_absorbed_by_bess
  <string>:11: UserWarning: BessConfig 'bess': C-rate 0.10 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=10.0, usable_mwh=100.0

tests/test_formulas.py::test_item4_small_unit_capped_to_ceiling_under_equal_share
  <string>:11: UserWarning: BessConfig 'ba': C-rate 0.20 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=2.0, usable_mwh=10.0

tests/test_formulas.py::test_d13_min_not_sum_fleet_endurance
  <string>:11: UserWarning: BessConfig 'a-d13': C-rate 10.00 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=10.0, usable_mwh=1.0

tests/test_reserve_reconciliation.py::test_tc_r2_depth_reserve_wins_when_diesel_floor_is_smaller
  <string>:11: UserWarning: BessConfig 'bess-reserve': C-rate 0.10 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=10.0, usable_mwh=100.0

tests/test_step7_payload.py::test_bess_bridging_seconds_above_power_ceiling_returns_zero
  <string>:11: UserWarning: BessConfig 'bess-0': C-rate 0.05 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=5.0, usable_mwh=100.0

tests/test_step7_payload.py::test_bess_bridging_seconds_within_power_ceiling
  <string>:11: UserWarning: BessConfig 'bess-1': C-rate 10.00 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=10.0, usable_mwh=1.0

tests/test_step8_scenarios.py::TestSolarStepTriggersStaging::test_solar_step_sets_pending_alert
tests/test_step8_scenarios.py::TestSolarStepTriggersStaging::test_solar_step_does_not_touch_gpu_state
tests/test_step8_scenarios.py::TestTC33Symmetry::test_compute_path_fires_alert
tests/test_step8_scenarios.py::TestTC33Symmetry::test_renewable_path_fires_alert_with_larger_gap
  <string>:11: UserWarning: BessConfig 'bess-0': C-rate 500.00 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=5.0, usable_mwh=0.01

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation
FAILED tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config
FAILED tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar
FAILED tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment
FAILED tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve
FAILED tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names - Asser...
FAILED tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel
FAILED tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited
FAILED tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants
FAILED tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude
FAILED tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context
FAILED tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait
FAILED tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes
FAILED tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load
FAILED tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip
15 failed, 2139 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 821.26s (0:13:41)
```

### Literal HEAD-control output

```text
FFFFFFFFFFFFFFFFF                                                        [100%]HEAD CONTROL {"scope": "17 selected HEAD control tests, not a historical full-suite rerun", "head": "dca40d0079f53e08c25967ca390dec462668f058", "failed": 17, "added_vs_control": [], "removed_vs_control": ["tests/test_addendum_g_stage3_option_c.py::test_stage3_last_former_ride_through_trip_causes_distinct_collapse", "tests/test_addendum_g_stage3_option_c.py::test_stage3_nonforming_fc_trip_reconciles_accounting_with_live_bess"], "remaining_vs_control": ["tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation", "tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config", "tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar", "tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment", "tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve", "tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names", "tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel", "tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited", "tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context", "tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants", "tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude", "tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait", "tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes", "tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load", "tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip"]}

=================================== FAILURES ===================================
_ TestI4DeliveryFaultMovesFrequency.test_I4_delivery_fault_causes_frequency_deviation _
tests/test_13_3_frequency.py:434: in test_I4_delivery_fault_causes_frequency_deviation
    assert tick.asset_delivery_error_mw != pytest.approx(0.0, abs=1e-6), (
E   AssertionError: I4: asset_delivery_error_mw must be non-zero (fleet under-delivers); got 0.000000000
E   assert 0.0 != 0.0 ± 1.0e-06
E    +  where 0.0 = TickResult(run_id='test', tick_index=1, sim_time_seconds=5.1, p_compute_demand_mw=0.05253, p_cooling_demand_mw=0.0, p_...sfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id='gt-1', slurm_metrics=None).asset_delivery_error_mw
E    +  and   0.0 ± 1.0e-06 = <function approx at 0x7f46ff1b8a40>(0.0, abs=1e-06)
E    +    where <function approx at 0x7f46ff1b8a40> = pytest.approx
__________ TestR4PMinStable.test_R4_fields_present_on_turbine_config ___________
tests/test_13_5_criteria.py:177: in test_R4_fields_present_on_turbine_config
    assert cfg_default.p_min_stable_frac == pytest.approx(0.40), (
E   AssertionError: p_min_stable_frac default must be 0.40 (CHOSEN catalogue value).  Got 0.35
E   assert 0.35 == 0.4 ± 4.0e-07
E     
E     comparison failed
E     Obtained: 0.35
E     Expected: 0.4 ± 4.0e-07
_____ test_tc173_executor_run_validates_from_truncated_record_and_sidecar ______
tests/test_artifact_truncation.py:448: in test_tc173_executor_run_validates_from_truncated_record_and_sidecar
    assert with_detail["status"] == "PASS"
E   AssertionError: assert 'FAIL' == 'PASS'
E     
E     - PASS
E     + FAIL
----------------------------- Captured stdout call -----------------------------
TC-173 sizes: untruncated_record_bytes=13703, derived_small_cap_bytes=13702, minimum_detail_truncated_record_bytes=11107
_____ test_live_diesel_is_less_aggressive_than_disabled_before_curtailment _____
tests/test_diesel_phase3.py:180: in test_live_diesel_is_less_aggressive_than_disabled_before_curtailment
    assert disabled_tiers
E   assert ()
___________ test_hybrid_covered_demand_does_not_release_bess_reserve ___________
tests/test_diesel_setpoint_gap.py:138: in test_hybrid_covered_demand_does_not_release_bess_reserve
    assert soc_480_mwh == pytest.approx(reconciled_floor_mwh)
E   assert 5.117526258383993 == 5.52 ± 5.5e-06
E     
E     comparison failed
E     Obtained: 5.117526258383993
E     Expected: 5.52 ± 5.5e-06
__________________________ test_fabric_scenario_names __________________________
tests/test_fabric_scenarios_e2e.py:102: in test_fabric_scenario_names
    assert rec.name.startswith("Regression test —"), (
E   AssertionError: Expected a regression-test display name, got '02 Regression test — Healthy training baseline'
E   assert False
E    +  where False = <built-in method startswith of str object at 0x7f46ee2ebcd0>('Regression test —')
E    +    where <built-in method startswith of str object at 0x7f46ee2ebcd0> = '02 Regression test — Healthy training baseline'.startswith
E    +      where '02 Regression test — Healthy training baseline' = ScenarioRecord(scenario_id='regression-test-healthy-training-baseline', name='02 Regression test — Healthy training ba...null}', created_at=datetime.datetime(2026, 10, 21, 10, 49, 49, 847392, tzinfo=datetime.timezone.utc), last_run_id=None).name
----------------------------- Captured stderr call -----------------------------
WARNING:     api.routes.scenarios - Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING:     api.routes.scenarios - Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING:     api.routes.scenarios - Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
------------------------------ Captured log call -------------------------------
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
_ TestDispatchTruthfulness.test_B1a_islanded_delivery_fault_visible_in_delivery_channel _
tests/test_forecast_path.py:590: in test_B1a_islanded_delivery_fault_visible_in_delivery_channel
    assert tick.asset_delivery_error_mw != pytest.approx(0.0, abs=1e-6), (
E   AssertionError: B1a: delivery fault must appear in asset_delivery_error_mw; got 0.000000000  (turbine_out=0.000000, gt_setpoint=0.000000)
E   assert 0.0 != 0.0 ± 1.0e-06
E    +  where 0.0 = TickResult(run_id='test', tick_index=1, sim_time_seconds=5.1, p_compute_demand_mw=0.10506, p_cooling_demand_mw=0.0, p_...sfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id='gt-1', slurm_metrics=None).asset_delivery_error_mw
E    +  and   0.0 ± 1.0e-06 = <function approx at 0x7f46ff1b8a40>(0.0, abs=1e-06)
E    +    where <function approx at 0x7f46ff1b8a40> = pytest.approx
____ test_fixed_target_survives_a_step_load_and_output_remains_rate_limited ____
tests/test_fuel_cell_phase2.py:107: in test_fixed_target_survives_a_step_load_and_output_remains_rate_limited
    ctx.sim_state.apply_workload_signal(
core/simulation_core.py:475: in apply_workload_signal
    self.lead_time_observations.record_start(self.run_id, signal)
core/lead_time_observations.py:66: in record_start
    signal.workload_class.value
E   AttributeError: 'str' object has no attribute 'value'
________ test_gridley_logs_no_match_with_question_and_scenario_context _________
tests/test_gridley.py:366: in test_gridley_logs_no_match_with_question_and_scenario_context
    assert record["scenario"] == "demo-20mw"
E   AssertionError: assert '43 demo-20mw' == 'demo-20mw'
E     
E     - demo-20mw
E     + 43 demo-20mw
E     ? +++
----------------------------- Captured stderr call -----------------------------
INFO:     api.db - Auth tables ready (backend=postgresql)
INFO:     api.app - Email portal URL: https://560e4bb4-a12b-40d1-a7c1-4cae34d4602a-00-2sy0v7r6028gw.picard.replit.dev  (source: REPLIT_DOMAINS)
WARNING:     api.routes.scenarios - Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING:     api.routes.scenarios - Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING:     api.routes.scenarios - Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
INFO:     api.app - Restored site_location: 'San Jose, CA' (lat=37.34, lon=-121.89, tz=America/Los_Angeles)
WARNING:     api.routes.ai - ai: gridley Claude response failed; using deterministic fallback: 'reply'
WARNING:     api.routes.ai - ai: gridley Claude response failed; using deterministic fallback: 'reply'
------------------------------ Captured log call -------------------------------
INFO     api.db:db.py:239 Auth tables ready (backend=postgresql)
INFO     api.app:app.py:185 Email portal URL: https://560e4bb4-a12b-40d1-a7c1-4cae34d4602a-00-2sy0v7r6028gw.picard.replit.dev  (source: REPLIT_DOMAINS)
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
INFO     api.app:app.py:291 Restored site_location: 'San Jose, CA' (lat=37.34, lon=-121.89, tz=America/Los_Angeles)
WARNING  api.routes.ai:ai.py:1488 ai: gridley Claude response failed; using deterministic fallback: 'reply'
WARNING  api.routes.ai:ai.py:1488 ai: gridley Claude response failed; using deterministic fallback: 'reply'
________ test_gridley_retrieves_operator_knowledge_for_natural_variants ________
tests/test_gridley.py:265: in test_gridley_retrieves_operator_knowledge_for_natural_variants
    assert chunks[0]["source_id"] == "gridsignal-operator-benefits", question
E   AssertionError: What does GridSignal do for someone running a GPU data center?
E   assert 'behind-the-m...arket-context' == 'gridsignal-operator-benefits'
E     
E     - gridsignal-operator-benefits
E     + behind-the-meter-market-context
_____ test_gridley_uses_grounded_operator_benefits_fallback_without_claude _____
tests/test_gridley.py:285: in test_gridley_uses_grounded_operator_benefits_fallback_without_claude
    assert "does not replace or directly command" in body["reply"]
E   AssertionError: assert 'does not replace or directly command' in '**Grounded GridSignal guidance**\n\n- The financing pressure around long-lived power assets and shorter GPU contract ...heduler queue and allocation signals to provide an earlier view of power demand while the job is still waiting to run.'
----------------------------- Captured stderr call -----------------------------
INFO:     api.db - Auth tables ready (backend=postgresql)
INFO:     api.app - Email portal URL: https://560e4bb4-a12b-40d1-a7c1-4cae34d4602a-00-2sy0v7r6028gw.picard.replit.dev  (source: REPLIT_DOMAINS)
WARNING:     api.routes.scenarios - Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING:     api.routes.scenarios - Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING:     api.routes.scenarios - Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
INFO:     api.app - Restored site_location: 'San Jose, CA' (lat=37.34, lon=-121.89, tz=America/Los_Angeles)
------------------------------ Captured log call -------------------------------
INFO     api.db:db.py:239 Auth tables ready (backend=postgresql)
INFO     api.app:app.py:185 Email portal URL: https://560e4bb4-a12b-40d1-a7c1-4cae34d4602a-00-2sy0v7r6028gw.picard.replit.dev  (source: REPLIT_DOMAINS)
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
INFO     api.app:app.py:291 Restored site_location: 'San Jose, CA' (lat=37.34, lon=-121.89, tz=America/Los_Angeles)
___ test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait ___
tests/test_kubernetes_scheduler_demo_scenario.py:20: in test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait
    assert spec["name"] == "Kubernetes Scheduler - Resource Queue Demo"
E   AssertionError: assert '24 Kubernete...ce Queue Demo' == 'Kubernetes S...ce Queue Demo'
E     
E     - Kubernetes Scheduler - Resource Queue Demo
E     + 24 Kubernetes Scheduler - Resource Queue Demo
E     ? +++
----------------------------- Captured stderr call -----------------------------
WARNING:     api.routes.scenarios - Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING:     api.routes.scenarios - Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING:     api.routes.scenarios - Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
------------------------------ Captured log call -------------------------------
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
______________ TestApiStaticLayer.test_api_gate_clean_api_passes _______________
tests/test_plane_separation.py:496: in test_api_gate_clean_api_passes
    assert not all_violations, (
E   AssertionError: api/ core-import violations found — build fails:
E       api/routes/ingest.py:17: from core.models import ... — forbidden in api/ (top-level package 'core' is in forbidden list)
E       api/routes/ingest.py:18: from core.slurm_scheduler import ... — forbidden in api/ (top-level package 'core' is in forbidden list)
E   assert not ["api/routes/ingest.py:17: from core.models import ... — forbidden in api/ (top-level package 'core' is in forbidden l...ngest.py:18: from core.slurm_scheduler import ... — forbidden in api/ (top-level package 'core' is in forbidden list)"]
_ test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load __
tests/test_scenario_fc100_islanded_v2.py:173: in test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load
    assert all(t.bess_output_mw == pytest.approx(0.0, abs=1e-9) for t in baseline)
E   assert False
E    +  where False = all(<generator object test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load.<locals>.<genexpr> at 0x7f46ee06bb50>)
----------------------------- Captured stderr call -----------------------------
WARNING:     api.routes.scenarios - Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING:     api.routes.scenarios - Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING:     api.routes.scenarios - Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
------------------------------ Captured log call -------------------------------
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
WARNING  core.dispatch:dispatch.py:1304 CurtailmentLadder.generate_candidates: dead-man expiry sim_time=600.0, activated_at=295.0, MAX_HOLD_S=300s (TC-46).
WARNING  core.dispatch:dispatch.py:1304 CurtailmentLadder.generate_candidates: dead-man expiry sim_time=1030.0, activated_at=725.0, MAX_HOLD_S=300s (TC-46).
__________ test_tc84f_demo_20mw_contingency_state_changes_after_trip ___________
tests/test_unit_trip.py:407: in test_tc84f_demo_20mw_contingency_state_changes_after_trip
    assert turbine1_offline_seen, (
E   AssertionError: turbine-1 was never set OFFLINE after the UNIT_TRIP event at t=120 s
E   assert False
----------------------------- Captured stderr call -----------------------------
WARNING:     api.routes.scenarios - Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING:     api.routes.scenarios - Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING:     api.routes.scenarios - Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING:     api.routes.scenarios - Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING:     api.routes.scenarios - Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
------------------------------ Captured log call -------------------------------
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-islanded-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-operator-trip turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded_ramp_3hr_50MW_BESS_50_to_1000_GPUs turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.53 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-10-tenant-overload-120pct turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 2.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario islanded-8-60-10-ramp turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 8.40 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario demo-rolling-planning-peaks turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 6.30 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario scenario-uneven-multisched-01 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 45.00 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-enterprise-8gpu-air-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-h100-sxm5-8way-nvl4-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.01 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-training turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario lead-time-nextgen-rack-liquid-inference turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.12 MW burst alone
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario addendum-h-lead-time-profile-validation turbine starting-count violation: cannot estimate first burst for hardware profile 'addendum_h_test_ramp_20s'
WARNING  api.routes.scenarios:scenarios.py:1461 Scenario S10_mit_supercloud_2021-08-11 turbine starting-count violation: base_load_mw is unset; first-burst coverage was checked against the 0.24 MW burst alone
WARNING  core.simulation_core:simulation_core.py:2065 Commitment engine: clearing stale pending-start register for 'turbine-1' at sim_time=120.0 — unit is OFFLINE, start did not take
______ test_stage3_last_former_ride_through_trip_causes_distinct_collapse ______
tests/test_addendum_g_stage3_option_c.py:374: in test_stage3_last_former_ride_through_trip_causes_distinct_collapse
    assert result.physical_balance.passed is True
E   AssertionError: assert False is True
E    +  where False = BalanceResult(defect_mw=-0.01, served_mw=0.0, import_mw=0.0, closes=False, tolerance_mw=1.9913e-14, terms=BalanceTerms...w=0.01, island_mode='islanded', p_served_mw=0.0, p_turbine_mw=0, p_bess_mw=-0.0, p_fuel_cell_mw=0.0, p_renewable_mw=0)).passed
E    +    where BalanceResult(defect_mw=-0.01, served_mw=0.0, import_mw=0.0, closes=False, tolerance_mw=1.9913e-14, terms=BalanceTerms...w=0.01, island_mode='islanded', p_served_mw=0.0, p_turbine_mw=0, p_bess_mw=-0.0, p_fuel_cell_mw=0.0, p_renewable_mw=0)) = TickResult(run_id='stage3-integration', tick_index=1, sim_time_seconds=0.01, p_compute_demand_mw=0, p_cooling_demand_m...atisfied=True, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id=None, slurm_metrics=None).physical_balance
------------------------------ Captured log call -------------------------------
WARNING  core.simulation_core:simulation_core.py:3563 physical balance invariant does not close: -0.01 MW (generation=0.0000, served=0.0000, unserved=0.0000, grid_import=0.0000, losses=0.0000, islanded=True)
_____ test_stage3_nonforming_fc_trip_reconciles_accounting_with_live_bess ______
tests/test_addendum_g_stage3_option_c.py:394: in test_stage3_nonforming_fc_trip_reconciles_accounting_with_live_bess
    assert result.physical_balance.passed is True
E   AssertionError: assert False is True
E    +  where False = BalanceResult(defect_mw=-0.01, served_mw=0.0, import_mw=0.0, closes=False, tolerance_mw=1.9913e-14, terms=BalanceTerms...w=0.01, island_mode='islanded', p_served_mw=0.0, p_turbine_mw=0, p_bess_mw=-0.0, p_fuel_cell_mw=0.0, p_renewable_mw=0)).passed
E    +    where BalanceResult(defect_mw=-0.01, served_mw=0.0, import_mw=0.0, closes=False, tolerance_mw=1.9913e-14, terms=BalanceTerms...w=0.01, island_mode='islanded', p_served_mw=0.0, p_turbine_mw=0, p_bess_mw=-0.0, p_fuel_cell_mw=0.0, p_renewable_mw=0)) = TickResult(run_id='stage3-integration', tick_index=1, sim_time_seconds=0.01, p_compute_demand_mw=0, p_cooling_demand_m...atisfied=True, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id=None, slurm_metrics=None).physical_balance
------------------------------ Captured log call -------------------------------
WARNING  core.simulation_core:simulation_core.py:3563 physical balance invariant does not close: -0.01 MW (generation=0.0000, served=0.0000, unserved=0.0000, grid_import=0.0000, losses=0.0000, islanded=True)
=============================== warnings summary ===============================
../../../../.pythonlibs/lib/python3.13/site-packages/fastapi/testclient.py:1
  /home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation
tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel
  <string>:11: UserWarning: BessConfig 'bess-1': C-rate 500.00 C is outside the 0.25–4.0 C physical range (PROTO-9 — chosen, no measured basis). rated_mw=5.0, usable_mwh=0.01

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation
FAILED tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config
FAILED tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar
FAILED tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment
FAILED tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve
FAILED tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names - Asser...
FAILED tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel
FAILED tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited
FAILED tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context
FAILED tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants
FAILED tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude
FAILED tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait
FAILED tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes
FAILED tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load
FAILED tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip
FAILED tests/test_addendum_g_stage3_option_c.py::test_stage3_last_former_ride_through_trip_causes_distinct_collapse
FAILED tests/test_addendum_g_stage3_option_c.py::test_stage3_nonforming_fc_trip_reconciles_accounting_with_live_bess
17 failed, 3 warnings in 39.54s
```

## 2b.6 — local commit, files and status

```text
commit 1713cd0ff01ebc0f8e11f581a149713677db2a45
Author:     Lloyd Spencer <146573701+simergalis@users.noreply.github.com>
AuthorDate: Wed Oct 21 10:50:47 2026 +0000
Commit:     Lloyd Spencer <146573701+simergalis@users.noreply.github.com>
CommitDate: Wed Oct 21 10:50:47 2026 +0000

    IMPL-ISL-10 + D7 (IMPL-ISL-11): reconcile curtailment after trips; capped grid-tied shortfall counts as unserved
```

Changed files and current line ranges:

- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3487–3512,3531–3534`.

- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_grid_import_limit_scenario.py:314–345,724–734`.

- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2b.py:1–53` (new).

- `tools/dr_isl/PHASE_2B_REPORT.md` renamed with 100% identical content to `tools/dr_isl/PHASE_2B_STOP1_REPORT.md:1–243`.

- The current full report is saved to `/tmp/DR-ISL-phase2b/PHASE_2B_REPORT.md` and copied back to `tools/dr_isl/PHASE_2B_REPORT.md` uncommitted as requested.

After commit, before report-copy creation, `git status --short` was empty. After creating the report copy the expected sole status entry is `?? tools/dr_isl/PHASE_2B_REPORT.md`; final status is appended below.

Runtime verification: restarted `artifacts/gridsignal: web` once after the code batch. Startup completed, Uvicorn listened on 0.0.0.0:22126 and GET / returned HTTP 200 (workflow log `/tmp/logs/artifactsgridsignal_web_20261021_104952_138_e36ed1a4.log`). Existing scenario-starting-count warnings were printed; startup did not fail.

Screenshot capture failed with upload status 503; no visual verification is claimed. An independent GET to the proxied development root returned `preview_http_status=200` and saved `/tmp/DR-ISL-phase2b/preview_root.html`.

### Scratch outputs (literal file list at assembly)

```text
/tmp/DR-ISL-phase2b/PHASE_2B_REPORT.md
/tmp/DR-ISL-phase2b/catalogue_gate.log
/tmp/DR-ISL-phase2b/catalogue_gate.py
/tmp/DR-ISL-phase2b/consumer_inventory.md
/tmp/DR-ISL-phase2b/consumer_search.txt
/tmp/DR-ISL-phase2b/consumers_all.txt
/tmp/DR-ISL-phase2b/failing_tests.txt
/tmp/DR-ISL-phase2b/full_suite.log
/tmp/DR-ISL-phase2b/gate-catalogue/S10_mit_supercloud_2021-08-11/S10_mit_supercloud_2021-08-11.1.events.json
/tmp/DR-ISL-phase2b/gate-catalogue/S10_mit_supercloud_2021-08-11/S10_mit_supercloud_2021-08-11.1.spec.json
/tmp/DR-ISL-phase2b/gate-catalogue/S10_mit_supercloud_2021-08-11/S10_mit_supercloud_2021-08-11.1.summary.json
/tmp/DR-ISL-phase2b/gate-catalogue/S10_mit_supercloud_2021-08-11/S10_mit_supercloud_2021-08-11.1.ticks.jsonl
/tmp/DR-ISL-phase2b/gate-catalogue/S10_mit_supercloud_2021-08-11/command.log
/tmp/DR-ISL-phase2b/gate-catalogue/S10_mit_supercloud_2021-08-11/engine.log
/tmp/DR-ISL-phase2b/gate-catalogue/demo-islanded-ramp/command.log
/tmp/DR-ISL-phase2b/gate-catalogue/demo-islanded-ramp/demo-islanded-ramp.1.events.json
/tmp/DR-ISL-phase2b/gate-catalogue/demo-islanded-ramp/demo-islanded-ramp.1.spec.json
/tmp/DR-ISL-phase2b/gate-catalogue/demo-islanded-ramp/demo-islanded-ramp.1.summary.json
/tmp/DR-ISL-phase2b/gate-catalogue/demo-islanded-ramp/demo-islanded-ramp.1.ticks.jsonl
/tmp/DR-ISL-phase2b/gate-catalogue/demo-islanded-ramp/engine.log
/tmp/DR-ISL-phase2b/gate-catalogue/results.json
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-100mw-fuel-cell-bess-diesel/command.log
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-100mw-fuel-cell-bess-diesel/engine.log
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-100mw-fuel-cell-bess-diesel/scenario-100mw-fuel-cell-bess-diesel.1.events.json
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-100mw-fuel-cell-bess-diesel/scenario-100mw-fuel-cell-bess-diesel.1.spec.json
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-100mw-fuel-cell-bess-diesel/scenario-100mw-fuel-cell-bess-diesel.1.summary.json
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-100mw-fuel-cell-bess-diesel/scenario-100mw-fuel-cell-bess-diesel.1.ticks.jsonl
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-equinix-sj-1/command.log
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-equinix-sj-1/engine.log
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-equinix-sj-1/scenario-equinix-sj-1.1.events.json
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-equinix-sj-1/scenario-equinix-sj-1.1.spec.json
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-equinix-sj-1/scenario-equinix-sj-1.1.summary.json
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-equinix-sj-1/scenario-equinix-sj-1.1.ticks.jsonl
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-hybrid-ai-100mw-addendum-i/command.log
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-hybrid-ai-100mw-addendum-i/engine.log
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-hybrid-ai-100mw-addendum-i/scenario-hybrid-ai-100mw-addendum-i.1.events.json
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-hybrid-ai-100mw-addendum-i/scenario-hybrid-ai-100mw-addendum-i.1.spec.json
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-hybrid-ai-100mw-addendum-i/scenario-hybrid-ai-100mw-addendum-i.1.summary.json
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-hybrid-ai-100mw-addendum-i/scenario-hybrid-ai-100mw-addendum-i.1.ticks.jsonl
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-turbine-01/command.log
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-turbine-01/engine.log
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-turbine-01/scenario-turbine-01.1.events.json
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-turbine-01/scenario-turbine-01.1.spec.json
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-turbine-01/scenario-turbine-01.1.summary.json
/tmp/DR-ISL-phase2b/gate-catalogue/scenario-turbine-01/scenario-turbine-01.1.ticks.jsonl
/tmp/DR-ISL-phase2b/gate-harness/baseline.ticks.jsonl
/tmp/DR-ISL-phase2b/gate-harness/engine.log
/tmp/DR-ISL-phase2b/gate-harness/informed.ticks.jsonl
/tmp/DR-ISL-phase2b/gate-harness/probe.json
/tmp/DR-ISL-phase2b/gate-harness/results.json
/tmp/DR-ISL-phase2b/gate_history.txt
/tmp/DR-ISL-phase2b/harness_gate.log
/tmp/DR-ISL-phase2b/harness_gate.py
/tmp/DR-ISL-phase2b/head_control.log
/tmp/DR-ISL-phase2b/head_control.py
/tmp/DR-ISL-phase2b/head_control_result.json
/tmp/DR-ISL-phase2b/post-catalogue/S10_mit_supercloud_2021-08-11/S10_mit_supercloud_2021-08-11.1.events.json
/tmp/DR-ISL-phase2b/post-catalogue/S10_mit_supercloud_2021-08-11/S10_mit_supercloud_2021-08-11.1.spec.json
/tmp/DR-ISL-phase2b/post-catalogue/S10_mit_supercloud_2021-08-11/S10_mit_supercloud_2021-08-11.1.summary.json
/tmp/DR-ISL-phase2b/post-catalogue/S10_mit_supercloud_2021-08-11/S10_mit_supercloud_2021-08-11.1.ticks.jsonl
/tmp/DR-ISL-phase2b/post-catalogue/S10_mit_supercloud_2021-08-11/S10_mit_supercloud_2021-08-11.2.events.json
/tmp/DR-ISL-phase2b/post-catalogue/S10_mit_supercloud_2021-08-11/S10_mit_supercloud_2021-08-11.2.spec.json
/tmp/DR-ISL-phase2b/post-catalogue/S10_mit_supercloud_2021-08-11/S10_mit_supercloud_2021-08-11.2.summary.json
/tmp/DR-ISL-phase2b/post-catalogue/S10_mit_supercloud_2021-08-11/S10_mit_supercloud_2021-08-11.2.ticks.jsonl
/tmp/DR-ISL-phase2b/post-catalogue/S10_mit_supercloud_2021-08-11/command.log
/tmp/DR-ISL-phase2b/post-catalogue/S10_mit_supercloud_2021-08-11/engine.log
/tmp/DR-ISL-phase2b/post-catalogue/demo-islanded-ramp/command.log
/tmp/DR-ISL-phase2b/post-catalogue/demo-islanded-ramp/demo-islanded-ramp.1.events.json
/tmp/DR-ISL-phase2b/post-catalogue/demo-islanded-ramp/demo-islanded-ramp.1.spec.json
/tmp/DR-ISL-phase2b/post-catalogue/demo-islanded-ramp/demo-islanded-ramp.1.summary.json
/tmp/DR-ISL-phase2b/post-catalogue/demo-islanded-ramp/demo-islanded-ramp.1.ticks.jsonl
/tmp/DR-ISL-phase2b/post-catalogue/demo-islanded-ramp/demo-islanded-ramp.2.events.json
/tmp/DR-ISL-phase2b/post-catalogue/demo-islanded-ramp/demo-islanded-ramp.2.spec.json
/tmp/DR-ISL-phase2b/post-catalogue/demo-islanded-ramp/demo-islanded-ramp.2.summary.json
/tmp/DR-ISL-phase2b/post-catalogue/demo-islanded-ramp/demo-islanded-ramp.2.ticks.jsonl
/tmp/DR-ISL-phase2b/post-catalogue/demo-islanded-ramp/engine.log
/tmp/DR-ISL-phase2b/post-catalogue/results.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-100mw-fuel-cell-bess-diesel/command.log
/tmp/DR-ISL-phase2b/post-catalogue/scenario-100mw-fuel-cell-bess-diesel/engine.log
/tmp/DR-ISL-phase2b/post-catalogue/scenario-100mw-fuel-cell-bess-diesel/scenario-100mw-fuel-cell-bess-diesel.1.events.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-100mw-fuel-cell-bess-diesel/scenario-100mw-fuel-cell-bess-diesel.1.spec.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-100mw-fuel-cell-bess-diesel/scenario-100mw-fuel-cell-bess-diesel.1.summary.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-100mw-fuel-cell-bess-diesel/scenario-100mw-fuel-cell-bess-diesel.1.ticks.jsonl
/tmp/DR-ISL-phase2b/post-catalogue/scenario-100mw-fuel-cell-bess-diesel/scenario-100mw-fuel-cell-bess-diesel.2.events.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-100mw-fuel-cell-bess-diesel/scenario-100mw-fuel-cell-bess-diesel.2.spec.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-100mw-fuel-cell-bess-diesel/scenario-100mw-fuel-cell-bess-diesel.2.summary.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-100mw-fuel-cell-bess-diesel/scenario-100mw-fuel-cell-bess-diesel.2.ticks.jsonl
/tmp/DR-ISL-phase2b/post-catalogue/scenario-equinix-sj-1/command.log
/tmp/DR-ISL-phase2b/post-catalogue/scenario-equinix-sj-1/engine.log
/tmp/DR-ISL-phase2b/post-catalogue/scenario-equinix-sj-1/scenario-equinix-sj-1.1.events.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-equinix-sj-1/scenario-equinix-sj-1.1.spec.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-equinix-sj-1/scenario-equinix-sj-1.1.summary.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-equinix-sj-1/scenario-equinix-sj-1.1.ticks.jsonl
/tmp/DR-ISL-phase2b/post-catalogue/scenario-equinix-sj-1/scenario-equinix-sj-1.2.events.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-equinix-sj-1/scenario-equinix-sj-1.2.spec.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-equinix-sj-1/scenario-equinix-sj-1.2.summary.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-equinix-sj-1/scenario-equinix-sj-1.2.ticks.jsonl
/tmp/DR-ISL-phase2b/post-catalogue/scenario-hybrid-ai-100mw-addendum-i/command.log
/tmp/DR-ISL-phase2b/post-catalogue/scenario-hybrid-ai-100mw-addendum-i/engine.log
/tmp/DR-ISL-phase2b/post-catalogue/scenario-hybrid-ai-100mw-addendum-i/scenario-hybrid-ai-100mw-addendum-i.1.events.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-hybrid-ai-100mw-addendum-i/scenario-hybrid-ai-100mw-addendum-i.1.spec.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-hybrid-ai-100mw-addendum-i/scenario-hybrid-ai-100mw-addendum-i.1.summary.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-hybrid-ai-100mw-addendum-i/scenario-hybrid-ai-100mw-addendum-i.1.ticks.jsonl
/tmp/DR-ISL-phase2b/post-catalogue/scenario-hybrid-ai-100mw-addendum-i/scenario-hybrid-ai-100mw-addendum-i.2.events.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-hybrid-ai-100mw-addendum-i/scenario-hybrid-ai-100mw-addendum-i.2.spec.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-hybrid-ai-100mw-addendum-i/scenario-hybrid-ai-100mw-addendum-i.2.summary.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-hybrid-ai-100mw-addendum-i/scenario-hybrid-ai-100mw-addendum-i.2.ticks.jsonl
/tmp/DR-ISL-phase2b/post-catalogue/scenario-turbine-01/command.log
/tmp/DR-ISL-phase2b/post-catalogue/scenario-turbine-01/engine.log
/tmp/DR-ISL-phase2b/post-catalogue/scenario-turbine-01/scenario-turbine-01.1.events.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-turbine-01/scenario-turbine-01.1.spec.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-turbine-01/scenario-turbine-01.1.summary.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-turbine-01/scenario-turbine-01.1.ticks.jsonl
/tmp/DR-ISL-phase2b/post-catalogue/scenario-turbine-01/scenario-turbine-01.2.events.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-turbine-01/scenario-turbine-01.2.spec.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-turbine-01/scenario-turbine-01.2.summary.json
/tmp/DR-ISL-phase2b/post-catalogue/scenario-turbine-01/scenario-turbine-01.2.ticks.jsonl
/tmp/DR-ISL-phase2b/post-harness-1/baseline.ticks.jsonl
/tmp/DR-ISL-phase2b/post-harness-1/engine.log
/tmp/DR-ISL-phase2b/post-harness-1/informed.ticks.jsonl
/tmp/DR-ISL-phase2b/post-harness-1/probe.json
/tmp/DR-ISL-phase2b/post-harness-1/results.json
/tmp/DR-ISL-phase2b/post-harness-2/baseline.ticks.jsonl
/tmp/DR-ISL-phase2b/post-harness-2/engine.log
/tmp/DR-ISL-phase2b/post-harness-2/informed.ticks.jsonl
/tmp/DR-ISL-phase2b/post-harness-2/probe.json
/tmp/DR-ISL-phase2b/post-harness-2/results.json
/tmp/DR-ISL-phase2b/post_catalogue.log
/tmp/DR-ISL-phase2b/post_catalogue.py
/tmp/DR-ISL-phase2b/post_harness_1.log
/tmp/DR-ISL-phase2b/post_harness_2.log
/tmp/DR-ISL-phase2b/preview_root.html
/tmp/DR-ISL-phase2b/suite_capture.py
/tmp/DR-ISL-phase2b/suite_result.json
/tmp/DR-ISL-phase2b/targeted_tests.log
/tmp/DR-ISL-phase2b/write_report.py
```

STOP — end of Phase 2b. No Phase 3 or IMPL-ISL-12 implementation.

## Literal final repository status and HEAD
```text
?? tools/dr_isl/PHASE_2B_REPORT.md
1713cd0ff01ebc0f8e11f581a149713677db2a45
```
