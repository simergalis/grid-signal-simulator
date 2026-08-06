# Phase B — Interval ordering and the single-writer guard

**Follows:** Phase A complete. Structures added, unwired; eight thresholds catalogued; Guard D1 green.
**Baseline:** 12 failed, 965 passed, 3 xfailed, 977 collected, 0 errors from canonical CWD `gridsignal_sim/`.
**Target model:** `backend/core/` — the live engine. **Not** `gridsignal_logger.py`.
**Scope:** two mechanisms, two tests, three carry-over items. No Phase C or D work.

Phase B establishes the invariant everything after it depends on: **a unit's output has exactly one writer per evaluation interval.** Get this wrong and every ramp-dependent result in Phases C through E is unverifiable.

---

## Item 1 — Loaded set from interval-entry state

`advance()` runs before `_synchronised_units` is rebuilt in the same tick. A unit promoted RAMPING → SYNCHRONISED inside `advance()` therefore has its output written by `advance()` — which snaps it to `_target_mw` — and again by `apply_loading()` before the interval ends. Two writes, one interval, and the step between them is not bounded by `r_asset × dt`.

`_check_loading_exclusion` does not catch it. That function tests **set membership**, and both writes are individually legitimate under a membership test.

**Fix:** determine the loaded set from unit states as they stand at interval entry. In `evaluate_tick`, before the `advance()` loop:

```python
_entry_states = {t.config.asset_id: t.state for t in state.turbines}
for t in state.turbines:
    t.begin_interval()
```

Build `_synchronised_units` from `_entry_states`, not from live state. A unit promoted during `advance()` is first loaded in the **following** interval.

Verify the current line numbers before editing — `core/simulation_core.py` and `core/models.py` both shifted during the configuration refactor.

## Item 2 — Write counter on the field

Replace membership checking with a count on the field itself, in `TurbineModule.set_output`:

```python
def set_output(self, new_output_mw: float) -> None:
    self._output_writes += 1
    if self._output_writes > 1:
        raise RuntimeError(                       # not assert — must survive -O
            f"{self.config.asset_id}: output written {self._output_writes}x in "
            f"one interval (state={self.state.value}). §7.1.3.1 permits one."
        )
    self._current_output_mw = max(0.0, min(new_output_mw, self.config.rated_mw))
```

`begin_interval()` resets the counter. `RuntimeError`, not `assert` — an assertion disappears under `-O` and this guard has to hold in production.

Leave `_check_loading_exclusion` in place for now; it is deleted in Phase C along with the legacy states it checks.

## Item 3 — TC-87 and TC-88

**TC-87 — ramp is rate-determined, not setpoint-determined.** A committed unit tracking a rising setpoint. Assert output at interval *n* equals `n × r_asset × dt` — the accumulated integral — independent of what the setpoint is doing. The current engine can produce the right value for the wrong reason when demand happens to rise alongside the ramp; this test must not be satisfiable that way.

**TC-88 — a unit promoted during `advance()` is not loaded in the interval of its promotion.** Drive a unit to synchronise inside `advance()`, then assert its output is unchanged for that interval and that its first loaded interval is the next one, bounded by `r_asset × dt`.

**TC-88 must be confirmed failing before the Item 1 change and passing after. Report both results.** A fix verified only by tests that already passed proves nothing about whether the ordering defect existed.

---

## Carry-over items

**C-1. Flip TC-89, TC-90 and TC-91 to `strict=True`.**

They are currently `xfail(strict=False)`, which means that when Phase D makes them pass they will report as xpass and say nothing. The whole point of writing them early is that they announce when commitment starts working. Under `strict=True` an unexpected pass fails the suite, which is the signal you want.

They must still fail — not error — at the end of Phase B. Confirm.

**C-2. Report which fixtures carry a non-zero `p_min_stable_frac`.**

Phase A's Item 3 found `demo-20mw` equilibrium demand at ~2.8 MW *"because `p_min_stable_frac=0.40` sets the floor"*. The configuration refactor found the default to be 0.0. Both cannot describe the same fixture set.

Report, per scenario fixture, the configured `p_min_stable_frac`. This determines Phase E's blast radius — if several fixtures already run at 0.40, flipping the default moves fewer numbers than expected; if none do and `demo-20mw` is special, Phase A's measurement needs re-reading.

**C-3. §7.1.3.8 needs rewriting — report, do not edit the spec.**

Phase A measured the degraded-N−1 window as **unbounded**: at 40% utilisation the headroom check never fires, so coverage stays `COVERED_WITH_SHED` for the entire run. §7.1.3.8 currently frames degradation during commitment as expected and bounded by the start sequence, which presumes commitment eventually happens.

Confirm the measurement holds against the reverted code — Phase A took it under the since-reverted sequential-start change, so it needs re-taking against what is now in the tree. Report the result. The spec edit is mine to make; you supply the number.

---

## Prohibited

- Any Phase C work — no state deletions, no `is_synchronised` rename, no `UNLOADING`, no payload rename.
- Any Phase D work — no wiring of `evaluate_commitment()`, no call sites.
- Deleting `_check_loading_exclusion` — that is Phase C.
- Using `assert` for the write guard.
- Editing any test assertion or fixture. `test_tc_p0_1/2/3/5` are Phase C.
- Editing the spec. Report the C-3 measurement; the amendment is made elsewhere.
- Writing any new physical constant as a code literal.
- Adding a module-scope numeric constant to `panels/`.
- Modifying `gridsignal_logger.py`.
- Proceeding past the Item 3 gate without reporting both TC-88 results.

## Acceptance criteria

- [ ] Loaded set built from interval-entry state; `begin_interval()` called before `advance()`.
- [ ] Write counter on `set_output`, raising `RuntimeError`, reset per interval.
- [ ] TC-87 passing, and demonstrably not satisfiable by a setpoint that happens to track the ramp.
- [ ] TC-88 confirmed failing pre-fix and passing post-fix, **both results reported**.
- [ ] TC-89, TC-90, TC-91 flipped to `strict=True` and still failing, not erroring.
- [ ] `p_min_stable_frac` reported per scenario fixture.
- [ ] Degraded-N−1 window re-measured against current tree; result reported.
- [ ] `_check_loading_exclusion` still present.
- [ ] Guards D1, D2, E Tier 1 green; TypeScript `--noEmit` clean.
- [ ] Suite reported against 12 / 965 / 3 xfailed / 977, any delta attributed.
