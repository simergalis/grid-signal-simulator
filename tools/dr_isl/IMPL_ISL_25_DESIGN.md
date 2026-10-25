# IMPL-ISL-25 — S10 MCP study-class design

**Status:** design only; no application code, tests, or scenario files were changed.

**Requested base:** `889a36f` (as supplied). At inspection, repository `HEAD` was `0dfc2bae0fa1be417a864c412f2959361c4f8cb7`, parent `889a36f6399638295f5462f0a95f63bd04cfdd2d`, commit subject `Published your App` (2026-10-25 03:16:17 UTC). This note is based on the observed current tree; this work did not publish, deploy, or push.

## 1. Current state

### MCP exposure and scenario gate

- `mcp_server/server.py:60–69` defines four Addendum H reference scenario IDs, the base-demo ID, `STUDY_SCENARIOS`, and `SCENARIO_IDS = STUDY_SCENARIOS`. Thus the MCP study allowlist is five scenario IDs: four H variants plus base demo.
- `_scenario_path()` at `mcp_server/server.py:219–226` refuses IDs outside `SCENARIO_IDS` and maps an accepted ID to `config/scenarios/<id>.json`.
- `scenario_list()` at `mcp_server/server.py:330–345` iterates that allowlist and reports each scenario's `kind`, `study_supported`, and resolved `study_class`. `scenario()` at `:347–353` returns the source path and JSON spec.
- `_call_tool()` routes `list_scenarios`, `get_scenario`, `get_run_metrics`, `compare_runs`, and `start_run` at `mcp_server/server.py:1252–1298`. `start()` independently rejects scenario IDs outside `STUDY_SCENARIOS` at `:445–450`.
- The currently supported class resolver is in `study_harness/executor.py:72–80`: `addendum_h` for `REFERENCE_IDS`, `base_demo` for `scenario-uneven-multisched-01`, and `UnsupportedScenarioError` otherwise. Those are two study classes, even though the MCP list contains five scenario IDs.
- The current base-demo fallback in `_expanded_spec()` is `study_harness/executor.py:282–317`. If a new ID is added to the resolver but not given its own expansion branch, it will enter the existing non-H branch and load the base-demo JSON at `:294–305`. That would be wrong for S10.

### Existing expansion and A/B behavior

- Addendum H expansion is intentionally separate: `executor.py:289–293` calls `expand_phase2b_reference_spec()`. That function loads the referenced base JSON and expands the compact H entry at `runtime/phase2b_reference.py:87–118`; it applies the study fuel overlay at `:113–115`.
- Base demo is canonicalized through `ScenarioSpec.model_validate_json(...).model_dump(mode="json")` at `executor.py:301–305`, then gets the post-validation `apply_study_fuel_model()` overlay at `:306–317`. That helper copies each turbine and sets `gt_mode="aero"` (`runtime/phase2b_reference.py:41–49`).
- Both classes use `_probe()` in baseline mode (`executor.py:342–376`). The probe captures per-tick compute/cooling demand replay and workload signal events. `_run_mode()` places the same replay events and demand replay into each arm, then sets the arm's `turbine_commitment_mode` at `:378–426`. `run_pair()` passes those same probe outputs to baseline and informed at `:677–732`.
- Therefore the proposed S10 pair should share one expanded S10 spec, one resolved seed manifest, the same 239-event workload input and replay, and the same 320-point non-GPU profile. The mode-specific spec field remains `turbine_commitment_mode`; the informed controller path is selected by the existing `mode` execution. The workload, fuel, operating-cost inputs, duration, and seed must not be independently regenerated per arm.
- The current `identical_compute_trace` condition compares `compute_trace_sha256` (`study_harness/acceptance.py:140–144`); the trace currently hashes only `p_compute_demand_mw` (`study_harness/metrics.py:211–224`). It does not itself prove that S10's non-GPU profile is identical. The S10 design should also record/compare the canonical profile digest and confirm per-tick `p_non_gpu_demand_mw` parity between arms, without changing the existing 10-condition verdict schema.

### Identity, seed, and cache

