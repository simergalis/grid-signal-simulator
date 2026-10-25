# D6c.C1 — legacy grid-import diagnosis

Read-only diagnosis recorded before any D6c application edit.

- `api/routes/runs.py:1165–1170` iterates completed ticks and adds
  `max(0.0, net_demand_mw - turbine_output_mw - bess_output_mw) * DT_H`
  to `grid_import_mwh`. This calculation has no grid-mode condition.
- `runtime/run_manager.py:764–786` serializes the per-tick
  `contingency_coverage` object, including its `grid_connected` value at line 782.
- `core/simulation_core.py:3312` states “islanded → grid_exchange_mw = 0.0
  exactly (PCC open)”. Lines 3371–3373 set islanded exchange to zero and route
  the balance residual to frequency. Lines 3375–3387 route a grid-connected
  residual to PCC exchange; lines 3392–3395 state that negative exchange is
  grid import and that islanded exchange is always zero.
- Therefore the endpoint residual is not grid import on islanded runs. In the
  recorded D6b REST result (`tools/dr_isl/d6b/D6B_3_REST.json:6–28`),
  S10 reports `grid_import_mwh: 5.5358` and `grid_import_cost: 664.2925` at
  `$120/MWh`; the D6b report records `5.535769413 MWh` unserved at
  `tools/dr_isl/D6B_REPORT.md:207`. This confirms the islanded shortfall was
  counted and priced as import.
- For grid-connected runs, the same local-demand residual is supplied through
  the PCC when the grid is not import-limited (`core/simulation_core.py:
  3375–3379`). Keeping the existing residual calculation for ticks whose
  `contingency_coverage.grid_connected` is true preserves the legacy grid-tied
  estimate. D6c.C2 is therefore identifiable and may proceed without changing
  simulator physics.
