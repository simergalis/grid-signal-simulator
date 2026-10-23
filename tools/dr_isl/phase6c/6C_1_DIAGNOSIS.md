# Phase 6c.1 — null-seed cache failure diagnosis

- Reproduction: `tests/test_mcp_server.py::test_mcp_cache_hit_and_build_parity_error` failed in isolation with `assert result["cache_hit"] is True`; actual `False`, expected `True` (`tests/test_mcp_server.py:217`). Full traceback is preserved in `6C_1_CACHE_FAILURE.log`.
- Fixture cache identity: `_identity(..., seed=None)` at `tests/test_mcp_server.py:182–187`; the `start_run` request omits `seed` at `:207–215`.
- Candidate start path resolves `seed_manifest` before identity at `mcp_server/server.py:456–466`; `_identity` uses `seed_manifest["root_seed"]` at `:419–428`. For a null request, `resolve_run_seed_manifest` marks `root_seed_drawn=True` and generates a fresh 64-bit seed with `secrets.randbits(64)` at `runtime/seed_resolution.py:43–47`.
- The cache key therefore contains the fresh root seed, while the test fixture cached an identity with seed `None`; lookup misses and the endpoint queues a fresh run (`mcp_server/server.py:468–469, 497–525`). This is the exact Phase 6b D4 seed-in-identity behavior, not a build-parity mismatch.
- The deterministic cache-hit control will use explicit seed `42` consistently for both the fixture identity and request. Its actual pass result is recorded after the focused test in 6c.3.
- Diagnosis: matches 6c.1's permitted cause; proceed to 6c.2.