- `RunIdentity` fields are `scenario_id`, `mode`, `parameter_set`, `seed`, `duration_seconds`, `tick_seconds`, `engine_commit`, and `harness_commit` (`study_harness/manifest.py:12–24`). `make_run_identity()` stores those fields at `:36–56`; `digest` is SHA-256 of sorted, compact JSON at `:26–33`.
- `make_study_run_identity()` adds `turbine_commitment_mode`, `study_class`, `frequency_reporting_metrics_version`, `study_identity_version`, and `seed_derivation_version` to `parameter_set` (`executor.py:83–113`). It removes `kube_clusters`, `slurm_config`, and `workload_events` at `:95–99`.
- The cache key is `identity.digest`: `RunManifestCache.get()` indexes `manifest["runs"]` by the digest and `put()` stores the record as `<digest>.json` (`study_harness/manifest.py:72–96`). MCP uses the same digest for its run ID and cache lookup (`mcp_server/server.py:474–478`).
- Current `STUDY_IDENTITY_VERSION` is **3** (`executor.py:51–53`). Keep the global version at 3 for this additive class. Bumping the global version would change existing base/H identities and invalidate their cache keys. Instead, add the new `study_class="supercloud_replay"` and an S10-only canonical `workload_events_sha256` identity parameter. S10 has no prior MCP cache because it is not currently accepted; existing class mappings and identity inputs must remain byte-identical.
- **Cache risk to address:** although the executor comment says replay content is separately hashed (`executor.py:97–98`), `workload_events` is removed before the digest is formed, and the cache lookup occurs before execution. Add the S10 event-source digest to its identity parameters; keep `non_gpu_load_profile_mw` in the spec-derived parameters (it is not removed). This prevents an edited S10 event timeline from reusing a stale S10 cache entry. Keep the two elements S10-specific so existing identities do not change.
- D4 seed resolution is already shared. MCP `start()` calculates the cache-bypass reason, resolves a seed manifest, then makes identity (`server.py:457–474`); `_identity()` uses the resolved root seed at `:406–433`. The resolver records a drawn root and stable derived consumer seeds (`runtime/seed_resolution.py:15–80`). Null-seed requests with cache reuse bypass cache (`executor.py:56–69` and `server.py:460–465`). Tests and parity runs should use an explicit recorded seed; do not add a second seed resolver.

## 2. Proposed class and S10 expansion

Use the proposed class name **`supercloud_replay`**. Add S10 additively to the existing tuple without reordering existing entries; map only `S10_mit_supercloud_2021-08-11` to the new class. Update the list's `kind` label so it is not mislabeled as the base demo.

In the one `_expanded_spec()` path, add an explicit class branch that reads S10's own tracked JSON at `config/scenarios/S10_mit_supercloud_2021-08-11.json`, validates it through `ScenarioSpec`, and emits `model_dump(mode="json")`. Prefer a shared canonical JSON loading helper for the base-demo and S10 branches; keep the separate H expansion intact. Do not use the base-demo path or create a second MCP-only expansion implementation.

The tracked S10 file is 24 hours (`end_sim_time=86400.0`, line 2496), with 239 `workload_events` entries (array begins at line 4), five turbine fuel blocks (first begins at line 2191), a 320-point `non_gpu_load_profile_mw` (line 2530), and `operating_cost_inputs` (line 3812). Its own fuel and operating-cost inputs are already present: **skip `apply_study_fuel_model()` for S10**. Applying that helper would overwrite turbine `gt_mode` with `"aero"` (`phase2b_reference.py:41–49`) and is not part of this class's expansion.

For the default comparison, make no scenario-content override. The common S10 spec keeps its original event list, CPU/non-GPU profile, fuel blocks, and operating-cost inputs; only the baseline/informed mode field and the existing common replay inputs vary by run. Any accepted request `parameter_overrides` must remain part of the expanded spec and its identity; the certified/default S10 pair uses none.

## 3. Run identity and cache design

The default S10 identity should include the existing `RunIdentity` fields, `study_class="supercloud_replay"`, the current v3/seed-derivation/frequency-metrics version values, the arm mode, the canonical S10 spec fields, and `workload_events_sha256`. The non-GPU profile remains in the canonical spec parameters. This ensures:

1. S10 baseline and informed identities are distinct because `mode` differs.
2. S10 cannot collide with base demo or H identities because both `scenario_id` and `study_class` differ.
3. An S10 event-timeline change invalidates only S10's cache key.
4. Existing base/H identities and their caches remain unchanged because their identity version and parameter construction remain untouched.

For `seed=None`, retain D4 behavior: draw and record a root seed, bypass cache, and return the existing cache-bypass reason. For an explicit seed, reuse the same resolved manifest for the probe and both arms. A requested seed and its recorded manifest root must match.

## 4. S10 compare acceptance and frequency validity

Use the existing 10 conditions unchanged: build parity; baseline and informed validity; baseline and informed energy balance; baseline and informed fuel reconciliation; identical compute trace; informed unserved energy no worse; informed peak unserved no worse (`study_harness/acceptance.py:11–21, 128–153`). `compare()` also rejects mismatched study classes (`mcp_server/server.py:760–776`). Both S10 arms therefore use `supercloud_replay`.

S10 is islanded, but its resolved UF/OF/collapse thresholds, UFLS stages, and 81U threshold are null (`config/scenarios/S10_mit_supercloud_2021-08-11.json:2484–2493`); it has no configured fuel-cell arrays. The configured-feedback predicate checks those thresholds, relays, stages, and FC ride-through (`core/frequency_reporting.py:29–64`), so S10's `frequency_feedback_configured` is false. Under the existing fail-closed rule, known `False` makes frequency validity pass regardless of the invalid tick count (`study_harness/acceptance.py:29–41`); the count/fraction remain reported and informative. Do not add an eleventh condition or loosen any other condition. Whether Lloyd wants S10 treated as certified is an open decision below.

## 5. MCP exposure; REST/UI boundary

