# Phase 6 D4 implementation progress

Base application commit: `f6ac658`.

## Implemented so far

- Added a shared keyed SHA-256 seed resolver in `runtime/seed_resolution.py`.
- Added the shared incremental physical-tick identity contract in `core/physical_identity.py`.
- Wired build-time seed manifests through spec, direct, load-test, API, and study-harness context creation.
- Added per-diesel RNG seeds, stable fabric seeds, stable generated fallback event IDs, SCADA/price/de-identification seeds, and SolarSim run seeding.
- Materialized the API run seed manifest and generator seeds before external timeline generation; retained the generated SolarSim MW input trace in run metadata and support trace replay from a recorded trace.
- Changed study/headless advisory cadence to simulation time; interactive runs retain wall-clock cadence.
- Added the physical identity digest to RunManager metadata and the study run record.
- Added study identity version 3 and the seed-derivation version to cache identity.
- Updated `tools/dr_isl/baseline_runner.py` to use the shared identity helper and stream hashes without writing per-tick exports.

## Focused verification

`python -m py_compile` passed for the modified Python modules.

`pytest -q tests/test_dr_isl_phase6_reproducibility.py tests/test_dr_isl_frequency_feedback.py --disable-warnings`
passed: **22 passed in 3.17s**.

TC-ISL-34–40 cover null seed recording/reuse, cross-process seed derivation, diesel RNG assignment, fabric seed wiring, physical-hash exclusions, advisory cadence, and replay from a recorded seed.

## Acceptance status

The fixed-seed study acceptance gate and unpinned multi-process scenario matrix have not run yet. No Phase 6 acceptance claim is made here.
