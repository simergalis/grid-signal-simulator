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
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py
index 587d1d5..fa69800 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py
@@ -33,6 +33,8 @@ if TYPE_CHECKING:
 def compute_loading_setpoints(
     synchronised: "list[TurbineModule]",
     p_fleet: float,
+    *,
+    output_bounds: dict[str, tuple[float, float]] | None = None,
 ) -> tuple[list[float], float]:
     """Compute per-unit setpoints for units in A.  Pure — no side effects.
 
@@ -64,6 +66,12 @@ def compute_loading_setpoints(
         return [0.0] * len(synchronised), 0.0
 
     msl_i = [t.config.p_min_stable_frac * t.config.rated_mw for t in synchronised]
+    ceiling_i = [t.config.rated_mw for t in synchronised]
+    if output_bounds is not None:
+        # D10: the same sequential allocator can use this interval's physical
+        # ramp/policy envelope; no second turbine/diesel loading algorithm.
+        msl_i = [output_bounds[t.config.asset_id][0] for t in synchronised]
+        ceiling_i = [output_bounds[t.config.asset_id][1] for t in synchronised]
     sum_msl = sum(msl_i)
 
     # ── Sub-MSL: feasible band lower bound ───────────────────────────────────
@@ -96,7 +104,7 @@ def compute_loading_setpoints(
     for i, t in enumerate(synchronised):
         if _residual_s < 1e-9:
             break
-        _headroom_i   = t.config.rated_mw - msl_i[i]
+        _headroom_i   = ceiling_i[i] - msl_i[i]
         _fill_i       = min(_residual_s, _headroom_i)
         setpoints[i] += _fill_i
         _residual_s  -= _fill_i
@@ -111,7 +119,7 @@ def compute_loading_setpoints(
         unclamped: list[int] = []
         for i, t in enumerate(synchronised):
             lo = msl_i[i]
-            hi = t.config.rated_mw
+            hi = ceiling_i[i]
             if setpoints[i] < lo - 1e-9:
                 residual += lo - setpoints[i]   # positive: we under-allocated
                 setpoints[i] = lo
@@ -135,10 +143,20 @@ def compute_loading_setpoints(
 # Apply loading to SYNCHRONISED units (has side effects on output_mw)
 # ---------------------------------------------------------------------------
 
+def ramp_limited_output(turbine: "TurbineModule", target_mw: float, dt_seconds: float) -> float:
+    """Pure prediction of the existing loading step, also used to apply it."""
+    delta = target_mw - turbine.output_mw()
+    max_step = turbine.config.r_asset_mw_per_s * dt_seconds
+    step = max(-max_step, min(max_step, delta))
+    return turbine.output_mw() + step
+
+
 def apply_loading(
     synchronised: "list[TurbineModule]",
     p_fleet: float,
     dt_seconds: float,
+    *,
+    output_bounds: dict[str, tuple[float, float]] | None = None,
 ) -> float:
     """Compute setpoints and advance SYNCHRONISED unit outputs toward them.
 