The MCP `energy` metrics section already conditionally returns `operating_cost` alongside frequency fields (`mcp_server/server.py:621–648`); study metrics compute itemized operating cost when the scenario includes `operating_cost_inputs` (`executor.py:526–575`). The existing tool dispatcher routes `get_run_metrics` and `compare_runs` generically (`mcp_server/server.py:1258–1269`), so the new records can use the existing sections and comparison response.

This is an additive MCP/harness feature. Do not change the REST or Scenario Planner paths. S10 remains the same tracked REST/UI scenario; the MCP class must not create a second source or alter what those existing paths read.

## 6. Risks and invariants

- Base demo, H1-24h, and H2-24h identities, physical hashes, metrics, and 10/10 compare verdicts must remain byte-identical to the D6c evidence. Do not bump global study identity version 3.
- Existing `ctx.step()` hashes remain unchanged.
- The accepted pinned S10 physical reference remains `ad91ced6445f21aa4a9a9b4ccb2fb4dd5114d42f2eae3ab5e0be5769fceaf508` (non-fuel `e0ccf0e15265d70738e53c74d273e8ab223d9b30b4439797b8188cb76be7aaba`), as recorded in `tools/dr_isl/D6C_REPORT.md`.
- Do not apply the base/H fuel overlay to S10; do not mutate its recorded GPU event schedule or non-GPU profile.
- Do not duplicate expansion in the MCP service. The harness expansion, seed manifest, identity, cache, and execution remain the single path used by `start_run` and `compare_runs`.
- Cache identity must account for S10's workload-event source even though the generic identity helper currently removes `workload_events`.

## 7. Proposed test plan (ID collision check)

The current simulator tests use TC-ISL IDs through **64**; no IDs 65–73 were found. Reserve the following proposed IDs for implementation:

- **TC-ISL-65:** `list_scenarios` includes S10 with `supercloud_replay`; `get_scenario` returns the exact S10 source path.
- **TC-ISL-66:** `start_run` accepts S10 for both modes and rejects neither arm; `get_run_metrics` exposes its operating-cost section.
- **TC-ISL-67:** S10 expansion loads and canonicalizes S10's own JSON; the five fuel blocks and operating-cost inputs are unchanged; the base-demo JSON and `apply_study_fuel_model()` are not used.
- **TC-ISL-68:** the common baseline probe and both arms use the same 239-event workload replay and same 320-point non-GPU profile; compute trace hashes match and the non-GPU profile/per-tick quantities match.
- **TC-ISL-69:** seed manifest and S10 event-source digest are present in identity; S10 baseline/informed identities are isolated from each other and from base/H; explicit-seed cache reuse works and null-seed requests bypass cache.
- **TC-ISL-70:** S10 `compare_runs` reports the existing 10 conditions, includes frequency fields, and applies the current `frequency_feedback_configured=False` validity behavior.
- **TC-ISL-71:** MCP-vs-REST S10 per-tick parity over all 17,280 ticks for the D6b.3(a) physical field set. Use the recorded REST rounding rule: selected numeric values round to 4 decimals, absolute tolerance `0.00005`; discrete fields (state, `frequency_valid`, start count) exact (`tools/dr_isl/d6b/D6B_3_REST_PHYSICS_COMPARE.json:661`). Exclude the same identity/context/reporting fields as that D6b comparison.
- **TC-ISL-72:** cache/source change invalidates S10 only; existing study identities and caches remain unchanged.
- **TC-ISL-73:** base/H study gates and the existing-scenario hash suite remain identical to D6c.

## 8. Questions for Lloyd

1. Should S10's `supercloud_replay` pair be only an operational comparison, or a protected/certified study with its own approval record?
2. Is the one-day 2021-08-11 trace the intended long-term study unit, or should a later, separate phase cover seven days or multiple SuperCloud dates?
3. What maximum runtime should gate MCP execution? S10 is 17,280 five-second ticks; the request estimates production 24-hour runs at roughly 25–40 minutes each. Confirm whether that is acceptable for two arms plus probe and cache misses.
4. Should MCP permit arbitrary `parameter_overrides` for S10, or restrict them to preserve the published candidate inputs? The default accepted pair should use none either way.

## 9. Estimated implementation scope

Expected changes: `mcp_server/server.py` (allowlist, listing kind, resolver-facing routes), `study_harness/executor.py` (explicit S10 class expansion and S10-only event digest), and focused MCP/study-harness tests (about two test files; an additional focused file is optional). `manifest.py` and `acceptance.py` should not need changes if the digest is added to the existing identity `parameter_set` and the 10 conditions are reused. Add a short implementation/evidence report after approval. Estimate: roughly 100–200 production/test lines across 4–6 files, excluding the evidence report.

Suggested gates after approval: implement the single expansion branch; run focused TC-ISL-65–73; verify S10 MCP-vs-REST tick parity and accepted S10 hash; verify byte-identical base/H identities and metrics plus existing scenario hashes; then run the full suite under two `PYTHONHASHSEED` values.
