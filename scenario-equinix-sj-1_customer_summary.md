# Scenario Summary: GPU Colo Center — SJ-1

## 1. Executive summary

`scenario-equinix-sj-1` models a grid-tied GPU colocation facility in **San Jose, California** with three independent compute environments:

- Kubernetes/H100
- Slurm/H100
- Ray/GB200 NVL72

The expanded center supports a modeled maximum of:

- **16,712 GPUs**
- **21.9 MW of IT compute load**
- Approximately **30.0 MW of total facility demand** after applying the calibrated effective PUE of **1.370424**

The site is supplied by:

- A **30 MW / 60 MWh BESS**
- A **24 MW fuel-cell array**
- A utility connection limited to **5 MW of grid import**
- No modeled solar generation
- No modeled turbine generation

The scenario is designed to demonstrate normal BESS dispatch, BESS reserve preservation, fuel-cell takeover, and capped grid-import behavior during a high-load event.

---

## 2. Site identity and operating context

| Attribute | Value |
|---|---|
| Scenario ID | `scenario-equinix-sj-1` |
| Site | San Jose, CA, USA |
| Latitude / longitude | 37.3382 / -121.8863 |
| Time zone basis | UTC−8 |
| Operating mode | Grid-tied |
| Grid authority tier | Autonomous |
| Nominal frequency | 60 Hz |
| Power factor | 0.85 |
| Simulation duration | 3,600 simulated seconds |
| Default playback speed | 1×; operators can run faster for demonstrations |

The scenario uses deterministic seeded workload generation so repeated runs preserve the same aggregate arrival timing and job-duration behavior.

---

## 3. GPU Colo Center capacity

### 3.1 Kubernetes H100 fleet

- **950 H100-class nodes**
- **8 GPUs per node**
- **7,600 GPUs**
- **9.69 MW IT load**

### 3.2 Slurm H100 fleet

- **950 H100-class nodes**
- **8 GPUs per node**
- **7,600 GPUs**
- **9.69 MW IT load**

### 3.3 Ray GB200 NVL72 fleet

- **21 liquid-cooled GB200 NVL72 racks**
- **72 GPUs per rack**
- **1,512 GPUs**
- **2.52 MW IT load**

### 3.4 Aggregate capacity

| Metric | Capacity |
|---|---:|
| H100 GPUs | 15,200 |
| GB200 GPUs | 1,512 |
| **Total GPUs** | **16,712** |
| H100 IT load | 19.38 MW |
| GB200 IT load | 2.52 MW |
| **Total IT capacity** | **21.90 MW** |
| Effective facility PUE | 1.370424 |
| **Estimated facility demand** | **30.0123 MW** |

The 21.9 MW figure is the modeled IT load. The approximately 30.0 MW figure includes facility overhead using the calibrated effective PUE.

### Important capacity distinction

The **30 MW facility figure is an estimated maximum site demand**, not a statement that 30 MW of firm non-BESS supply is always available. The modeled non-BESS supply path is:

- 24 MW fuel-cell capacity
- 5 MW maximum utility import
- **29 MW combined non-BESS supply**

The BESS provides normal-operation support and retained emergency coverage for the remaining gap.

---

## 4. Workload and scheduler topology

The compute estate is split into independent scheduler clusters. Each cluster maintains its own capacity accounting and does not share a single global node ceiling.

| Cluster | Scheduler | Hardware | Maximum capacity | Share |
|---|---|---|---:|---:|
| `sj1-k8s-h100` | Kubernetes | H100, 8 GPUs/node | 950 nodes / 7,600 GPUs | 42.5% |
| `sj1-slurm-h100` | Slurm | H100, 8 GPUs/node | 950 nodes / 7,600 GPUs | 42.5% |
| `sj1-ray-gb200` | Ray | GB200 NVL72, 72 GPUs/rack | 21 racks / 1,512 GPUs | 15.0% |

### Workload timing

H100 scheduler clusters:

- Mean inter-arrival time: **45 seconds**
- Mean job size: **200 nodes**
- Job-size standard deviation: **80 nodes**
- Minimum job size: **50 nodes**
- Maximum job size: **300 nodes**
- Mean duration: **300 seconds**
- Minimum duration: **30 seconds**
- Reorder window: **10 seconds**
- NTP timing jitter: **2 seconds**

Ray cluster:

- Mean inter-arrival time: **45 seconds**
- Mean job size: **5 racks**
- Job-size standard deviation: **2 racks**
- Minimum job size: **1 rack**
- Policy maximum job size: **42 racks**
- Physical fleet maximum: **21 racks**
- Mean duration: **300 seconds**
- Minimum duration: **30 seconds**

The 42-rack Ray job policy ceiling cannot override the physical 21-rack fleet capacity.

---

## 5. Power-supply architecture

### 5.1 Battery energy-storage system

| Attribute | Value |
|---|---:|
| Rated power | 30 MW |
| Usable energy | 60 MWh |
| Initial SoC | 95% |
| Initial usable energy | Approximately 57 MWh |
| Grid-forming anchor | Yes |
| Anchor reserve | 1 MW |
| Normal dispatch depth | 3 percentage points |

The BESS normal-operation policy allows discharge from **95% down to 92% SoC**.

