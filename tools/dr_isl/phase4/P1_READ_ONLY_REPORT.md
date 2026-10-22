# Phase 4 second resumption — P1 read-only conditions / approval needed

Application is at ae49aaa. No new test or simulation has been run in this second resumption. No commit made.

## Complete existing release conditions

- Coverage state is COVERED_WITH_SHED or CANNOT_CARRY (simulation_core.py:770-773).
- Sustained risk condition is met after update(risk_state, dt_seconds), using configured contingency_release_confirm_s (simulation_core.py:348-350,774,783-784; commitment.py:120-130).
- Episode is armed (simulation_core.py:301,779-780,785); a complete COVERED tick rearms; successful release disarms at805.
- Pending-start register is empty (simulation_core.py:786).
- An OFFLINE hot-standby turbine passes the shared start predicate after only the reserve label is temporarily cleared and restored (simulation_core.py:629-678).
- Choose the first such unit in existing thermal/roster order (simulation_core.py:789-796).
- Clear label and command_start; only STARTING success is recorded; rejection restores reserve label (simulation_core.py:796-805).

## Distinction requiring clarification

The existing unit helper (_releasable_hot_standby_turbines) answers whether a machine passes unchanged interlocks under explicit release authority. The release function additionally requires a currently confirmed bad N-1 state, an armed episode and an empty pending-start register. Those are not checked by the unit helper.

Candidate 69350a3 reuses the unit helper (no guard copy), but does not gate reserve population on a current confirmed N-1 episode. Candidate 85595a8 predates C2(c). Both are kept in stashes; neither is applied to main.

## Existing focused-test blocker (imported evidence, not a rerun)

All 12 new tests passed. The complete focused batch had 50 passed, 1 failed. The failure is tests/test_dr_isl_phase2c.py::test_tc_isl_18_floor_warning_is_diagnostic_only[10.0-0], line54: expected1.4583333333333333MWh, observed6.25MWh. See PHASE_4_RESUMED_FOCUSED.txt/.xml.

The build-only snapshot records d2r_bridge, hot_standby_release, gt-hot-01, wait0s, start300s, BESS30MW/60MWh, depth0MWh, diesel1.4583333333333333MWh, D2-r6.25MWh and build_warnings=[]. No physical step was taken in that snapshot. See PHASE_4_RESUMED_BUILD_ONLY.json.

This is not an explicit zero-floor or unconditional-release assertion, so the existing test-update allowance does not clearly cover it. It was left unchanged.

P2 GPU-order diagnosis, P3 acceptance, P4 full suite and P5 tracking have not started for this second resumption. P6 commits remain gated. Old full-suite results are not a result for this candidate.

## Literal base-source excerpts

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:629–645

```python
629: def _offline_turbine_roster(
630:     turbines: list[TurbineModule],
631: ) -> list[TurbineModule]:
632:     """Return offline turbines in hot → warm → cold, then roster order."""
633:     roster_index = {id(turbine): index for index, turbine in enumerate(turbines)}
634:     candidates = [
635:         turbine
636:         for turbine in turbines
637:         if turbine.state == TurbineState.OFFLINE
638:     ]
639:     return sorted(
640:         candidates,
641:         key=lambda turbine: (
642:             _STANDBY_THERMAL_PRIORITY[turbine.thermal_state],
643:             roster_index[id(turbine)],
644:         ),
645:     )
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:664–678

```python
664: def _releasable_hot_standby_turbines(
665:     turbines: list[TurbineModule], sim_time: float,
666: ) -> list[TurbineModule]:
667:     """Evaluate unchanged interlocks under the existing explicit release authority."""
668:     candidates = []
669:     for turbine in _offline_turbine_roster(turbines):
670:         if turbine.config.hot_standby:
671:             turbine.config.hot_standby = False
672:             try:
673:                 eligible, _ = turbine.start_eligibility(sim_time)
674:             finally:
675:                 turbine.config.hot_standby = True
676:             if eligible:
677:                 candidates.append(turbine)
678:     return candidates
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:757–826

