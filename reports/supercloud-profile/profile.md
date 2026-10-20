# SuperCloud Slurm log profile

## slurm_log: `slurm-log.csv (datacenter-challenge/202201)`

Rows profiled: 395914

| Hypothesis | Status | Evidence |
|---|---|---|
| H0_header_matches_notebook | **PASS** | missing=[] extra=[] |
| H1_times_epoch_seconds | **PASS** | 800000/800000 non-zero time values within 2000..2033 as epoch seconds; time_start==0 rows=0 by state={} |
| H2_tres_req_id_eq_count | **PASS** | malformed=0; ids seen={1: 395914, 2: 395863, 4: 395914, 5: 395914, 1001: 6, 1002: 98170}; rows with 1001/1002 (GPU)=98176 (README states 98,177 GPU jobs) |
| H2b_tres_alloc_same_format | **PASS** | ids seen in tres_alloc={1: 395914, 2: 395914, 3: 47724, 4: 395914, 5: 395914, 1001: 6, 1002: 99338} |
| H3_timelimit_minutes | **PASS** | COMPLETED jobs checked=200000; runtime within limit if minutes=1.0000, if seconds=0.7931; timelimit quantiles={'min': 10, 'p01': 240, 'p50': 525600, 'p99': 4294967295, 'max': 4294967295} |
| H4_mem_req_mb_with_per_cpu_flag | **PASS** | rows with bit 63 set=346766; decoded mem_req equals tres_req mem (id 2) in 395715/395863 rows; mismatch samples=[] |
| H5_state_numeric_enum | **PASS** | value_counts={'3': 309037, '4': 53980, '5': 21349, '6': 7089, '11': 4414, '7': 44, '1024': 1}; low-byte mapping={'3': 'COMPLETED', '4': 'CANCELLED', '5': 'FAILED', '6': 'TIMEOUT', '11': 'OUT_OF_MEMORY', '7': 'NODE_FAIL', '1024': 'PENDING'} |
| H6_gres_used_format | **INCONCLUSIVE** | samples=[] |
| H7_time_ordering | **PASS** | rows violating submit<=eligible<=start<=end (all >0): 0 |
| H8_id_job_unique | **PASS** | duplicate id_job rows=0 (array jobs may legitimately repeat; see id_array_*) |
| H9_nodes_alloc_vs_nodelist | **PASS** | nodelist entry count equals nodes_alloc in 395914/395914 rows; mismatch samples=[] |

### Derived (converter-relevant)

```
{
  "time_span_utc": [
    1609535703,
    1633101131
  ],
  "timelimit_infinite_rows": 173875,
  "state_values_with_flag_bits": {
    "1024": 1
  },
  "multi_node_rows": 6561,
  "gpu_rows": 98176,
  "gpu_multi_node_rows": 2365,
  "gpu_per_node_distribution": {
    "1": 79875,
    "2": 18162,
    "1/2": 50,
    "4": 44,
    "1/4": 30,
    "1/3": 7,
    "2/6": 2,
    "1/6": 2,
    "1/7": 1,
    "1/8": 1,
    "1/10": 1,
    "2/3": 1
  },
  "gpu_tres_id_mix": {
    "1002": 98170,
    "1001": 6
  }
}
```

| Column | blank | numeric | non-numeric | distinct | samples |
|---|---|---|---|---|---|
| id_job | 0 | 395914 | 0 | >5000 |  |
| id_array_job | 0 | 395914 | 0 | >5000 |  |
| id_array_task | 0 | 395914 | 0 | >5000 |  |
| id_user | 0 | 395914 | 0 | 608 |  |
| kill_requid | 0 | 395914 | 0 | 462 |  |
| nodes_alloc | 0 | 395914 | 0 | 37 |  |
| nodelist | 0 | 0 | 395914 | 2915 |  |
| cpus_req | 0 | 395914 | 0 | 101 |  |
| derived_ec | 0 | 395914 | 0 | 19 |  |
| exit_code | 0 | 395914 | 0 | 37 |  |
| gres_used | 395914 | 0 | 0 | 0 |  |
| array_max_tasks | 0 | 395914 | 0 | 10 |  |
| array_task_pending | 0 | 395914 | 0 | 1 |  |
| constraints | 0 | 0 | 395914 | 7 |  |
| flags | 0 | 395914 | 0 | 4 |  |
| mem_req | 0 | 395914 | 0 | 107 |  |
| partition | 0 | 0 | 395914 | 5 |  |
| priority | 0 | 395914 | 0 | 2717 |  |
| state | 0 | 395914 | 0 | 7 |  |
| timelimit | 0 | 395914 | 0 | 100 |  |
| time_submit | 0 | 395914 | 0 | >5000 |  |
| time_eligible | 0 | 395914 | 0 | >5000 |  |
| time_start | 0 | 395914 | 0 | >5000 |  |
| time_end | 0 | 395914 | 0 | >5000 |  |
| time_suspended | 0 | 395914 | 0 | 1 |  |
| track_steps | 0 | 395914 | 0 | 2 |  |
| tres_alloc | 0 | 0 | 395914 | 1145 |  |
| tres_req | 0 | 0 | 395914 | 641 |  |
| job_type | 0 | 0 | 395914 | 4 |  |

## tres-mapping.txt

```
tres_id,resource_type
1,cpu
2,mem
3,energy
4,node
5,billing
6,fs
7,vmem
8,pages
1001,gpu:tesla
1002,gpu:volta
```
