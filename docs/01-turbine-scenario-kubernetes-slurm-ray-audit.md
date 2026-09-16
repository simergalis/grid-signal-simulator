# Read-only audit: 01 Turbine Scenario with Kubernetes Slurm and Ray

**Scenario ID:** `scenario-uneven-multisched-01`  
**Audit scope:** scenario identity, site size, grid connection, generation/storage fleet, turbine model and parameters, workload split, scheduler wiring, and available run telemetry.  
**Audit status:** read-only; no project files or simulator state were modified.

## 1. Scenario identity

- **Display name:** `01 Turbine Scenario with Kubernetes Slurm Ray`
- **Scenario ID:** `scenario-uneven-multisched-01`
- **Definition:** `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json:2`
- **Catalog registration:** `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/scenarios.py:1400-1403`
- **Duration:** 7,200 seconds / two hours, from `.../scenario-uneven-multisched-01.json:11-13`

## 2. Site size and grid connection

### Site/design draw

- **Explicit facility design-draw field:** not defined.
- `base_load_mw` is explicitly `null`: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json:5-9`
- There is no `design_peak_load_mw` field in this scenario.
- The description separately states **45 MW and 90 MW workload bursts**: `.../scenario-uneven-multisched-01.json:3`

Those 45 MW and 90 MW values are stated as burst sizes, but the scenario does not identify them as an independent facility design-draw/nameplate field.

Runtime details:

- `enterprise_8gpu_air` is a **10.2 kW H100-class, 8-GPU chassis profile**: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py:112-134`
- The factory defaults `pue_base` to **1.03** when absent: `.../runtime/scenario_factory.py:652-657`
- Runtime comments identify compute demand as PUE-inclusive: `.../runtime/scenario_factory.py:261-267`

### Grid mode

- **Mode:** islanded
- Scenario field: `island_mode: true` at `.../scenario-uneven-multisched-01.json:8-12`
- Runtime mapping:
  - `true` → `IslandMode.ISLANDED`
  - `false` → `IslandMode.GRID_TIE`
  - Source: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py:631-635`

### Grid import limit

- **Scenario-specific import limit:** not defined.
- The factory maps an absent value to `None`: `.../runtime/scenario_factory.py:657-662`
- The schema documents `None` as unlimited grid balancing, applicable only in grid-tied mode; exports are not capped: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py:1818-1826`

Because this scenario is islanded, there is no active PCC/grid-import balancing path for the run.

## 3. Generation and storage fleet

### Gas turbines

The scenario declares **four turbines**, each rated at **25 MW**, for **100 MW aggregate nameplate**:

- `gt-spin-01`: spinning at t=0
- `gt-spin-02`: spinning at t=0
- `gt-hot-01`: hot standby
- `gt-hot-02`: hot standby

Source: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json:173-177`

Each turbine has:

- `rated_mw: 25.0`
- `r_asset_mw_per_s: 0.5`
- `p_min_stable_frac: 0.35`
- `cold_start_s: 600`
- `warm_start_s: 360`
- `hot_start_s: 300`
- `thermal_state: "hot"`

The two spinning turbines are placed directly into the synchronized state and initialized at their minimum stable output by the factory: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py:864-900`

### BESS

One grid-forming BESS is declared:

- Asset: `bess-0`
- Power rating: **30 MW**
- Usable energy: **60 MWh**
- Initial SoC: **95%**
- Grid-forming: `true`
- Anchor reserve: **1.0 MW**
- Authority tier: `autonomous`

Source: `.../scenario-uneven-multisched-01.json:180-182`

The factory passes these values directly into `BessConfig`: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py:904-926`

### Diesel block

The scenario declares an enabled diesel power block:

- Target capacity: **20 MW**
- Unit rating: **20 MW**
- Start probability: `p_start: 1.0`
- Reliability target: `1.0`
- Advisory-only authority
- Start delay: **3,600 seconds**
- Residual ramp time: **60 seconds**

Source: `.../scenario-uneven-multisched-01.json:184-194`

The schema materializes this block as **one primary 20 MW diesel unit**:

- `ceil(20 / 20) = 1` active unit
- With `p_start=1.0` and reliability target `1.0`, the minimum total fleet is also one unit
- Materialized ID: `diesel-000`
- No standby diesel unit is generated

Materialization logic: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py:824-879`

