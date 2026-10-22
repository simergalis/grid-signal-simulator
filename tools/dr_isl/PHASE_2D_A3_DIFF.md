diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
index 59a2f49..1b2b974 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
@@ -1357,6 +1357,7 @@ class DieselModule(AssetModule):
     _resuming_from_unloading: bool = False
     _resume_start_output_mw: float = 0.0
     _resume_elapsed_s: float = 0.0
+    _dispatch_ceiling_mw: Optional[float] = field(default=None, init=False)
 
     def __post_init__(self) -> None:
         if self.config.rated_mw <= 0.0:
@@ -1444,7 +1445,7 @@ class DieselModule(AssetModule):
         self._current_output_mw = 0.0
         self._resuming_from_unloading = False
 
-    def advance(self, sim_time: float, dt_seconds: float) -> None:
+    def advance(self, sim_time: float, dt_seconds: float, *, dispatch_controlled: bool = False) -> None:
         """Advance startup, synchronization output, or controlled unloading."""
         if dt_seconds < 0.0:
             raise ValueError("diesel dt_seconds must not be negative")
@@ -1464,12 +1465,14 @@ class DieselModule(AssetModule):
                     self._current_output_mw = (
                         self.config.rated_mw * self.config.f_block
                     )
+                    self._dispatch_ceiling_mw = self._current_output_mw
                 else:
                     self.state = DieselState.FAILED_START
                     self._current_output_mw = 0.0
             return
 
         if self.state == DieselState.SYNCHRONISED:
+            _delivered_before_advance = self._current_output_mw
             if self._resuming_from_unloading:
                 self._resume_elapsed_s += dt_seconds
                 duration = self.config.residual_ramp_s
@@ -1496,6 +1499,11 @@ class DieselModule(AssetModule):
                     base_mw
                     + (self.config.rated_mw - base_mw) * fraction
                 )
+            self._dispatch_ceiling_mw = self._current_output_mw
+            if dispatch_controlled:
+                # D10: advance machine capability, not delivered power.  A
+                # subsequent accepted stop must capture actual dispatched MW.
+                self._current_output_mw = _delivered_before_advance
             return
 
         if self.state == DieselState.UNLOADING:
@@ -1514,6 +1522,35 @@ class DieselModule(AssetModule):
     def output_mw(self) -> float:
         return self._current_output_mw
 
+    @property
+    def dispatch_floor_mw(self) -> float:
+        if self.state == DieselState.UNLOADING:
+            # User-approved D10 exception: preserve the tail below 30%.
+            return self.output_mw()
+        if self.state == DieselState.SYNCHRONISED:
+            # PROPOSED_HERE, D10: NFPA 110 §8.4.2 / Annex A test-load
+            # reference, used as a wet-stacking proxy for continuous load;
+            # this is a modelling minimum, not an NFPA run requirement.
+            return 0.30 * self.config.rated_mw
+        return 0.0
+
+    @property
+    def dispatch_ceiling_mw(self) -> float:
+        if self.state != DieselState.SYNCHRONISED:
+            return self.dispatch_floor_mw
+        available = (
+            self.output_mw() if self._dispatch_ceiling_mw is None
+            else self._dispatch_ceiling_mw
+        )
+        return max(self.dispatch_floor_mw, min(self.config.rated_mw, available))
+
+    def apply_dispatch_target(self, target_mw: float) -> None:
+        """D10: sole economic output application; unloading stays physical."""
+        if self.state == DieselState.SYNCHRONISED:
+            self._current_output_mw = max(
+                self.dispatch_floor_mw, min(self.dispatch_ceiling_mw, target_mw),
+            )
+
     def command_stop(self, sim_time: float) -> Optional[str]:
         """Begin controlled unloading, enforcing the diesel minimum run time."""
         self._last_known_sim_time = sim_time
@@ -1535,6 +1572,9 @@ class DieselModule(AssetModule):
         if self.state != DieselState.UNLOADING:
             return
         self.state = DieselState.SYNCHRONISED
