# Replit Agent Prompt — NAR-001 Phase 1 Authorization and Amendments

Paste everything below the line.

---

## PHASE 0 RESPONSE

Both stop conditions reviewed. **Proceed to Phase 1** with the amendments below.

**On the nine physics modules — my trigger was miscalibrated, and your report is the correct answer.** The condition was written to detect *duplicate* implementations of the same physics, not decomposition into modules with distinct responsibilities under a single orchestrator. Nine modules called by `evaluate_tick()` with non-overlapping scope is decomposition. No action.

**On sections F and H exceeding the NOT_FOUND threshold — proceed and record the absences.** That trigger existed to surface exactly this before an implementation prompt was written, and it did its job. `NOT_FOUND` is the deliverable for those sections, not a blocker.

---

## PRE-CHECK — answer in chat before starting Phase 1

**Q1. Is there a second physics path anywhere outside `core/`?**

Search the entire repository, not just `core/`. Specifically: does `gridsignal_logger.py` still exist, in any directory, in any state including unused or dead code? Report every file outside the nine modules you listed that contains a swing equation, a power-balance computation, a ramp calculation, or an asset power model.

Answer this one question in chat and stop. If any second path exists, do not start Phase 1 — the inventory needs a per-signal path-attribution column and I will amend the prompt. If none exists, proceed straight to Phase 1 without waiting for me.

---

## AMENDMENTS TO THE PHASE 1 PROMPT

### A1. Detect at the source, not at the wire

`TickResult` is the substrate, not `_tick_result_to_dict()`. Several signals you flagged are present internally but absent from the wire, and that distinction is now the most important thing the inventory records.

Replace the `backend` / `transport` split in the YAML block with:

```yaml
  on_tick_result: true                   # is it a field on the TickResult dataclass?
  tick_result_field: it_draw_mw
  defined_at: "core/models.py:891"
  assigned_at: "core/simulation_core.py:412"      # where the value is computed
  excerpt: "self.it_draw_mw = compute_mw + 0.0"    # verbatim, single line
  on_wire: true                          # emitted by _tick_result_to_dict()?
  wire_field: itDrawMw
  wire_at: "runtime/run_manager.py:NNN"
  frontend_field: itDraw
  rendered_at: "frontend/src/subsystem/panels/compute.ts:NN"
  frontend_literal: false
  units_declared: false
  units_declared_where: null
  units_assumed_by_you: MW
  duplicates: []
  notes: ""
```

A signal that is `on_tick_result: true, on_wire: false` is a different and much cheaper problem than one that does not exist. Record the difference.

### A2. Required new section — fields on `TickResult` but not on the wire

Add to the output file:

```
## 9. TickResult fields not emitted by _tick_result_to_dict()
```

Full list, with field name and type. This tells me what the change monitor can see for free.

### A3. Required new section — catalogue keys that already express a tolerance

You reported deadband-like semantics under other names (`levelled_off_epsilon_mw`, `commit_confirm_s`). I do not want a parallel set of keys with overlapping meaning — that is the dual-implementation defect in configuration form.

```
## 10. Existing tolerance / hysteresis / confirmation-window keys
```

For every key in `gridsignal_parameters.json` whose meaning is an epsilon, tolerance, deadband, hysteresis band, confirmation window, hold time, debounce, or staleness threshold: exact key name, section (`locked` / `adjustable` / `enumerated`), current value, units-declared status, and every code site that reads it. Do not judge whether it should be reused. List it.

### A4. Test case numbering

Ignore the TC numbers in the design document — they collide with TC-61…TC-98 and are void. Do not assign any TC numbers in this inventory. I will allocate from TC-110 onward once the inventory is complete.

### A5. Targeted questions — answer in section 11 of the output file

```
## 11. Targeted questions
```

Answer each with file:line and a verbatim excerpt. Where the answer is "does not exist", say so plainly.

**Q2 — Turbine display states.** `TurbineState` has `OFFLINE`, `OUT_OF_SERVICE`, `STARTING`, `UNLOADING`, `SYNCHRONISED`. The UI displays `available`, `syncing`, and `open`. None of those three are enum members. Where does that mapping happen? Is it a mapping function, a switch in TSX, or a set of string literals? Give the site and the full mapping.

**Q3 — `floor_violated`.** It does not appear on `TickResult`, but it has been observed in operator-facing output alongside a `HOLD` decision. Search every module. Where is it set, what reads it, and does it reach the wire by any route? If it exists only inside `core/commitment.py`, say so and give the symbol.

**Q4 — Solar elevation.** Does `renewable/solar.py` compute a solar elevation, altitude, or zenith angle internally, even though it is not exported? Give the symbol and file:line if so.

**Q5 — `p_expected_mw`.** Give the assignment expression verbatim and name every input to it, each with file:line. Do not summarise the calculation in prose — I want the line.

**Q6 — Time source for solar.** What time value does `renewable/solar.py` use to determine sun position? Give the variable and where it originates. Does it consume `site_utc_offset_h`, a UTC timestamp, a local timestamp, or something else?

**Q7 — `site_utc_offset_h`.** Where is it set, from what, and which modules read it?

**Q8 — `kube_metrics.active_jobs`.** What exactly does it count? Give the code that derives or increments it. What is the relationship, if any, between it and the number of jobs contributing to IT draw?

**Q9 — Workload staleness tags.** What threshold sets `WORKLOAD_SIGNAL_STALE` and `WORKLOAD_SIGNAL_ABSENT`? Where is that threshold defined, and is it a catalogue key or a literal? Is any elapsed-time-since-last-event value computed anywhere, even if not exported?

**Q10 — `contingency_coverage`.** Full field list of the object, with types. Include `shed_required_mw` and every sibling.

**Q11 — Tick rate.** `tick_rate_s` is absent from the catalogue. Where is the tick interval actually set? Give the literal and file:line. Is it a single value or set per run?

**Q12 — Reserve fields.** You report `reserve_satisfied: bool`, `reserve_floor_mw`, and `committed_rated_mw`, with no `reserve_margin_mw`. Give the expression that computes `reserve_satisfied`, verbatim. Does it evaluate a point estimate or a confidence band? Name the exact field it compares.

**Q13 — Verdict string construction.** In `useSubsystemData.ts`, give the code that builds the Compute & Workload verdict, verbatim. Specifically: what determines the thermal clause, and does it read any thermal field at all?

**Q14 — `recommendation` table.** What writes to it? Is there a lifecycle or state machine, and where is it defined?

---

## UNCHANGED

Everything in the original prompt still applies: read-only, one output file, `file:line` plus verbatim excerpt mandatory for every `FOUND`, `NOT_FOUND` and `AMBIGUOUS` are correct answers, do not reconcile duplicates, do not create catalogue keys, do not infer units or behaviour from identifier names, do not edit any spec or decision record, do not run the simulator.

One addition to the do-not list:

- **Do not fix, rename, or export any field you find missing.** Several questions above will point at things that are absent or wrong. Report them. Changing them is a separate, later, gated task.