@@ -149,12 +167,11 @@ def apply_loading(
     No stored state — calling twice with the same inputs is idempotent for the
     setpoint computation, though output_mw will advance twice.
     """
-    setpoints, sub_msl_surplus_mw = compute_loading_setpoints(synchronised, p_fleet)
+    setpoints, sub_msl_surplus_mw = compute_loading_setpoints(
+        synchronised, p_fleet, output_bounds=output_bounds,
+    )
     for t, sp in zip(synchronised, setpoints):
-        delta = sp - t.output_mw()
-        max_step = t.config.r_asset_mw_per_s * dt_seconds
-        step = max(-max_step, min(max_step, delta))
-        t.set_output(t.output_mw() + step)
+        t.set_output(ramp_limited_output(t, sp, dt_seconds))
     return sub_msl_surplus_mw
 
 
@@ -183,10 +200,7 @@ def apply_loading_targets(
                 float(targets_mw.get(turbine.config.asset_id, minimum)),
             ),
         )
-        delta = target - turbine.output_mw()
-        max_step = turbine.config.r_asset_mw_per_s * dt_seconds
-        step = max(-max_step, min(max_step, delta))
-        turbine.set_output(turbine.output_mw() + step)
+        turbine.set_output(ramp_limited_output(turbine, target, dt_seconds))
     return sub_msl_surplus_mw
 
 
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py
index 8a7cf6c..adc2ab9 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py
@@ -39,6 +39,7 @@ class PowerSourceType(str, Enum):
     BESS         = "bess"
     TURBINE      = "turbine"
     FUEL_CELL    = "fuel_cell"
+    DIESEL       = "diesel"
 
 
 class AuthorityTier(str, Enum):
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
index d253eb5..758ef61 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -29,7 +29,10 @@ from .asset_modules import (
     TurbineState,
 )
 from .fuel_cell_module import BlockFuelCellFleet, FuelCellModule
-from .loading import apply_loading, apply_loading_targets, ramp_capability
+from .loading import (
+    apply_loading, apply_loading_targets, compute_loading_setpoints,
+    ramp_capability, ramp_limited_output,
+)
 from .contingency import BessSnapshot, FuelCellSnapshot, PlantState, TurbineSnapshot, evaluate_contingency
 from .kube_demand import KubeDemandAgent, KubeGridState
 from .lead_time_observations import LeadTimeObservationRecorder
@@ -780,6 +783,7 @@ def _cost_ranked_dispatch_allocations(
     bess_available_mw: float,
     turbine_available_mw: float,
     fuel_cell_available_mw: float,
+    diesel_available_mw: float = 0.0,
 ) -> dict[str, float]:
     """Allocate discretionary demand using the shared marginal-cost ranking.
 
@@ -823,12 +827,29 @@ def _cost_ranked_dispatch_allocations(
             cost_basis_note="catalogue: fuel_cell_ppa_rate_mwh",
         ),
     ]
+    if diesel_available_mw > 0.0:
+        sources.append(_PowerSource(
+            source_id="diesel-fleet",
+            source_type=_PowerSourceType.DIESEL,
+            dispatchable=True,
+            counts_toward_reserve=True,
+            # PROPOSED_HERE, D10 fallback: no catalogue diesel price exists.
+            # Rank-only infinity (not a fuel price): diesel is last on rise /
+            # first on back-down because diesel fuel/MWh exceeds gas and FC.
+            # Source: approved DR-2026-10-20-ISLAND-COLLAPSE D10.
+            marginal_cost_mwh=math.inf,
+            response_latency_class=_ResponseLatencyClass.RAMP_LIMITED,
+            authority_tier=_AuthorityTier.AUTONOMOUS,
+            available_mw=diesel_available_mw,
+            cost_basis_note="D10: ranking-only last; no catalogue diesel price",
+        ))
     ranked = _PowerRanker().rank(sources).ranked_sources
     remaining_mw = max(0.0, demand_mw)
     allocations = {
         "bess-fleet": 0.0,
         "turbine-fleet": 0.0,
         "fuel-cell-fleet": 0.0,
+        "diesel-fleet": 0.0,
     }
     for source in ranked:
         if remaining_mw <= 1e-9:
@@ -1672,6 +1693,44 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         )
         for t in _truly_sync_units
     )