+        # D10: resuming exposes the current tail, not a stale pre-unload
+        # capacity. advance() then raises capability on the existing ramp.
+        self._dispatch_ceiling_mw = self._current_output_mw
         self._resuming_from_unloading = True
         self._resume_start_output_mw = self._current_output_mw
         self._resume_elapsed_s = 0.0
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py
index 2a63a3a..5e8e365 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py
@@ -112,12 +112,12 @@ class DieselFleetCoordinator:
 
     @property
     def output_mw(self) -> float:
-        """Aggregate measured output from synchronised diesel units."""
+        """IMPL-ISL-14: aggregate every breaker-closed unit, including unloading."""
         return sum(
             (
                 unit.output_mw()
                 for unit in self.diesel_units
-                if unit.state == DieselState.SYNCHRONISED
+                if unit.is_on_bus
             ),
             0.0,
         )
@@ -184,6 +184,8 @@ class DieselFleetCoordinator:
         dt_seconds: float,
         *,
         success_overrides: Optional[Mapping[str, bool]] = None,
+        advance_units: bool = True,
+        consume_fuel: bool = True,
     ) -> DieselFleetSnapshot:
         """Advance units and coordinate one synthetic-gap fleet tick.
 
@@ -195,9 +197,10 @@ class DieselFleetCoordinator:
             raise ValueError("diesel fleet dt_seconds must not be negative")
         self._last_sim_time = sim_time
 
-        for unit in self.diesel_units:
-            unit.advance(sim_time, dt_seconds)
-        self._consume_fuel(dt_seconds)
+        if advance_units:
+            self.advance_units(sim_time, dt_seconds)
+        if consume_fuel:
+            self._consume_fuel(dt_seconds)
         self._complete_cooldown_if_ready(sim_time)
 
         if gap_mw > 0.0:
@@ -227,15 +230,24 @@ class DieselFleetCoordinator:
                     success_overrides or {},
                 )
         else:
-            if any(unit.state == DieselState.UNLOADING for unit in self.diesel_units):
-                self._restore_elapsed_s += dt_seconds
-            elif any(unit.state == DieselState.SYNCHRONISED for unit in self.diesel_units):
+            if any(unit.state == DieselState.SYNCHRONISED for unit in self.diesel_units):
                 self._begin_unloading(sim_time)
+            # IMPL-ISL-15: a refused stop is not unloading/restoration time.
+            if (
+                any(unit.state == DieselState.UNLOADING for unit in self.diesel_units)
+                and not any(unit.state == DieselState.SYNCHRONISED for unit in self.diesel_units)
+            ):
                 self._restore_elapsed_s += dt_seconds
+            else:
+                self._restore_elapsed_s = 0.0
 
             if (
                 self._restore_elapsed_s >= self.restore_hold_s
                 and any(unit.state == DieselState.UNLOADING for unit in self.diesel_units)
+                and all(
+                    unit._unload_elapsed_s >= unit.config.cooldown_s
+                    for unit in self.diesel_units if unit.state == DieselState.UNLOADING
+                )
             ):
                 self._finish_unloading(sim_time)
 
@@ -360,13 +372,22 @@ class DieselFleetCoordinator:
         self.insufficient_start_alert_fired = False
         self.insufficient_start_alerts.clear()
 
+    def advance_units(self, sim_time: float, dt_seconds: float, *, dispatch_controlled: bool = False) -> None:
+        """Advance lifecycle once; live D10 dispatch separately records delivery."""
+        for unit in self.diesel_units:
+            unit.advance(sim_time, dt_seconds, dispatch_controlled=dispatch_controlled)
+
+    def record_dispatch_fuel(self, dt_seconds: float) -> None:
+        """D10: use this interval's achieved, not pre-allocation, load fraction."""
+        self._consume_fuel(dt_seconds)
+
     def _consume_fuel(self, dt_seconds: float) -> None:
         dt_hours = dt_seconds / 3600.0
         if dt_hours <= 0.0:
             return
         consumed_gal = 0.0
         for unit in self.diesel_units:
-            if unit.state != DieselState.SYNCHRONISED:
+            if not unit.is_on_bus:  # IMPL-ISL-14: the unloading tail burns fuel.
                 continue
             if unit.config.rated_mw <= 0.0:
                 continue
