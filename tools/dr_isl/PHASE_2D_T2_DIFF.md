diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
index 758ef61..60596e0 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -1693,8 +1693,15 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         )
         for t in _truly_sync_units
     )
-    _diesel_loading_bounds = None
     if state.diesel_units:
+        state.diesel_fleet_coordinator.advance_units(
+            sim_time, dt_seconds, dispatch_controlled=True,
+        )
+    _diesel_on_bus = any(unit.is_on_bus for unit in state.diesel_units)
+    _diesel_loading_bounds = None
+    if _diesel_on_bus:
+        # DR D10 / D10-gap, T2: an off-bus fleet contributes no dispatch terms.
+        # Preserve the pre-D10 primary envelopes until diesel is actually on bus.
         # D10: one ramp calculation/one sequential loading allocator. Preserve
         # the existing controller/baseload policy as a physical floor, rather
         # than allocating diesel against turbine MW already held by that policy.
@@ -1783,9 +1790,6 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     _diesel_dispatch_floor_mw = 0.0
     _diesel_dispatch_headroom_mw = 0.0
     if state.diesel_units:
-        state.diesel_fleet_coordinator.advance_units(
-            sim_time, dt_seconds, dispatch_controlled=True,
-        )
         _diesel_dispatch_floor_mw = sum(t.dispatch_floor_mw for t in state.diesel_units)
         _diesel_dispatch_headroom_mw = sum(
             t.dispatch_ceiling_mw - t.dispatch_floor_mw for t in state.diesel_units
@@ -1795,7 +1799,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     # allocator's resource envelopes bound the full physical dispatch request.
     _allocation_demand_mw = (
         max(0.0, p_dispatch_required_mw + _droop_correction_mw)
-        if state.diesel_units else _p_dispatch_droop_mw
+        if _diesel_on_bus else _p_dispatch_droop_mw
     )
     _economic_demand_mw = max(
         0.0,
@@ -1995,7 +1999,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
             # Diesel coordination runs after BESS arbitration.  Use measured
             # delivery from the preceding interval when deciding whether the
             # retained reserve must be released.
-            - (0.0 if state.diesel_units else state._prev_diesel_output_mw)
+            - (0.0 if _diesel_on_bus else state._prev_diesel_output_mw)
             - _grid_emergency_support_mw,
         )
         _emergency_release_authorized = _emergency_gap_mw > 0.0
