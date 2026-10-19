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
| H4_mem_req_mb_with_per_cpu_flag | **PASS** | rows with bit 63 set=346766; decoded mem_req equals tres_req mem (id 2) in 395715/395863 rows; mismatch samples=['mem_req=307200 cpus=320 nodes=8 tres_mem=2457600', 'mem_req=65536 cpus=80 nodes=2 tres_mem=131072', 'mem_req=8192 cpus=16 nodes=8 tres_mem=65536', 'mem_req=8192 cpus=16 nodes=8 tres_mem=65536', 'mem_req=65536 cpus=80 nodes=2 tres_mem=131072'] |
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
| id_job | 0 | 395914 | 0 | >5000 | `82691694838059`, `3434806870797`, `8370846758272`, `50552783599355`, `16051179268048` |
| id_array_job | 0 | 395914 | 0 | >5000 | `38873353215144`, `16618712154521`, `74939912707152`, `84173100828392`, `37264331060186` |
| id_array_task | 0 | 395914 | 0 | >5000 | `2504`, `2523`, `2543`, `4294967294`, `2625` |
| id_user | 0 | 395914 | 0 | 608 | `42770088536256`, `28063009141185`, `78105663882022`, `11289836447956`, `20010471345300` |
| kill_requid | 0 | 395914 | 0 | 462 | `61026541062099`, `87110995014675`, `37416557891891`, `66483638897081`, `74586577910780` |
| nodes_alloc | 0 | 395914 | 0 | 37 | `1`, `2`, `4`, `3`, `5` |
| nodelist | 0 | 0 | 395914 | 2915 | `['r9189566-n911952']`, `['r2100214-n851693']`, `['r9535192-n386398']`, `['r9175025-n386398']`, `['r5573787-n386398']` |
| cpus_req | 0 | 395914 | 0 | 101 | `20`, `1`, `4`, `6`, `2` |
| derived_ec | 0 | 395914 | 0 | 19 | `0`, `9`, `32512`, `256`, `33280` |
| exit_code | 0 | 395914 | 0 | 37 | `0`, `35072`, `33280`, `256`, `32512` |
| gres_used | 395914 | 0 | 0 | 0 |  |
| array_max_tasks | 0 | 395914 | 0 | 10 | `0`, `4`, `8`, `6`, `10` |
| array_task_pending | 0 | 395914 | 0 | 1 | `0` |
| constraints | 0 | 0 | 395914 | 7 | `xeon-g6`, `xeon-g6&6248`, `xeon-e5`, `\N`, `xeon-p8` |
| flags | 0 | 395914 | 0 | 4 | `4`, `2`, `8`, `12` |
| mem_req | 0 | 395914 | 0 | 107 | `9223372036854784308`, `102400`, `20480`, `9223372036854777780`, `2048` |
| partition | 0 | 0 | 395914 | 5 | `normal`, `test`, `gaia`, `xeon-p8`, `db` |
| priority | 0 | 395914 | 0 | 2717 | `10237`, `110413`, `10239`, `110692`, `10771` |
| state | 0 | 395914 | 0 | 7 | `3`, `5`, `6`, `4`, `7` |
| timelimit | 0 | 395914 | 0 | 100 | `4294967295`, `1440`, `720`, `14400`, `525600` |
| time_submit | 0 | 395914 | 0 | >5000 | `1609535703`, `1609807695`, `1609535912`, `1609808481`, `1609809099` |
| time_eligible | 0 | 395914 | 0 | >5000 | `1609535704`, `1609807695`, `1609535912`, `1609808481`, `1609809100` |
| time_start | 0 | 395914 | 0 | >5000 | `1609806297`, `1609806607`, `1609807004`, `1609807695`, `1609808470` |
| time_end | 0 | 395914 | 0 | >5000 | `1609806605`, `1609807004`, `1609807331`, `1609811546`, `1609808777` |
| time_suspended | 0 | 395914 | 0 | 1 | `0` |
| track_steps | 0 | 395914 | 0 | 2 | `0`, `1` |
| tres_alloc | 0 | 0 | 395914 | 1145 | `1=20,2=170000,4=1,5=20`, `1=40,2=340000,4=1,5=40`, `1=1,2=8500,4=1,5=1`, `1=4,2=34000,4=1,5=4`, `1=6,2=51000,4=1,5=6` |
| tres_req | 0 | 0 | 395914 | 641 | `1=20,2=170000,4=1,5=20`, `1=1,2=8500,4=1,5=1`, `1=4,2=34000,4=1,5=4`, `1=6,2=51000,4=1,5=6`, `1=1,2=102400,4=1,5=1` |
| job_type | 0 | 0 | 395914 | 4 | `OTHER`, `LLSUB:INTERACTIVE`, `LLSUB:BATCH`, `LLMAPREDUCE:MAP` |

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