+    _diesel_loading_bounds = None
+    if state.diesel_units:
+        # D10: one ramp calculation/one sequential loading allocator. Preserve
+        # the existing controller/baseload policy as a physical floor, rather
+        # than allocating diesel against turbine MW already held by that policy.
+        _diesel_loading_bounds = {}
+        _policy_targets = dict(getattr(state, "_preload_targets_mw", {}) or {})
+        _explicit_policy_targets = bool(_policy_targets)
+        if not _policy_targets and _generation_baseload_active:
+            _base_setpoints, _ = compute_loading_setpoints(
+                _truly_sync_units,
+                max(0.0, _generation_baseload_target_mw - _uncontrolled_on_bus_mw - _msl_held_mw),
+            )
+            _policy_targets = {
+                t.config.asset_id: sp for t, sp in zip(_truly_sync_units, _base_setpoints)
+            }
+        for _t in _truly_sync_units:
+            _minimum = _t.config.p_min_stable_frac * _t.config.rated_mw
+            _lo = ramp_limited_output(_t, _minimum, dt_seconds)
+            _hi = ramp_limited_output(_t, _t.config.rated_mw, dt_seconds)
+            if _explicit_policy_targets or _t.config.asset_id in _policy_targets:
+                # apply_loading_targets holds omitted units at minimum too.
+                _target = max(_minimum, min(_t.config.rated_mw, _policy_targets.get(_t.config.asset_id, _minimum)))
+                _lo = ramp_limited_output(_t, _target, dt_seconds)
+                if _explicit_policy_targets or not _generation_peak_following:
+                    _hi = _lo
+            _diesel_loading_bounds[_t.config.asset_id] = (_lo, max(_lo, _hi))
+        _msl_held_mw = sum(
+            ramp_limited_output(t, t.config.p_min_stable_frac * t.config.rated_mw, dt_seconds)
+            for t in _unloading_units
+        )
+        _turbine_must_run_mw = (
+            _uncontrolled_on_bus_mw + _msl_held_mw
+            + sum(bounds[0] for bounds in _diesel_loading_bounds.values())
+        )
+        _turbine_incremental_available_mw = sum(
+            hi - lo for lo, hi in _diesel_loading_bounds.values()
+        )
     # Economic BESS availability must account for both the instantaneous power
     # ceiling and energy that can actually be delivered during this tick.  If
     # only the power ceiling is ranked, an empty/near-empty BESS reserves cheap
@@ -1721,18 +1780,47 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
             min(_physical_ceiling_mw, _normal_energy_ceiling_mw)
         )
     _bess_available_mw = sum(_bess_normal_dispatch_ceilings_mw)
+    _diesel_dispatch_floor_mw = 0.0
+    _diesel_dispatch_headroom_mw = 0.0
+    if state.diesel_units:
+        state.diesel_fleet_coordinator.advance_units(
+            sim_time, dt_seconds, dispatch_controlled=True,
+        )
+        _diesel_dispatch_floor_mw = sum(t.dispatch_floor_mw for t in state.diesel_units)
+        _diesel_dispatch_headroom_mw = sum(
+            t.dispatch_ceiling_mw - t.dispatch_floor_mw for t in state.diesel_units
+        )
+    # D10: diesel must not be hidden behind the old primary-only dispatch
+    # intent ceiling. Keep the droop/frequency calculation unchanged; the one
+    # allocator's resource envelopes bound the full physical dispatch request.
+    _allocation_demand_mw = (
+        max(0.0, p_dispatch_required_mw + _droop_correction_mw)
+        if state.diesel_units else _p_dispatch_droop_mw
+    )
     _economic_demand_mw = max(
         0.0,
-        _p_dispatch_droop_mw
+        _allocation_demand_mw
         - fuel_cell_output_mw
         - _turbine_must_run_mw,
+        # diesel's synchronized minimum / immutable unloading tail is must-run.
     )
+    _economic_demand_mw = max(0.0, _economic_demand_mw - _diesel_dispatch_floor_mw)
     _economic_allocations = _cost_ranked_dispatch_allocations(
         _economic_demand_mw,
         bess_available_mw=_bess_available_mw,
         turbine_available_mw=_turbine_incremental_available_mw,
         fuel_cell_available_mw=0.0,
-    )
+        diesel_available_mw=_diesel_dispatch_headroom_mw,
+    )
+    _diesel_dispatch_target_mw = _diesel_dispatch_floor_mw + _economic_allocations["diesel-fleet"]
+    _diesel_extra_mw = _economic_allocations["diesel-fleet"]
+    for _diesel in state.diesel_units:
+        _extra = min(
+            _diesel_extra_mw,
+            _diesel.dispatch_ceiling_mw - _diesel.dispatch_floor_mw,
+        )
+        _diesel.apply_dispatch_target(_diesel.dispatch_floor_mw + _extra)
+        _diesel_extra_mw -= _extra
     _planned_bess_setpoint_mw = _economic_allocations["bess-fleet"]
     _thermal_dispatch_target_mw = (
         _turbine_must_run_mw + _economic_allocations["turbine-fleet"]
@@ -1745,7 +1833,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         # replacing conventional turbine generation during a peak.
         _conventional_following_target_mw = max(
             0.0,
-            _p_dispatch_droop_mw - fuel_cell_output_mw,
+            _p_dispatch_droop_mw - fuel_cell_output_mw - _diesel_dispatch_target_mw,
         )
         if _generation_peak_following:
             _thermal_dispatch_target_mw = max(
@@ -1779,7 +1867,8 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         )
     else:
         _sub_msl_surplus_mw = apply_loading(
-            _truly_sync_units, _p_sync_fleet_mw, dt_seconds
+            _truly_sync_units, _p_sync_fleet_mw, dt_seconds,
+            output_bounds=_diesel_loading_bounds,
         )
 
     # Addendum H Phase 1: account for the completed interval after loading has
@@ -1883,7 +1972,9 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         p_dispatch_required_mw
         - _post_loading_turbine_output_mw
         - fuel_cell_output_mw,
+        # D10: the single plan has already credited current diesel delivery.
     )
