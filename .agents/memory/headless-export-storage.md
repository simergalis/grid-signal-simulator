---
name: Headless export storage
description: Separate scratch capacity and failure handling for verbose baseline exports
---

Check the actual scratch filesystem capacity before running verbose headless exports. In this workspace, `/tmp` was a separate 4 GiB tmpfs even though the workspace filesystem had hundreds of GiB available. A single incomplete Slurm GPU-peaks JSONL export exceeded 2 GiB.

**Why:** Exhausting `/tmp` stopped the baseline writer, concurrent study-artifact writes, and the full-suite JUnit writer. A large available workspace filesystem does not imply space is available at the prescribed scratch path.

**How to apply:** Check `df` for the actual output directory. If the user prescribes `/tmp` and exports cannot fit, request authorization for disk-backed scratch instead of silently moving files. After exhaustion, preserve failure evidence and the partial export's size/hash before removing only generated incomplete output. Never treat a partial JSONL or empty JUnit file as completed validation.

For the DR-ISL programme, the user subsequently required streaming physical hashes and metric accumulators in memory, not full per-tick exports for long runs. Persist only summaries, hashes and requested windows; cap each scratch file at 200 MB and STOP if the requirement cannot fit.

**Why:** The user chose bounded streaming after the scratch-exhaustion stop, rather than authorizing large disk-backed exports.

**How to apply:** Do not invoke the persisted baseline runner's full-export mode for long programme checks. Preserve its seeder, pinning and hash contract through an output-only streaming adapter, without changing simulation inputs.

Persist bounded verification summaries, exact hashes, final test counts and
failing-ID lists incrementally under `tools/dr_isl/`, not only in `/tmp`.

**Why:** Scratch directories and background-shell logs disappeared after a
long validation run, while the workspace failing-ID list survived. A successful
process exit or a passing observation does not ensure its evidence survives.

**How to apply:** Flush each completed gate's bounded evidence to the workspace
before starting the next gate. Retain the no-full-tick-export rule and file-size
cap. If scratch disappears, report the missing evidence explicitly; do not
reconstruct unobserved final counts or silently rerun past a STOP gate.
