# S1 full-suite failure-node comparison

The post-change full suite used:

```text
cd attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2
PYTHONPATH=gridsignal_sim pytest -q --disable-warnings
```

The prior captured result was `82 failed, 2,010 passed, 3 skipped, 23
xfailed`. The fresh result was `83 failed, 2,011 passed, 3 skipped, 23
xfailed, 54 warnings, 3 subtests passed`.

The prior failure log was not retained in `/tmp`, so the before set was
reconstructed from the complete failure list in the previous version of this
report. The fresh failure set was extracted from
`/tmp/s1-post-full-suite-r2.log`.

## Set difference

```text
before - after:
gridsignal_sim/tests/test_step8_scenarios.py::test_list_includes_seeded_and_created

after - before:
gridsignal_sim/tests/test_gpu_load_profile.py::test_gpu_load_profile
gridsignal_sim/tests/test_step8_scenarios.py::TestScenarioCRUD::test_list_includes_seeded_and_created

symmetric difference: 3 nodes
```

The Step 8 difference is a pytest node-id change from the unqualified function
name to the class-qualified name, not a second scenario failure. The GPU load
profile node is the one genuinely new failure in the set comparison; it is
outside the S1 harness files and was not weakened or xfailed.

## S1-focused verification

The focused harness suite passed:

```text
9 passed
```

The induced-miss test still reports exactly one deliberate forecast miss. The
seven-day replay has zero H-1 informed misses and 39 H-2 informed misses.
The S1 changes therefore did not make forecast-miss accounting vacuous.