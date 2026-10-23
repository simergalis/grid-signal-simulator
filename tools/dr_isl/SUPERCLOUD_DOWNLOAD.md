# MIT SuperCloud Slurm log download

Public S3 was listed anonymously using HTTPS `ListObjectsV2` against `mit-supercloud-dataset` (no credentials). Bucket-root common prefixes were `2022-hpca/`, `challenges/`, and `datacenter-challenge/`. The example prefix `datacenter-challenge/202201/` exists and contains:

| Object key | Size (bytes) | Last modified (UTC) |
|---|---:|---|
| `datacenter-challenge/202201/slurm-log.csv` | 103,165,427 | 2022-01-20T17:20:11Z |
| `datacenter-challenge/202201/tres-mapping.txt` | 111 | 2022-01-20T17:20:11Z |
| `labelled-slurm-log.csv` | Not present under this prefix | — |

The prefix also lists `labelled_job_stats.csv` (339 bytes) and `labelled_jobids.csv` (82,332 bytes); neither is `labelled-slurm-log.csv`. No CPU, GPU, or node-data archive was downloaded. Only the two requested objects above were downloaded to `attached_assets/supercloud/`.

## Downloaded files

| Local file | SHA-256 | Bytes | Physical lines |
|---|---|---:|---:|
| `attached_assets/supercloud/slurm-log.csv` | `27259e5b8e6daecd80b7853126af40ba759bc25edc9053fc174ef7a4f186aa01` | 103,165,427 | 395,915 |
| `attached_assets/supercloud/tres-mapping.txt` | `4897c5cf1575664217f93d9c66cda3c06cae9d90f827a5dadc5483044dd64a51` | 111 | 11 |

`slurm-log.csv` contains 395,914 CSV data records plus its header. Its header row is:

`id_job,id_array_job,id_array_task,id_user,kill_requid,nodes_alloc,nodelist,cpus_req,derived_ec,exit_code,gres_used,array_max_tasks,array_task_pending,constraints,flags,mem_req,partition,priority,state,timelimit,time_submit,time_eligible,time_start,time_end,time_suspended,track_steps,tres_alloc,tres_req,job_type`

The numeric `time_start` and `time_end` fields were interpreted as Unix seconds and normalized to UTC. Across non-empty `time_start` values, the minimum is `2021-01-05T00:24:57Z`; the maximum is `2021-10-01T15:03:35Z`. Rows with `time_start` on 2021-08-11 UTC: **578**. Rows with `time_end` on that date: **344**. Distinct rows with either `time_start` or `time_end` on that date: **580**. All 395,914 records had parseable values in both fields. No data rows are reproduced in this report.

## Tracking check

`git check-ignore -v` reports `.gitignore:52:attached_assets/` for each downloaded file. `git ls-files -- attached_assets/supercloud/slurm-log.csv attached_assets/supercloud/tres-mapping.txt` returns no paths. The downloaded data files are ignored and untracked.

No D6 generator work was started.
