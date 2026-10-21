# DR-2026-10-20-ISLAND-COLLAPSE — Phase 2d DESIGN STOP

Status: **STOP at 2d.0, before application changes.**

Base inspected: `01ce05304b77192c44066e97f1783c98d6647d14`.

Package prefix P:
`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`.

Scratch prefix T: `/tmp/DR-ISL-phase2d/`.

## STOP condition and decision required

The approved instruction contains both:

> While a diesel unit is on bus (SYNCHRONISED or UNLOADING), its output is a dispatch variable between a minimum load and rated output.
> Minimum load = 0.30 × rated.

and:

> The configured unloading ramp must complete at its configured rate.

The existing unloading ramp reaches zero while the unit remains UNLOADING and on bus until the coordinator opens its breaker:

- `P/core/asset_modules.py:1404–1406`: `is_on_bus` includes SYNCHRONISED and UNLOADING.
- `:1501–1512`: `output = unload_start_output * (1 - min(1, unload_elapsed / cooldown_s))`, floored at zero.
- `:1528–1530`: accepted stop captures the current output and resets unloading elapsed time.
- `:1542–1550`: `complete_unloading()` changes state to OFFLINE and output to zero.
- `P/core/models.py:986–988`: default minimum run 900 s, minimum down 300 s, cooldown 300 s.

For a 20 MW unit, the requested minimum is 6 MW. The real existing ramp falls below 6 MW before its configured duration ends. Clamping it to 6 MW changes that ramp; opening the breaker at the threshold shortens it. Keeping the ramp unchanged violates the literal D10 minimum while the unit is UNLOADING.

This is a conflict between the requested D10 operating envelope and the protected shutdown/cooldown trajectory, not a failed full-scenario result. Hard constraint 4 requires a design report rather than choosing a new shutdown interpretation.

**Recommended clarification, NOT approved or implemented:** apply the 30% continuous-operation proxy only to SYNCHRONISED units. Treat UNLOADING as the existing ramp-constrained on-bus tail, allowed below 30%, counted in fleet power and fuel until its normal breaker opening. It would enter the same site balance as other physically constrained output, not a second diesel balancing path.

Alternative: keep the 30% lower bound throughout UNLOADING, but explicitly amend the shutdown trajectory/ramp requirement. No alternative ramp or timing constant is chosen here.

## 2d.0 — current design, literal source evidence

### Output writers and lifecycle

`P/core/asset_modules.py`:

| Lines | Current behavior |
|---|---|
| 1453–1466 | Successful startup enters SYNCHRONISED, records run start, and writes `rated_mw * f_block`. |
| 1470–1498 | SYNCHRONISED advance writes either a resume-to-rated ramp or the block-plus-residual-ramp output. |
| 1501–1512 | UNLOADING advance writes the configured linear trajectory to zero. |
| 1514–1515 | `output_mw()` returns `_current_output_mw`; no economic setpoint is read here. |
| 1517–1531 | `command_stop()` enforces minimum run, then enters UNLOADING and captures its initial MW. |
| 1542–1550 | `complete_unloading()` opens the breaker and writes zero. |

The coordinator advances units and consumes fuel before evaluating the current gap (`P/core/diesel_fleet.py:198–201`). It owns start/stop decisions:

- Positive-gap debounce and episode creation: `:203–214`.
- Start/resume branch: `:219–228`.
- Restoration counter and unloading completion: `:229–240`.
- Stop and completion delegation: `:328–335`.

### Dispatch, generation and curtailment

1. `P/core/simulation_core.py:777–839`: `_cost_ranked_dispatch_allocations()` constructs BESS, turbine and fuel-cell sources, calls the shared ranker, and allocates remaining MW in ranked order.
2. `:1660–1679`: turbine minimum-stable/must-run output is separated from incremental capacity.
3. `:1689–1722`: physical and normal BESS ceilings are resolved using the existing reserve floor.
4. `:1723–1740`: demand net of measured FC and turbine must-run output enters the economic helper; its BESS and turbine allocations set their targets.
5. `:1943–1952`: the arbitrator applies primary-source/BESS dispatch.
6. `:1953–1968`: the residual excluding diesel is sent to `diesel_fleet_coordinator.step()`.
7. `:1969–1970`: its measured output becomes `diesel_output_mw` and previous-tick diesel output.
8. `:2994–2999`: diesel is added to turbine, BESS, FC and renewable generation.
9. `:3014–3035`: islanded achieved surplus and the existing dump-response delay determine the explicit curtailment sink.
10. `:3460`: post-trip generation reconciliation also includes diesel; `:3537` supplies achieved generation to the balance terms.

Current ranker sorting is ascending `marginal_cost_mwh` (`P/core/power_source_priority.py:234`). `PowerSourceType` has no DIESEL member (`:33–41`).

### Cost table

The authoritative catalogue is `P/gridsignal_parameters.json` (`P/core/site_parameters.py:149–150`). The existing helper reads:

| Key location in catalogue | Runtime printed value, USD/MWh |
|---|---:|
| `turbine_variable_per_mwh`, line 1321 | 55.0 |
| `fuel_cell_ppa_rate_mwh`, line 1335 | 65.0 |
| `bess_marginal_cost_mwh`, line 1391 | 38.0 |

Literal diagnostic output from `T/design_probe.log`:

