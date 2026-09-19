# S1 full-suite failure-node comparison

The two reproducibility runs used:

```text
cd attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2
PYTHONPATH=gridsignal_sim pytest -q --disable-warnings
```

Both runs completed with `82 failed, 2,013 passed, 3 skipped, 23 xfailed, 54
warnings, 3 subtests passed`. Run 1 took `573.85s`; run 2 took `576.38s`.
The sorted 82-node failure set is committed in
`s1-full-suite-failure-nodes.txt`.

## Back-to-back set difference

```text
r1 - r2: none
r2 - r1: none
symmetric difference: 0 nodes
```

The identical set proves the full-suite failures are reproducible on unchanged
code. The GPU load-profile node is absent from both runs after the test-only
completion polling fix. No failure was weakened, skipped, deleted, or
strict-xfailed.

## S1-focused verification

The focused harness suite passed:

```text
10 passed
```

The H-1 bounded/unbounded determinism test ran the full 24-hour informed path
and matched the complete metric set; its evidence is in
`forecast-history-determinism.md`.
The induced-miss test still reports exactly one deliberate forecast miss. The
seven-day replay has zero H-1 informed misses and 39 H-2 informed misses.
The S1 changes therefore did not make forecast-miss accounting vacuous.

## S3 MCP regression comparison

After adding the isolated S3 MCP boundary, the same full-suite command was run
twice without test selection changes, skips, or xfails:

```text
cd attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2
PYTHONPATH=gridsignal_sim pytest -q --disable-warnings
```

Run 1 completed with `82 failed, 2,015 passed, 3 skipped, 23 xfailed, 54
warnings, 3 subtests passed` in `573.87s`.

Run 2 completed with `82 failed, 2,015 passed, 3 skipped, 23 xfailed, 54
warnings, 3 subtests passed` in `575.88s`.

The two sorted S3 failure lists are recorded in:

- `s3-run1-failure-nodes.txt`
- `s3-run2-failure-nodes.txt`

The S3 failure-node set difference is empty:

```text
s3 run 1 - s3 run 2: none
s3 run 2 - s3 run 1: none
symmetric difference: 0 nodes
s3 run 1 - prior 82-node baseline: none
prior 82-node baseline - s3 run 1: none
```

The two additional passing tests are the focused MCP HTTP regression tests;
the pre-existing 82 failure nodes are unchanged.