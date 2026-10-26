"""Aggregate MW-weighted queue-wait histogram used for synthetic Slurm submits."""

# PROPOSED_HERE: apply one empirical S10 day to synthetic Slurm jobs because
# D6i found queue waits are strongly MW-weighted. This is an aggregate
# histogram only (no job IDs or row-level source records). Source:
# tools/dr_isl/D6I_S10_QUEUE_VISIBILITY.md and attached SuperCloud input
# SHA-256 27259e5b8e6daecd80b7853126af40ba759bc25edc9053fc174ef7a4f186aa01.
# The 153 in-day GPU jobs were weighted by their start-MW. Their node counts
# use the recorded 11.5612282649 chassis/GPU factor (50 MW / 424 peak V100s /
# 10.2 kW per chassis); at 10.2 kW/chassis and 1.03 PUE, integer chassis sum
# is exactly proportional to MW.
SYNTHETIC_QUEUE_WAIT_CDF_VERSION = "s10-2021-08-11-mw-weighted-v1"

# Rows: (queue wait seconds, aggregate MW-proportional chassis weight, job count).
# Generated from 153 starts on 2021-08-11; source population and method are
# documented in D6i. The histogram has no event identifiers or per-job rows.
SYNTHETIC_QUEUE_WAIT_CDF_HISTOGRAM = (
    (0, 8478, 62),
    (1, 1655, 27),
    (2, 857, 8),
    (3, 69, 3),
    (4, 416, 8),
    (5, 92, 4),
    (6, 58, 3),
    (7, 152, 9),
    (8, 35, 2),
    (68, 24, 2),
    (332, 4902, 1),
    (412, 4902, 1),
    (1348, 1480, 1),
    (1359, 1480, 1),
    (1391, 1480, 1),
    (1407, 740, 1),
    (2381, 1480, 1),
    (2487, 2960, 1),
    (2821, 740, 1),
    (2853, 740, 1),
    (2959, 4902, 1),
    (3137, 740, 1),
    (3150, 740, 1),
    (3955, 2960, 1),
    (4711, 1480, 1),
    (5476, 2960, 1),
    (6187, 740, 1),
    (7253, 2960, 1),
    (8568, 2960, 1),
    (10112, 2960, 1),
    (11636, 740, 1),
    (17855, 4902, 1),
    (20842, 4532, 1),
    (23861, 2960, 1),
    (26944, 1480, 1),
)