The runtime constructs diesel modules from the materialized `diesel_units` list: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py:929-955`

### Other generation assets

- **Solar:** not defined; the factory defaults `solar_rated_mw` to `0.0` and creates no solar array: `.../runtime/scenario_factory.py:957-969`
- **Fuel cells:** not enabled and no fuel-cell units are declared. The factory only creates them when `fuel_cell_units` or `fuel_cell_enabled` is present: `.../runtime/scenario_factory.py:997-1007`

## 4. Turbine model and parameters

### Turbine classification

The scenario does not set a per-unit `gt_mode`.

The runtime `TurbineConfig` default is:

- `gt_mode: "frame"`

The code distinguishes:

- `"frame"` — large heavy-duty frame
- `"aero"` — aeroderivative

Source: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py:0810-0813`

The scenario therefore runs as a **generic TurbineModule using the default frame/industrial classification**. It is not configured as an aeroderivative unit, and there is no reciprocating-engine turbine class or mode in this path.

The runtime uses one generic `TurbineModule` class: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py:0897-0900`

### Ramp rate

- Per-unit ramp rate: **0.5 MW/s**
- Equivalent: **30 MW/min**
- Explicit scenario value: `.../scenario-uneven-multisched-01.json:173-177`
- The factory passes the scenario value into `TurbineConfig`: `.../runtime/scenario_factory.py:0818-0824`

### Minimum stable load

- **35% of rated output**
- For each 25 MW turbine: **8.75 MW minimum stable load**
- Scenario value: `.../scenario-uneven-multisched-01.json:173-177`
- Schema documentation identifies 0.35 as the GE simple-cycle minimum stable-load assumption: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py:898-901`

### Start times

Configured per turbine:

| Start type | Time |
|---|---:|
| Hot | 300 s |
| Warm | 360 s |
| Cold | 600 s |

Source: `.../scenario-uneven-multisched-01.json:173-177`

All four units have `thermal_state: "hot"`. Therefore, the two hot-standby units use the **300-second hot-start path** on their initial start command. The warm and cold values remain configured for later thermal classifications.

The factory passes duration overrides and initial thermal state into `TurbineConfig`: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py:0839-0847`

The start state machine selects the initial configured thermal state on the first start: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py:1072-1079`

### Other operational constraints

The validated runtime representation also enables:

- Minimum run time: **1,800 s**
- Minimum down time: **900 s**
- Both guards enabled

These are schema defaults because the scenario does not override them: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py:902-916`

### Heat rate, efficiency, and fuel model

For the gas turbines:

- **Heat rate:** not defined
- **Electrical efficiency:** not defined
- **Fuel type:** not defined
- **Fuel units:** not defined
- **Part-load heat-rate curve:** not defined
- **No-load fuel burn:** not defined

The turbine schema fields cover rating, ramp, standby state, minimum stable load, start timing, thermal state, and governor/frequency parameters, but contain no turbine fuel or heat-rate fields: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py:882-945`

The `TurbineConfig` also contains no gas-turbine heat-rate, efficiency, fuel-type, or fuel-consumption field: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py:0744-0862`

The separate diesel model has a fuel-burn concept, but that applies to the diesel block rather than the gas turbines.

### Spinning reserve

The turbine model represents **upward MW reserve/headroom**:

- Only synchronized, non-hot-standby units contribute to reserve.
- Unloading units do not contribute.

Source: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py:1000-1007`

This is not represented as a turbine fuel-backed reserve-energy value in MWh. No gas-turbine spinning-reserve MWh field is defined.

## 5. Workload split and demand generation

### Stochastic scheduler shares

The scenario defines three `kube_clusters`:

| Scheduler | Tenant | Share | Hardware | Capacity unit |
|---|---|---:|---|---|
| K8S | `K8S-H100` | 40% | `enterprise_8gpu_air` | node |
| SLURM | `SLURM-H100` | 40% | `enterprise_8gpu_air` | node |
| RAY | `RAY-GB200` | 20% | `nextgen_rack_liquid` | rack |

