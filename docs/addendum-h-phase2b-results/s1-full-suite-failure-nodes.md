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