---
name: BESS anchor reserve design (Step 3 Item 4)
description: IslandMode enum, grid_forming flag, bridging_available_mw, fleet split, and why sum-of-durations not min().
---

**The formula (v2.5 §7.1.2):**
`BESS_bridging_available(t) = rated_mw − p_anchor_reserve_mw`
…only when `grid_forming=True AND island_mode=ISLANDED`. Otherwise deduction = 0.

**Where things live:**
- `IslandMode` enum: `core/models.py` (before `SiteConfig`)
- `SiteConfig.island_mode`: defaults to `IslandMode.ISLANDED` (conservative per TC-63)
- `BessConfig.p_anchor_reserve_mw`: defaults to `1.0` MW (non-zero per TC-63, PROTO-9)
- `BessConfig.grid_forming`: defaults to `False` (anchor role must be explicitly assigned)
- `BessModule.bridging_available_mw(island_mode)`: power ceiling for arbitration
- `BessModule.max_sustainable_seconds(discharge_mw, island_mode)`: uses bridging_available_mw as ceiling (extends D11)
- `BessModule.cover_shortfall(allocated_mw, fleet_covered, dt_seconds, island_mode)`: new signature
- `DispatchArbitrator.__init__(turbines, bess_units, site)`: now takes site reference for island_mode

**Fleet split (tick):**
Proportional to `bridging_available_mw` per unit. Homogeneous fleet → equal share. Heterogeneous → avoids D11 zero-return from over-allocation to weak units.

**Reserve aggregation (stage_for_predicted_step):**
Proportional allocation of peak_shortfall → SUM each unit's `max_sustainable_seconds(allocated_i, island_mode)`. NOT min().

**Why sum not min:**
- When fleet CAN cover: all allocated_i ≤ bridging_available_i → finite durations → sum >> gap_s ✓
- When fleet CANNOT cover: proportional overflows → some units get allocated_i > bridging_available_i → those return 0.0 → sum collapses below gap_s → alert fires ✓
- min() over equal shares fails for heterogeneous fleets: a weak unit returns 0.0, min=0, false alert even when fleet can cover.

**THE TRAP with cover_shortfall taper flag:**
The old taper logic used `turbine_output >= p_total` (fleet-level check). With proportional split, a depleted/anchored unit gets `allocated_mw=0` even when the fleet still has a shortfall. If taper used allocated==0, that unit would falsely advance its taper timer. Fix: pass explicit `fleet_covered: bool` from tick(), derived from `fleet_shortfall <= 0`.

**TC-63 conservatism:**
- `p_anchor_reserve_mw` MUST default non-zero. Default 0 silently reproduces unadjusted arithmetic.
- `island_mode` MUST default `ISLANDED`. Default `GRID_TIE` makes p_anchor_reserve zero for all units (grid_forming irrelevant in grid-tie), silently reproducing unadjusted arithmetic.
- `grid_forming` defaults `False` — anchor role is explicit designation, not default. This is compatible with TC-63 because the non-zero p_anchor_reserve_mw default is the TC-63 requirement; grid_forming controls when it applies.

**Why:** v2.5 §7.1.2 requires anchor headroom in both directions for frequency regulation. Without it, a reserve check can pass shortly before a frequency excursion (TC-61, TC-63). The default ISLANDED + non-zero reserve ensures conservative behavior unless explicitly overridden.
