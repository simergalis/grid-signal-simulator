# P2 GPU profile diagnosis

No test or application code changed for P2. Both versions used fresh isolated API processes for each context, the built-in pytest startup context (skips unrelated DB forecast import), and an HTTP loopback port redirect only.

| Version | Context | GPU result |
|---|---|---|
| base | isolation1 | passed |
| base | isolation2 | passed |
| base | isolation3 | passed |
| base | file | failed |
| base | prefix | failed |
| candidate | isolation1 | passed |
| candidate | isolation2 | passed |
| candidate | isolation3 | passed |
| candidate | file | passed |
| candidate | prefix | passed |

Base file: interval-end2400s, fraction0.5, expected0.1. Base prefix: interval-end720s, fraction1.0, expected0.5. Both assertions are tests/test_gpu_load_profile.py:169 via284.

The test lookup uses the result timestamp (tests/test_gpu_load_profile.py:82-89,146-169); the simulation evaluates the profile at interval start (core/simulation_core.py:1233) and stamps the result at interval end (:3818-3822). HTTP polling every0.3s sometimes observes the boundary tick and sometimes skips it. The shared runtime snapshot is WebSocketHub._latest_ticks (runtime/run_manager.py:186,231-237,263), read by api/routes/runs.py:937-938. No evidence identifies a polluted pytest module singleton.

Classification: pre-existing context-/timing-dependent boundary sampling (IMPL-SSH-07 family), not a Phase4 regression. All six isolated runs passed, and the base full-prefix context reproduced the exact earlier720s signature. The common preceding node order is identical; candidate additionally has12 new reserve cases. Base prefix774cases/9failures; candidate786cases/8failures,0 added against the known list. Full-order lists and per-case XML/JSON are retained.

The lookup AST and GPU test SHA-256 are identical between base and candidate; see P2_SOURCE_PROOF.json. Do not modify the test in this phase. A future test correction would align its boundary expectation with interval-end telemetry, rather than change physics or add sleeps.
