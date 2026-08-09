# Integration Follow-up — Corrections after the Phase 0/1 report

Four changes to the shipped package, plus four items in the existing code. The
package suite is now **43 tests** (was 33). Run it before changing anything and
report the count — 33 means you have the earlier zip and are missing
`max_frequency_error_from_thresholds`, TC-141 through TC-145, and `calibrate.py`.

Integration report accepted. F-1, F-2, and F-3 are all correct, and F-1 in
particular is the finding this phase existed to produce.

---

## C-1 — `balance_defect_tolerance_mw = 0.0` must be replaced

DR-BAL-2 was closed with a tolerance of 0.0 calibrated from `demo-baseline`.
That is degenerate, and it is my module's fault for returning it rather than
refusing: 11 ticks of an idle site where the arithmetic cancels exactly is an
absence of evidence, not a measured floor. It would block the first genuinely
correct run whose MW-scale sums leave float rounding of order 1e-15.

`calibrate_noise_floor` now raises `DegenerateCalibration` on an all-zero
sample (TC-142).

**Calibrate from I2a instead.** It is structurally the same kind of sum as the
balance identity, it is exercised on all 869 recorded ticks, and it is known to
close — the harness measured a p99 magnitude of about 3.55e-15 MW, which is
float noise on that many terms and nothing else.

```bash
python3 -m core.calibrate reports/NAR-001_residuals.jsonl --invariant I2a
```

Report the suggested value. Set `balance_defect_tolerance_mw` to it and record
the basis string alongside it in the catalogue entry, so a later reader can see
where the number came from. Sanity check before you set it: the value must be
many orders below 14.34 MW and 18.05 MW, the defects it exists to catch.

If the CLI refuses, do not work around it — report what it said.

## C-2 — Re-baseline `test_D4_depleted_bess`, do not loosen it

The correct re-baseline asserts the specific gap and its terms, not a wider
bound. A tolerance large enough to pass a 0.105 MW deficit is roughly 1e11 times
the float-noise floor; TC-144 pins that.

```python
def test_D4_depleted_bess_reports_the_real_supply_gap():
    """DR-2026-08-09-BALANCE Phase 0. Islanded, BESS depleted, 10 nodes: no
    generation against ~0.105 MW of demand, so the balance defect is the gap.

    Before Phase 0 this asserted abs(defect) < 1e-3, which held only because the
    field was `_d4_sum - _balance_residual_mw` -- zero by algebra, a routing
    identity dressed as a diagnostic.

    The defect resolves to zero in Phase 4, when frequency collapse makes UFLS
    reachable and `p_unserved_mw` becomes non-zero. Until then a non-zero value
    here is the expected, correct result.
    """
    tick = run_depleted_bess_scenario()
    assert tick.p_generation_mw == pytest.approx(0.0)
    assert tick.d4_balance_defect_mw == pytest.approx(
        -(tick.p_demand_mw - tick.p_unserved_mw), rel=1e-9)
    assert tick.d4_balance_defect_mw < -0.05      # a real gap, not rounding
```

Adapt the fixture call to whatever the existing test uses. Keep the docstring —
it is the record of why the assertion changed.

## C-3 — Wire `p_unserved_mw` now, even though it is always zero

Your DR item notes it is hardcoded to 0.0 in Phase 0 because shed is computed
downstream. Pass the real field through anyway. When Phase 4 makes shed
reachable, a hardcoded zero silently double-counts: served load would not be
reduced by the shed, and the identity would report a deficit that had in fact
been resolved. Wiring it now costs nothing while the value is zero, and removes
a defect that would otherwise appear three phases later and look like a physics
problem.

## C-4 — The dual droop path is a defect, not a null-guard

F-2 describes "the fallback to the unbounded formula" when
`droop_max_frequency_error_hz` is null. That is two code paths for one behaviour,
selected by a config check, and it must not survive.

DR-BAL-1 is resolved: the clamp is **derived, not chosen**.

```python
from core.droop import max_frequency_error_from_thresholds
clamp = max_frequency_error_from_thresholds(
    site.frequency_nominal_hz,
    [<first-stage UF setting>, <first-stage OF setting>])
```

First-stage settings only. Second-stage fast trips are not the boundary of
governor action. The function raises rather than defaulting when none are
supplied.

So: locate the site's protective settings, report where they live and what
values they hold, derive the clamp, and **delete the unbounded fallback branch
entirely**. If no first-stage settings exist anywhere in the codebase, stop and
report — do not substitute a figure from IEEE 1547 or any other standard, and do
not keep the fallback as a workaround.

Expected suite delta remains zero while frequency is frozen.

---

## One verification I want rather than an argument

Among the 13 pre-existing failures are "droop restoring-force tests". Their
coinciding with a droop change is probably nothing, and your bit-for-bit
reasoning is the right reasoning — but please confirm it by measurement rather
than by inference:

```bash
git stash && python3 -m pytest <those tests> -q > /tmp/before.txt
git stash pop && python3 -m pytest <those tests> -q > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt
```

Report the diff. Empty is the expected answer.

---

## Recurring pattern worth a standing check

F-1 makes three. `p_expected_mw` assigned from `p_renewable_mw`; `p_served_mw`
defined as demand minus commanded shed; `d4_balance_defect_mw` computed as
`_d4_sum - _balance_residual_mw`. Three fields whose definitions make the
condition they exist to detect structurally unreachable.

Three is not coincidence. Worth adding to review: **for any field intended as a
diagnostic, can this quantity ever be non-zero given how it is computed?** If the
answer needs thinking about, it is probably an identity.

---

## Do not

1. Do not widen any tolerance to make a test pass. C-2 exists because that is the
   tempting wrong fix.
2. Do not keep the unbounded droop branch as a null-guard.
3. Do not choose a value for the clamp or the tolerance. Both are derived.
4. Do not wire `swing.py`. Phase 2 needs a sub-tick loop scoped as its own task.
5. Do not modify `p_served_mw` or the §23 curtailment path.
6. Do not edit a shipped test to make it pass.

## Stop and report if

- The package suite does not report 43 passed before you change anything.
- `python3 -m core.calibrate` refuses on I2a as well.
- No first-stage protective settings exist in the codebase.
- The droop restoring-force diff is non-empty.
- Wiring `p_unserved_mw` changes any existing test.
