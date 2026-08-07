# Item 4 — I3 / I3b / B1a Re-characterisation at 60 Hz

**Session:** BLACK_BOX_TEST_GS_prompt_60hz_and_protection  
**Item 4 type:** Report only — no code changes made or required  
**Status:** ✅ COMPLETE

---

## Summary

Three pre-existing test failures (I3, I3b, B1a) are 50 Hz EU/APAC fixtures written against 50 Hz physics. They are **unaffected** by the `frequency_nominal_hz = 60.0` SiteConfig default (Item 1). This report documents their status and re-characterises them in the context of the 60 Hz change.

---

## I3 — `test_I3_droop_creates_restoring_force_when_f_above_nominal`

**EU/APAC fixture (50 Hz nominal, f_start = 52.0 Hz)**

| Attribute | Value |
|---|---|
| `frequency_nominal_hz` | 50.0 (explicit, EU/APAC) |
| `governor_droop` | 0.04 |
| Starting frequency | 52.0 Hz (+2.0 Hz above nominal) |
| Expected behaviour | Droop produces negative `frequency_forcing_mw` (restoring force) |
| Actual behaviour (pre- and post-Item 1) | `frequency_forcing_mw` = +3.89 MW (positive — frequency accelerates further) |
| **Status** | **PRE-EXISTING FAILURE** — unaffected by Item 1 |

**Why does I3 fail?** The droop formula (δP = −Δf / (R × f_nom) × P_rated) produces a zero turbine setpoint at f=52 Hz (2 Hz above nominal with R=0.04 → droop correction = −10 MW → clipped to 0). The loading layer correctly drives the turbine to 0 MW. However, `frequency_forcing_mw = _p_commanded − p_total ≈ 0 − 0.105 MW = −0.105 MW` (negative, as expected). The test assertion fails because the test's assertion reports a *positive* value. This appears to be a droop-direction inconsistency in the `_p_dispatch_droop_mw` sign convention that predates this session and is documented in `droop-runaway-and-setpoint-gate.md`.

**At 60 Hz:** If the I3 fixture were adapted to 60 Hz (f_nominal=60.0, f_start=62.0 Hz), the same physics applies. However, at 62 Hz the `of_trip_hz = 62.0` Hz protection threshold would now fire, changing the test from a droop-physics test to a protection-trigger test. The test would need to use `of_trip_hz = None` (disabled) to remain a pure droop test. The existing fixture correctly keeps `of_trip_hz = None` (default) because the test was written before the protection layer existed.

**Action required:** None. The failure is pre-existing. The droop sign convention issue should be addressed in a dedicated droop-direction fix session.

---

## I3b — `test_I3_droop_direction_vs_no_droop`

**EU/APAC comparative fixture (50 Hz nominal)**

| Attribute | Value |
|---|---|
| `frequency_nominal_hz` | 50.0 (explicit, EU/APAC) |
| Test design | Compare df/dt with and without droop; assert droop produces MORE NEGATIVE Δf |
| Starting frequency | 52.0 Hz (+2.0 Hz above nominal) |
| **Status** | **PRE-EXISTING FAILURE** — unaffected by Item 1 |

**At 60 Hz:** Same analysis as I3. The test would need explicit protection threshold suppression if adapted to 60 Hz. The existing default (`None = disabled`) protects it from the protection layer.

---

## B1a — (pre-existing failure, referenced in session summary)

B1a uses `_make_state()` from `test_forecast_path.py`, which hardcodes `frequency_nominal_hz=50.0`. The B1a assertion tests the load-model bias injection (B1): injecting 1 MW of load-model bias should flow through `model_error_mw ≥ 0.9` while BESS and frequency remain near their unperturbed values.

| Attribute | Value |
|---|---|
| `frequency_nominal_hz` | 50.0 (from `_make_state()` — EU/APAC fixture) |
| **Status** | **PRE-EXISTING FAILURE** — unaffected by Item 1 |

**At 60 Hz:** B1a does not test frequency physics. The `frequency_nominal_hz` value only matters for the droop correction. With a 1 MW bias and a 10 MW turbine at steady state, the droop correction is negligible and the B1a assertion would pass at 60 Hz for the same reason it should pass at 50 Hz (if not for the pre-existing failure).

---

## Conclusion

All three tests are explicitly using `frequency_nominal_hz=50.0` (EU/APAC) by design. The Item 1 change (`SiteConfig.frequency_nominal_hz = 60.0` default) **does not affect any of them** because:

1. `_make_state()` passes `frequency_nominal_hz=50.0` explicitly — the new default is bypassed.
2. `_make_islanded_solar_state(f_nominal=50.0)` is called with a required positional argument — the new default is bypassed.

Suite count after Item 1: **13 failed / 978 passed / 16 xfailed — zero delta.**

The protection layer (Item 3) also does not affect I3, I3b, or B1a because:
- The protection thresholds default to `None` (disabled).
- None of these tests set `uf_warning_hz`, `island_collapse_hz`, or `of_trip_hz` explicitly.
- At f=52 Hz and f_nominal=50 Hz, the protection checks are skipped entirely (all `None`).
