---
name: Headless export storage
description: Separate scratch capacity and failure handling for verbose baseline exports
---

Check the actual scratch filesystem capacity before running verbose headless exports. In this workspace, `/tmp` was a separate 4 GiB tmpfs even though the workspace filesystem had hundreds of GiB available. A single incomplete Slurm GPU-peaks JSONL export exceeded 2 GiB.

**Why:** Exhausting `/tmp` stopped the baseline writer, concurrent study-artifact writes, and the full-suite JUnit writer. A large available workspace filesystem does not imply space is available at the prescribed scratch path.

**How to apply:** Check `df` for the actual output directory. If the user prescribes `/tmp` and exports cannot fit, request authorization for disk-backed scratch instead of silently moving files. After exhaustion, preserve failure evidence and the partial export's size/hash before removing only generated incomplete output. Never treat a partial JSONL or empty JUnit file as completed validation.