```text
DIESEL_PARAMETER_KEYS []
DIESEL_COST_KEYS []
EXISTING_COST bess_marginal_cost_mwh 38.0
EXISTING_COST turbine_variable_per_mwh 55.0
EXISTING_COST fuel_cell_ppa_rate_mwh 65.0
```

There is no diesel entry in this catalogue/ranked physics-source table. Subject to resolving the STOP condition, D10's requested fallback is diesel last on incremental dispatch and first on back-down. No invented dollar cost or ranking constant has been added.

### Integration design not implemented

The single economic allocation would include on-bus diesel capacity, its state-dependent physical floor/envelope, and a diesel allocation target. One output-application owner must respect the module's physical envelope; the coordinator would retain start/stop ownership. Fuel must use achieved dispatched output rather than a stale pre-allocation block value.

Ordering also needs to preserve the protected start decision: the current coordinator receives a pre-diesel primary-source residual (`P/core/simulation_core.py:1956–1965`), not an independently reconstructed second dispatch. No revised trigger, debounce, minimum run, restore hold, cooldown, authority tier, commitment, floor formula, frequency or protection implementation was selected.

## In-memory unloading check

Files: `T/design_probe.py`, `T/design_probe.log`, `T/design_probe.json`.

This is a small direct DieselModule fixture, NOT a scenario simulation, a new baseline, or a patched implementation. It calls the real `command_stop()` and `advance()` without monkeypatching. Both fixtures use a 20 MW rating, 6 MW proposed minimum, minimum run 900 s and cooldown 300 s. The initial outputs 20 MW and 6 MW show both a rated-output stop and a hypothetical already-backed-down D10 stop.

The fixture's 0.30 proxy is **PROPOSED_HERE**, sourced to the user's D10 instruction citing NFPA 110 §8.4.2 / Annex A. The continuous-operation interpretation was not independently verified here. Other config values are printed in full in the log; startup/ramp-up fields are irrelevant to this direct accepted-stop probe.

Literal accepted-stop results:

```text
STOP_RESULT 20.0 None unloading
STOP_RESULT 6.0 None unloading
```

Every row below has `state="unloading"`, `is_on_bus=true`, and `D10_minimum_mw=6.0`:

| Unload-start MW | Elapsed unloading s | Actual output MW | Below D10 minimum |
|---:|---:|---:|---|
| 20.0 | 5 | 19.666666666666664 | false |
| 20.0 | 210 | 6.000000000000001 | false |
| 20.0 | 215 | 5.666666666666666 | true |
| 20.0 | 295 | 0.33333333333333437 | true |
| 20.0 | 300 | 0.0 | true |
| 6.0 | 5 | 5.8999999999999995 | true |
| 6.0 | 210 | 1.8000000000000003 | true |
| 6.0 | 215 | 1.7 | true |
| 6.0 | 295 | 0.10000000000000031 | true |
| 6.0 | 300 | 0.0 | true |

The probe deliberately does not call `complete_unloading()`: this shows the on-bus module envelope before its coordinator opens the breaker. The conflict already occurs at 215 s from rated output, or at 5 s from minimum output, not only at the final zero-output endpoint.

## IMPL-ISL-14/15 observations, unchanged

- Fleet output currently filters to SYNCHRONISED only (`P/core/diesel_fleet.py:114–123`).
- Fuel also filters to SYNCHRONISED (`:368–370`), then uses `clamp(output/rated, 0, 1) * full_load_gal_per_hour * dt_hours` (`:373–380`). This curve has **no additive no-load term**.
- The restore timer advances after `_begin_unloading()` without checking whether a stop was refused (`:232–234`); completion is gated by timer and any UNLOADING unit (`:236–240`).

These source observations do not authorize implementing the separable fixes after the whole phase has hit its design STOP. No IMPL-ISL-14 or IMPL-ISL-15 code was changed.

## 2d.1–2d.7 disposition

| Item | Literal status |
|---|---|
| 2d.1 D10 | NOT STARTED: operating-envelope conflict above. |
| 2d.2 IMPL-ISL-14 | NOT IMPLEMENTED. |
| 2d.3 IMPL-ISL-15 | NOT IMPLEMENTED. |
| 2d.4 tests | No tests created or updated; TC-ISL-19–22 were not assigned. |
| 2d.5 scenario runs | NOT STARTED. No H arms, regression scenarios, app-path or base-demo reruns. |
| 2d.6 full suite | NOT RUN. No new Phase 2d pass/fail counts or failing-ID list exist. The Phase 2c list remains unchanged; it is not presented as a Phase 2d result. |
| 2d.7 implementation commit | NONE. Only this STOP report and its Library metadata may be committed. |

Before creating this report, the following command returned exit 0:

```text
git diff --exit-code 01ce053 -- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim tools/dr_isl/baseline_runner.py
```

At that point `git status --porcelain` printed no entries. Thus the application package and persisted runner were unchanged by the diagnosis. The local report-only commit hash and post-commit Git status are delivered in chat rather than self-referenced inside the committed report.

Persisted report: `tools/dr_isl/PHASE_2D_REPORT.md`.
Matching scratch copy: `T/PHASE_2D_REPORT.md`.

No scenario JSON, production code, test or parameter edit; no implementation commit; no publish, deploy or push; no Phase 3.

**STOP — clarification required before resuming Phase 2d.**
