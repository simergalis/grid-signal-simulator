# Verify the integration path, restore MSL, catalogue the open parameters

**Follows:** Conformance gaps closed. Ramp gap, UNLOADING colour, Gaps 7 and 9 all landed.
**Baseline:** 15 failed / 976 passed / 16 xfailed backend; 29 frontend; `tsc --noEmit` clean.
**Scope:** Items 1–2 are corrections. Item 3 is the parameter sweep, and it is the largest piece.

The visual work is done and the ramp gap is finally legible. Two things from that session need closing, and one finding in it is larger than the report treated it as.

---

## Item 1 — The integration verification, actually run (blocking)

The acceptance criterion asked for `commitment_block` values read off the emitted payload on a workload-carrying tick. The report delivered:

> **VIOLATED case (inferred from payload chain)** … The payload key `reserve_floor_mw` at wire time **will be** 49.5

That is a code reading, and it was checked off as complete. It is not the same thing.

**Why the one case that ran does not discriminate.** The satisfied case executed at **zero demand**, where `floor_mw = 0 + largest` and `utilisation = 0`. Those are also the values the *old broken code* produces under a degenerate input — `decommit_utilisation × committed` is not what was checked, but at zero demand nothing distinguishes the two implementations. The one executed case cannot tell a fixed consumer from an unfixed one, and the consumer was the defect.

**The stated obstacle is avoidable.** Reaching 34.5 MW through the GPU ramp needs ~300 ticks; constructing the state does not. Build a `SimulationState` with turbines already SYNCHRONISED and a demand that yields a violated floor, call `evaluate_tick` once, and read the emitted dict. No ramp-up.

Report, from the **payload dict**, for one satisfied and one violated tick with non-zero demand:

`committed_rated_mw`, `reserve_floor_mw`, `reserve_satisfied`, `utilisation`, `action`, `pending_start_unit_id`.

Confirm `utilisation` is non-zero in both. A zero there means the state was not loaded and the test does not discriminate.

## Item 2 — Restore the MSL figure in megawatts

The `NO-LOAD / MSL MW` column was dropped, on the grounds that the dashed rule in the bar carries the same datum.

It does not. The dashed rule shows MSL as a **fraction of rated** — a position. The column showed it in **MW** — a number. An operator asking *how low can this unit go* needs the megawatts, and reading it off a bar position is not an answer.

It also just became worth showing. MSL read `0.00` on every scenario until Phase E; it is now non-zero across all 23 and gates the entire unload sequence. This is the first release in which that column has anything to say.

Two acceptable fixes:

- Put the MSL figure in the bar's sub-annotation, which already carries text (`"tracking → 13.50 · +2.30 MW to go"`). It would read `"at minimum stable load · 6.00 MW"`.
- Restore the column and drop `RAMP meas/cfg` instead, which duplicates a value the bar's slope already implies.

Take either; state which and why. **Do not leave the megawatt figure absent.**

---

## Item 3 — Catalogue the open parameters

The sweep found 22 uncatalogued numeric defaults and reported them for awareness. Four of them are load-bearing, and Guard D is structurally blind to all 22 — it enforces agreement between code and catalogue and is silent about absence, which is the same gap `_COOLING_MARGIN` and `unload_tail_s` sat in.

These are the parameters the product's claims rest on.

### Priority 1 — catalogue these first, with honest provenance

| Field | Why it matters |
|---|---|
| `TurbineConfig.r_asset_mw_per_s` | The ramp rate. The single most consequential constant in §7.1.3, and the entire argument of the Generation panel. Reported OPEN, no measured basis. |
| `SiteConfig.inertia_constant_s` | H — the frequency-response timescale. Claim discipline says absolute frequency figures must not be quoted until H is measured; that constraint is unenforceable while H is an uncatalogued literal. |
| `SiteConfig.governor_droop` | Governs frequency response alongside H. Reported OPEN. |
| `TurbineConfig.cold_start_s` / `warm_start_s` / `hot_start_s` | Determine commitment timing after Phase D. CHOSEN, no OEM basis. `hot_start_s` was already corrected 60 → 300 once during this work. |

### Priority 2 — catalogue if straightforward

`hot_threshold_s`, `warm_threshold_s`, `levelled_off_tol_mw`, `bess_response_tau_s`, `workload_signal_stale_s`.

### Do not catalogue

Booleans (`hot_standby`, `min_run_enabled`, `min_down_enabled`, `grid_forming`, `band_enabled`, `uncalibrated`) — not physical constants.

Per-unit nameplates (`TurbineConfig.rated_mw`, `BessConfig.rated_mw`, `usable_mwh`, `initial_soc_fraction`) — these are scenario configuration, not site parameters, and a fleet-wide catalogue entry would be wrong. **Report why for each**, so the exclusion is a decision on the record rather than an omission.

`load_model_bias_mw` — test injection only. Confirm that is true; if any production path reads it, that is a finding.

### Provenance must be honest

Most of these are `CHOSEN` with no measured basis, and the entries must say so. A `CHOSEN` entry that reads as `SPEC_DEFAULT` is worse than no entry, because it launders a guess into an authority. Where a figure has an origin — a spec section, a vendor sheet, a PROTO tag — cite it. Where it does not, say `CHOSEN` and put the absence in the `reason` field.

This matters ahead of the operator feedback sessions. A generation engineer will ask where `r_asset` comes from, and the answer needs to be a catalogue entry stating it is unvalidated, not a literal nobody can find.

### After cataloguing

Every catalogued field reads through `site_parameters`, and Guard D3 then covers the call sites. Report the Guard D2 backlog and the D3 call-site count before and after.

**Do not enforce any new cross-parameter invariant** beyond the `unload_tail_s > levelled_off_window_s` check already added. If the sweep suggests others — H against droop, thresholds against start times — report them as candidates.

---

## Prohibited

- Inferring a payload value from code rather than reading it from an emitted dict.
- Marking Item 1 complete on a zero-demand tick.
- Leaving the MSL megawatt figure absent from the panel.
- Cataloguing a boolean or a per-unit nameplate.
- Writing `SPEC_DEFAULT` or any authoritative provenance on a value with no measured basis.
- Enforcing a new cross-parameter invariant. Report candidates.
- Editing any test assertion.
- Adding a module-scope numeric constant to `panels/`.
- Modifying `gridsignal_logger.py`.
- Proceeding past the Item 1–2 gate without reporting.

## Acceptance criteria

- [ ] Satisfied and violated `commitment_block` values read from the emitted payload dict, both with non-zero `utilisation`.
- [ ] MSL restored in megawatts; approach stated.
- [ ] Priority 1 fields catalogued with honest provenance and `spec_ref`; each reads through `site_parameters`.
- [ ] Priority 2 fields catalogued or deferred with a reason.
- [ ] Every excluded field reported with why it is excluded.
- [ ] `load_model_bias_mw` confirmed test-only, or the production reader reported.
- [ ] Guard D2 backlog and D3 call-site count reported before and after.
- [ ] Cross-parameter invariant candidates reported, none enforced.
- [ ] Guards D1, D2, D3, E green; `tsc --noEmit` clean.
- [ ] Suite reported against 15 / 976 / 16 xfailed and 29 frontend, every delta attributed.
