# GridSignal Simulator — Implementation Skeleton

Working `RunManager` / `AssetModule` skeleton for the design specified in
*GridSignal Simulator — Design Specification*, v1.0. All 10 included
tests pass; this is runnable code, not pseudocode.

```
gridsignal_sim/
├── core/                        # deterministic, synchronous, no asyncio
│   ├── models.py                 # dataclasses: WorkloadSignal, configs, TickResult
│   ├── asset_modules.py          # AssetModule ABC + GPU/BESS/Turbine/Solar/Cooling
│   ├── dispatch.py               # CheckpointClassifier, DispatchArbitrator, ConfidenceEngine
│   ├── simulation_core.py        # evaluate_tick() — the single fixed-order orchestrator
│   └── scenario_factory.py       # test/demo convenience: builds a RunContext quickly
├── runtime/                      # asyncio concurrency layer — the only place asyncio appears
│   ├── run_manager.py            # RunContext, RunManager, WebSocketHub
│   └── example_usage.py          # runnable demo: 3 concurrent runs on one RunManager
├── tests/
│   ├── test_formulas.py          # whitebox tests, ported from source spec Addendum A (TC-01 etc.)
│   └── test_concurrency.py       # isolation, no head-of-line blocking, determinism-under-load
├── scripts/
│   └── load_test.py              # standalone load harness — Design Spec §9 / §12, usable as a CI gate
└── pytest.ini
```

## Design-spec correspondence

## Fuel-cell inverter MVA assumption

For a block-addressable fuel-cell unit,
`apparent_power_rating_mva_per_block` is fixed installed inverter hardware
rating and the array rating is `block_count × rating`; it is never inferred
from power factor. When omitted it defaults exactly to `block_rated_mw`. That
equality is an assumption, not vendor data: vendor inverter kVA is unpublished,
so dependent real-capacity, reactive, apparent-loading, reserve, and
commitment telemetry is explicitly marked low confidence. Authors should supply
the site-specific MVA rating to restore normal site confidence. Real output per
block is physically limited to
`min(block_rated_mw, apparent_power_rating_mva_per_block × power_factor)`.

## Fuel-cell intrinsic output ramp

Every synchronized, producing block-addressable fuel-cell block has an
always-on real-power ramp limit, including when no optional fuel manifold is
configured. The default proposed rate is `effective_block_rated_mw / 3 s`: the
initial-slope equivalent `P/τ` of the existing three-second first-order
fuel-to-power lag. A constant MW/s ramp cannot duplicate an exponential
response at every instant; this derivation matches its maximum initial slope
without inventing a settling threshold. Optional pressure, delivered-fuel, and
utilisation constraints are applied after the intrinsic ramp and may only
reduce achievable output further. Synchronization establishes the
minimum-stable floor after start dwell; stops and protection trips disconnect
to zero rather than operating below that stable floor.

| Skeleton piece | Design Spec section |
|---|---|
| `core/*` being plain sync Python with zero `asyncio` imports | §2 principle 2 ("fidelity over cleverness") and §4.3 |
| `evaluate_tick()`'s fixed call order (GPU → Cooling → Turbine/BESS → Solar → Classifier → Confidence) | §5, §10.1 |
| `RunContext` owning all mutable state for one run, sharing nothing with siblings | §4.2 |
| `RunManager._drive()` — one `asyncio.Task` per run, `await`s at every I/O point | §4.2, code sample in §4.2 |
| `WebSocketHub.broadcast()` using `asyncio.gather` with per-socket exception isolation | §4.4 |
| `TimeseriesSink` protocol (swap `InMemoryTimeseriesSink` for a real SQLAlchemy-async sink) | §6 |

## Running it

```bash
cd gridsignal_sim
PYTHONPATH=. python -m pytest tests/ -v          # 10 tests, all passing
PYTHONPATH=. python runtime/example_usage.py      # 3 concurrent runs, printed results

# Load test — Design Spec §9's validation plan, made executable:
PYTHONPATH=. python scripts/load_test.py                              # NFR-exact: 5 runs, 50/8/4/4 assets, 4h
PYTHONPATH=. python scripts/load_test.py --matrix                     # 1x/2x/4x headroom sweep (§9)
PYTHONPATH=. python scripts/load_test.py --report-json out.json       # machine-readable, for CI (§12.5)
# exits 1 on any NFR violation — usable directly as a CI gate
```

**Measured results at exact NFR scale** (5 concurrent runs × 50 GPU modules / 8 turbines / 4 BESS / 4
solar, 4-simulated-hour scenario, "max" playback speed):

| NFR (functional spec §11) | Budget | Measured |
|---|---|---|
| Dashboard update latency | < 1000 ms | p99 ≈ 5 ms |
| 4h scenario wall-clock | < 30 s | ≈ 12 s |
| `evaluate_tick()` compute time | (Design Spec §4.3 claim: 0.3–0.5 ms) | p50 ≈ 0.76 ms, p99 ≈ 1.2 ms — same order of magnitude as claimed; the claim's 66-asset estimate undercounts the checkpoint-classifier's per-job history bookkeeping, which dominates actual cost |

The `--matrix` sweep additionally shows where the *current* single-process design's headroom runs out: 2x NFR scale still passes (≈25s), 4x fails the 30s wall-clock budget (≈47s) — useful evidence for if/when the `ProcessPoolExecutor` scale-out path (Design Spec §4.5) actually becomes necessary. It isn't necessary at the scale the functional spec specifies.

**A real bug this script caught:** the first version of `SimulationState.apply_workload_signal` broadcast every `WorkloadSignal` to *every* GPU module instead of routing it to the one module it belongs to. At 1 module (the default test/demo scale) this is invisible. At 50 modules it meant every module accumulated all 50 jobs' node counts, and checkpoint classification ran 2,500 times/tick instead of 50 — a single-run 4h scenario went from ~12s to "still running after several minutes." Fixed by tracking job→module ownership in `SimulationState`. This is exactly the kind of thing Design Spec §4.3's back-of-envelope estimate can't catch and a load test at real NFR scale can.

## What's deliberately stubbed, not implemented

These are marked with `TODO` or noted inline — they're real work items for
the build, not oversights in the skeleton:

- **Persistence**: `InMemoryTimeseriesSink` stands in for the SQLAlchemy-async
  + SQLite sink described in Design Spec §6.
- **Scenario pass/fail verdicts**: `RunManager._drive()`'s `finally` block has
  a `TODO` where scenario assertion evaluation (functional spec §6/§7.2) goes.
- **Per-job draw attribution**: `simulation_core.py` classifies checkpoints
  against a GPU module's *aggregate* draw, correct for one-job-per-module
  starter scenarios (functional spec §6.4) but flagged inline as needing
  extension for multiple concurrent jobs sharing a module.
- **BESS fleet arbitration**: multiple BESS units currently all see the same
  shortfall figure rather than a coordinated split — noted inline in
  `dispatch.py`.
- **REST/WebSocket wiring to FastAPI**: `WebSocketHub` is defined against a
  minimal `Protocol` (`send_json`) specifically so it doesn't require a real
  ASGI server to test (Design Spec §12) — wiring an actual FastAPI
  `WebSocket` object in is a thin adapter, not shown here.
- **Scenario Builder / stressor injection**: `core/scenario_factory.py` is a
  test convenience, not the real Scenario Builder (functional spec §7.2) or
  its injectable stressors (functional spec §6.2).