```python
757: def _release_hot_standby_for_contingency(
758:     state: SimulationState,
759:     coverage: ContingencyCoverage,
760:     *,
761:     sim_time: float,
762:     dt_seconds: float,
763: ) -> ContingencyReleaseAlert | None:
764:     """Release at most one hot standby after sustained real N-1 risk.
765: 
766:     This is intentionally not part of evaluate_commitment().  The ordinary
767:     commitment path must continue to exclude hot-standby units from its
768:     offline candidates; this path is the inverse, contingency-only action.
769:     """
770:     risk_state = coverage.state in (
771:         ContingencyState.COVERED_WITH_SHED,
772:         ContingencyState.CANNOT_CARRY,
773:     )
774:     state._contingency_release_cond.update(risk_state, dt_seconds)
775: 
776:     # One complete COVERED tick re-arms the episode.  A bad condition never
777:     # re-arms itself, even after the first released unit reaches STARTING or
778:     # SYNCHRONISED.
779:     if coverage.state == ContingencyState.COVERED:
780:         state._contingency_release_armed = True
781: 
782:     if (
783:         not risk_state
784:         or not state._contingency_release_cond.met
785:         or not state._contingency_release_armed
786:         or not state._pending_start.is_empty
787:     ):
788:         return None
789: 
790:     hot_standby_units = _releasable_hot_standby_turbines(state.turbines, sim_time)
791:     if not hot_standby_units:
792:         return None
793: 
794:     turbine = hot_standby_units[0]
795:     before_state = turbine.state
796:     turbine.config.hot_standby = False
797:     turbine.command_start(sim_time)
798:     if turbine.state != TurbineState.STARTING:
799:         # Preserve the reserve label when the turbine's own start guards reject
800:         # the command; no release was actually made and a later tick may retry.
801:         turbine.config.hot_standby = True
802:         return None
803: 
804:     state._pending_start.record_start(turbine.config.asset_id, sim_time)
805:     state._contingency_release_armed = False
806:     _record_turbine_transition(
807:         state,
808:         turbine,
809:         sim_time=sim_time,
810:         action="release",
811:         source="automatic_contingency",
812:         reason="automatic contingency cascade release",
813:         from_state=before_state,
814:         to_state=turbine.state,
815:         controller_approved=(
816:             True
817:             if getattr(state, "_commitment_mode", "baseline") == "informed"
818:             else None
819:         ),
820:     )
821:     return ContingencyReleaseAlert(
822:         turbine_id=turbine.config.asset_id,
823:         coverage_state=coverage.state.value,
824:         shed_mw=float(coverage.shed_required_mw),
825:         fires_at_sim_time=sim_time,
826:     )
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py:1057–1067

```python
1057:     def start_eligibility(self, sim_time: float) -> tuple[bool, str]:
1058:         """DR D2 / IMPL-ISL-5: the single, unchanged turbine start interlock."""
1059:         if self.config.hot_standby:
1060:             return False, "hot_standby"
1061:         if self.state != TurbineState.OFFLINE:
1062:             return False, "state"
1063:         if self.config.min_down_enabled and not math.isnan(self._stop_time_s):
1064:             elapsed = sim_time - self._stop_time_s
1065:             if elapsed < self.config.t_min_down_s:
1066:                 return False, "min_down"
1067:         return True, "eligible"
```

### attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py:103–130

```python
103: class SustainedCondition:
104:     """Durable hysteresis timer for commit and decommit conditions.
105: 
106:     Tracks how long a condition has been continuously true.  Resets to 0.0
107:     on the first tick the condition is false.
108: 
109:     Design
110:     ------
111:     sustained_s  : accumulated seconds the condition has been continuously true.
112:     threshold_s  : minimum duration required before met is True.
113: 
114:     Not frozen — evaluate_commitment() mutates sustained_s per tick.
115:     No I/O, no wall clock; the caller passes dt_s and the boolean predicate.
116:     """
117:     sustained_s: float = 0.0
118:     threshold_s: float = 0.0
119: 
120:     def update(self, condition_true: bool, dt_s: float) -> None:
121:         """Advance by dt_s when the condition holds; reset to 0.0 otherwise."""
122:         if condition_true:
123:             self.sustained_s = self.sustained_s + dt_s
124:         else:
125:             self.sustained_s = 0.0
126: 
127:     @property
128:     def met(self) -> bool:
129:         """True when the condition has been sustained ≥ threshold_s seconds."""
130:         return self.sustained_s >= self.threshold_s
```