That corresponds to:

- Normal-operation discharge envelope: approximately **1.8 MWh**
- Retained charge at the 92% floor: approximately **55.2 MWh**

The remaining charge is held for emergency support and is not released during ordinary operation unless the non-BESS sources cannot cover the demand.

### 5.2 Fuel-cell array

- Fuel-cell array enabled
- **4 stacks**
- **6 MW per stack**
- **24 MW total rated output**

The fuel-cell array is the primary non-BESS source after the BESS reaches its normal-operation reserve floor.

### 5.3 Utility grid connection

- Grid-tied operation
- **5 MW maximum grid import**
- PCC import cap applies to negative grid exchange
- Grid import is represented as a negative signed value in the telemetry payload

The grid can cover demand after the fuel-cell fleet reaches its available output, but import is limited to 5 MW. Any remaining deficit remains visible as unserved demand or requires emergency BESS support, depending on the operating state.

### 5.4 Solar and turbines

- Solar rated capacity: **0 MW**
- Turbine fleet: **none configured**
- The scenario intentionally focuses on BESS, fuel-cell, and capped-grid behavior.

---

## 6. Dispatch sequence

The intended source sequence is:

### Normal demand

1. BESS supplies demand.
2. BESS SoC declines from 95% toward 92%.
3. Once the normal 3-percentage-point dispatch envelope is consumed, BESS output falls to zero for ordinary demand.
4. Fuel-cell capacity supplies the demand.
5. Grid import covers any remaining demand, up to the 5 MW PCC limit.

### Emergency demand

If demand remains uncovered after:

- Fuel-cell output
- Available grid import
- Other available non-BESS sources

then the retained BESS charge can be released for emergency support.

This means the BESS is not treated as an unlimited normal-operation source. Most of its energy is preserved for a source outage or an otherwise uncovered deficit.

---

## 7. PUE and facility-demand model

The scenario uses:

- `pue_base`: **1.074**
- `alpha_max`: **0.276**
- Effective modeled PUE: **1.370424**
- Thermal time constant: **20 seconds**
- Thermal update interval: **90 seconds**

The 21.9 MW IT target becomes:

```text
21.9 MW IT × 1.370424 effective PUE
≈ 30.0123 MW facility demand
```

The PUE calibration is intended to approximate Equinix’s disclosed **2025 global portfolio average total PUE of approximately 1.37**.

For customer-facing documentation, this should be described as a scenario calibration, not as a measured SJ-1-specific value. The assumed cooling/non-cooling split is an industry-average estimate and is not presented as a site measurement.

---

## 8. PCC import validation burst

The scenario includes a validation-only high-load stimulus designed to demonstrate fuel-cell-to-grid handoff behavior.

### Validation event

- Start time: **900 simulated seconds**
- Duration: **60 simulated seconds**
- 13 concurrent tenant burst slices
- Each slice: 2,142 GPUs
- Aggregate injected load: **19.4922 MW**

This event is not intended to represent normal customer workload. It is a deterministic test stimulus that raises site demand above the 24 MW fuel-cell capacity after the BESS has reached its 92% reserve floor.

Expected behavior during the burst:

- BESS remains at approximately **92% SoC**
- BESS contributes no normal-operation output
- Fuel cell reaches approximately **24 MW**
- Grid import supplies the residual load
- Grid import remains at or below **5 MW**
- No unserved load occurs while total demand remains below the combined 29 MW fuel-cell-plus-grid capacity

The validation burst should be described in the customer document as a controlled scenario test, not as the normal customer workload.

---

## 9. Customer-facing operating narrative

> The SJ-1 GPU colocation center is modeled as a 16,712-GPU facility with 21.9 MW of IT capacity and approximately 30.0 MW of total facility demand after calibrated PUE overhead. The compute estate is divided across independent Kubernetes/H100, Slurm/H100, and Ray/GB200 environments, each with its own scheduling and capacity controls.
>
> During normal operation, the 30 MW / 60 MWh BESS supplies the initial load and discharges through a controlled 3-percentage-point SoC window, from 95% to 92%. Once that normal-operation envelope is consumed, the battery preserves its remaining charge as emergency reserve. The 24 MW fuel-cell array then supplies the primary non-BESS demand, followed by utility import through a hard 5 MW PCC limit. A controlled high-load validation event demonstrates that the fuel-cell fleet reaches its rated capacity and that the residual demand transfers to the capped grid connection without exceeding the import limit.

---

## 10. Important modeling caveats

- The 16,712-GPU figure is the configured maximum fleet capacity.
- The 21.9 MW figure is IT load, not total facility demand.
- Approximately 30.0 MW is the PUE-inclusive facility estimate.
- The effective PUE is calibrated and modeled, not a direct measurement of this site.
- The 24 MW fuel-cell rating is the aggregate of four 6 MW stacks.
- The grid is capped at 5 MW of import.
- The BESS is not intended to sustain the full 30 MW facility indefinitely.
- Solar and turbine generation are intentionally absent from this scenario.
- The high-load tenant burst is a validation stimulus and should not be interpreted as the normal customer workload.
- Per-job policy limits are separate from total facility capacity; a 300-node H100 job cap does not represent the full H100 fleet capacity.