Source: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json:15-72`

Distributions:

- **Kubernetes**
  - Mean interarrival: 40 s
  - Mean job size: 180 nodes
  - Standard deviation: 90 nodes
  - Range: 50–320 nodes
  - Mean duration: 280 s
  - Minimum duration: 40 s
  - Reorder window: 8 s
  - NTP jitter: 2 s
  - Maximum nodes: 900
  - Minimum nodes: 150

- **Slurm stochastic share**
  - Mean interarrival: 95 s
  - Mean job size: 220 nodes
  - Standard deviation: 100 nodes
  - Range: 60–340 nodes
  - Mean duration: 340 s
  - Minimum duration: 45 s
  - Maximum nodes: 900

- **Ray**
  - Mean interarrival: 65 s
  - Mean job size: 6 racks
  - Standard deviation: 3 racks
  - Range: 1–40 racks
  - Mean duration: 260 s
  - Minimum duration: 30 s
  - Maximum nodes: 40

### Scripted burst events

The scenario also has explicit workload signals:

- K8S: 4,283 nodes at t=30 s; ends at t=270 s
- SLURM: 8,566 nodes at t=310 s; ends at t=610 s
- RAY: 3,426 nodes at t=920 s; ends at t=1,520 s
- K8S: 7,995 nodes at t=1,850 s; ends at t=2,450 s
- RAY: 5,711 nodes at t=2,700 s; ends at t=3,300 s

Source: `.../scenario-uneven-multisched-01.json:160-170`

### Which scheduler path is actually used?

- The three `kube_clusters` definitions are all instantiated as **KubeDemandAgent** instances: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py:1177-1185`
- Each definition is converted into a `KubeConfig`, with the hardware catalogue supplying rated kW and GPU capacity: `.../runtime/scenario_factory.py:1210-1263`
- The K8S/SLURM/RAY labels select metadata/configuration within the generic KubeDemandAgent path; they do not each instantiate completely separate scheduler demand engines.

There is also a separate explicit Slurm path because this scenario contains `slurm_config`:

- The factory creates an independent `SlurmSchedulerEngine`.
- The three explicit Slurm jobs are converted to `SlurmJobSpec`.
- This path is intentionally separate from `KubeDemandAgent`.

Sources: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py:1311-1318` and `.../runtime/scenario_factory.py:1348-1377`

The scripted workload events are converted into generic `WorkloadSignal` records. Scheduler labels and Ray identifiers are carried as fields, but the event conversion itself does not create a separate Ray execution model: `.../runtime/scenario_factory.py:1488-1536`

## 6. Run telemetry currently exposed

### Per-tick turbine telemetry

The serialized run payload exposes:

- Aggregate `turbine_output_mw`
- Per-unit `turbine_units`
- Per-unit state
- Per-unit time to online
- Thermal state
- Start phase
- Out-of-service reason
- Rated MW and ramp configuration
- `units_on_bus_count`
- `on_bus_output_mw`
- Turbine ramp credit
- Observed ramp rate
- Estimated time to close

Sources: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py:405-408`, `.../runtime/run_manager.py:548-552`, and `.../runtime/run_manager.py:588-619`

### Turbine fuel consumed

- **Gas-turbine fuel consumed per run:** not reported.
- There is no gas-turbine cumulative fuel field in `TickResult` or the serialized tick payload.
- The telemetry serializer reports fuel fields for fuel cells and remaining fuel for diesel, but not consumed gas-turbine fuel:
  - Fuel-cell fuel telemetry: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py:437-440`
  - Diesel fuel remaining/runtime remaining: `.../runtime/run_manager.py:465-478`

For diesel, the scenario's materialized block uses a default burn rate of **230 gal/hour/unit at full load**, and the fuel type is diesel. That is diesel configuration/telemetry, not gas-turbine fuel consumption.

### Turbine start counts

- **Per-run turbine start count:** not reported.
- The turbine module tracks run-start and stop timestamps, but no cumulative start counter: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py:900-917`
- The serialized per-unit fields include live state and start phase, but no `start_count`: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py:588-594`

### Spinning-reserve MWh

- **Spinning-reserve MWh:** not reported.
- The engine exposes reserve-related **MW** quantities such as turbine ramp credit and BESS bridging capability, not an energy reserve total in MWh: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py:544-552`
- The turbine reserve rule itself is an upward-headroom eligibility rule: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py:1000-1007`

## Bottom line

This scenario is a **100 MW islanded frame-class gas-turbine fleet** with two 25 MW units synchronized at 35% MSL, two additional 25 MW hot-standby units, a 30 MW/60 MWh grid-forming BESS, and one advisory-only 20 MW diesel unit.

The scenario has MW-level dispatch, startup, reserve-headroom, workload, BESS, and diesel telemetry. It does **not** currently define or report:

- Gas-turbine heat rate
- Gas-turbine efficiency
- Gas-turbine fuel type or fuel units
- Gas-turbine part-load fuel behavior
- Gas-turbine no-load fuel burn
- Per-run gas-turbine fuel consumed
- Turbine start counts
- Spinning-reserve energy in MWh