+    _physical_bess_shortfall_mw = max(0.0, _physical_bess_shortfall_mw - _diesel_dispatch_target_mw)
     _emergency_release_authorized = False
     if _normal_bess_energy_exhausted:
         _grid_emergency_support_mw = (
@@ -1904,7 +1995,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
             # Diesel coordination runs after BESS arbitration.  Use measured
             # delivery from the preceding interval when deciding whether the
             # retained reserve must be released.
-            - state._prev_diesel_output_mw
+            - (0.0 if state.diesel_units else state._prev_diesel_output_mw)
             - _grid_emergency_support_mw,
         )
         _emergency_release_authorized = _emergency_gap_mw > 0.0
@@ -1944,15 +2035,15 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         # against an actual shortfall; negative values preserve its existing
         # surplus-absorption path so fixed FC overproduction charges the BESS.
         # tick() removes measured turbine output exactly once.
-        p_dispatch_required_mw - fuel_cell_output_mw,
+        p_dispatch_required_mw - fuel_cell_output_mw - _diesel_dispatch_target_mw,
         dt_seconds,
         bess_dispatch_target_mw=_effective_bess_setpoint_mw,
         bess_dispatch_ceilings_mw=_bess_dispatch_ceilings_mw,
         bess_soc_floors_mwh=_bess_soc_floors_mwh,
     )
-    # Coordinate diesel from the measured residual after primary source
-    # arbitration. Diesel must not reduce the BESS planner's input and then
-    # leave the same MW in the turbine dispatch demand.
+    # DR D10-gap: this allocation's achieved pre-diesel residual includes the
+    # emergency BESS release and supersedes the availability-based gap. Compute
+    # it once, after non-diesel delivery, for coordination and deficit reporting.
     _gap_before_diesel_mw = max(
         0.0,
         p_dispatch_required_mw
@@ -1961,11 +2052,17 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         - fuel_cell_output_mw,
     )
     diesel_enabled = bool(state.diesel_units)
-    _diesel_snapshot = state.diesel_fleet_coordinator.step(
-        gap_mw=_gap_before_diesel_mw if diesel_enabled else 0.0,
-        sim_time=sim_time,
-        dt_seconds=dt_seconds,
-    )
+    if diesel_enabled:
+        state.diesel_fleet_coordinator.step(
+            gap_mw=_gap_before_diesel_mw, sim_time=sim_time,
+            dt_seconds=dt_seconds, advance_units=False, consume_fuel=False,
+        )
+        state.diesel_fleet_coordinator.record_dispatch_fuel(dt_seconds)
+        _diesel_snapshot = state.diesel_fleet_coordinator.snapshot()
+    else:
+        _diesel_snapshot = state.diesel_fleet_coordinator.step(
+            gap_mw=0.0, sim_time=sim_time, dt_seconds=dt_seconds,
+        )
     diesel_output_mw = float(_diesel_snapshot.output_mw)
     state._prev_diesel_output_mw = diesel_output_mw if diesel_enabled else 0.0
 
