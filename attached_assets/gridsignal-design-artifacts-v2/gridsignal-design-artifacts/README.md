# GridSignal — Design Artifacts

**Reference material. This is not a work order.**

> **To the coding agent reading this:** these files are for the repo's record. **Do not
> restyle the console to match them** unless explicitly asked in a separate instruction.
> The work order in the accompanying prompt is **PUB-1** — two narrow fixes (mute the DQ
> legend chips at rest; add type-to-confirm to irreversible actions). Nothing else here is
> in scope for that task.

Drop this into `docs/` so design intent lives alongside the code, for the same reason
`docs/acceptance-matrix.md` does rather than sitting in a chat log.

---

## Contents

```
gridsignal-design-artifacts/
├── README.md                          ← this file
├── UI-IMPLEMENTATION-PLAN.md          ← phased build plan, with a do-not-touch register
├── MOCKUP-NOTES.md                    annotations, data provenance, responsive notes
├── GridSignal_Replit_Build_Plan_v2.2.md   now carries PA-7 and PA-8
└── mockups/
    ├── gridsignal-01-ready.svg/.png/@2x      startup state, before a run
    ├── gridsignal-02-live.svg/.png/@2x       live at T+25 s — the pitch frame
    ├── gridsignal-03-annotated.svg/.png      startup + 10 numbered callouts
    └── gridsignal-04-topology.svg/.png/@2x   where GridSignal sits in the power chain
```

SVGs are the source of truth — vector, and they carry SMIL flow animation. Open them in a
browser to see supply lines pulse in the direction of power flow. The PNGs are static frames.

---

## Why these exist

The four screens in this package are **investor-facing mock-ups**, not a spec for the
operator console. They differ in a way worth knowing:

- The **console** follows §19.11 authority discipline — muted at rest, colour reserved for
  abnormal conditions, three affordances (Propose / Acknowledge / Confirm-consequence).
- The **mock-ups** are the same visual language pitched slightly warmer, because they answer
  "what is this system?" rather than "what should I do right now?"

Where they conflict, **the console's rules win.** The mock-ups are an argument; the console
is an instrument.

---

## Two things in here that are load-bearing

**1. Every number traces to a live field.** `MOCKUP-NOTES.md` §3 maps all thirteen figures on
screen to their `TickResult` source. `example_usage.py` prints `P_total=23.954 MW` for
demo-20mw; the screen says 23.95. Nothing is placeholder art, and that is the point — a
mock-up whose numbers cannot be reproduced live is a liability in a technical demo.

**2. Four requested elements were deliberately omitted** because they do not exist in the
codebase: wind (PA-2, never built), state of health (no degradation model), a 24-hour BESS
forecast (the horizon is 30–60 s), and a thermal heatmap (one aggregate zone). Drawing them
would create exactly the gap the build spent forty defects closing. `MOCKUP-NOTES.md` §4 has
the detail.

---

## Amendments raised by this work

`GridSignal_Replit_Build_Plan_v2.2.md` now carries two additions to the amendment register:

| ID | Substance |
|---|---|
| **PA-7** | The WorkloadSignal contract spans **two** integration surfaces. §6.2 already says "scheduler/framework," but TC-05 is titled *"Explicit **scheduler** checkpoint event"* and TC-51 says *"The **scheduler** event is authoritative"* — both describing an event no scheduler emits. Slurm, Kubernetes and Ray have no visibility into a training job's checkpoints; that comes from framework instrumentation. Split the contract and correct both test titles |
| **PA-8** | *"Job scheduler"* is imprecise as the umbrella term. Exact for Slurm; Kubernetes is a container orchestrator; Ray is a distributed execution framework. Prefer "workload orchestration" or "cluster scheduler." Cosmetic against PA-7, but correct them together |

Neither is in force until v2.5 adopts them. Both are documentation corrections, not build work.

---

## Known gaps recorded elsewhere, repeated here so they are on file

- Token budget (soft 2.2 M / hard 15 M per site-day) specified in design, **never implemented**
- Token spend not tracked — the router discards `body["usage"]`, which is one line from observable
- Six agent calls run **serially on synchronous urllib inside one tick**; the dashboard freezes
  ~6 s early in every run with keys present
- Verdicts live in `RunManager._completed` (memory). After a restart both `/runs/{id}/result`
  and `/runs/{id}/timeseries` return 404 — symmetric, so the results screen shows one clean
  error rather than half-loading
- **No authentication.** `reviewer_id` is caller-supplied and unverified. This is why the
  deployment must stay **invite only**
- `favicon.svg` 404s on every page load

---

## One caveat on `gridsignal-04-topology`

The first three mock-ups were visually verified. **The topology diagram was not** — the image
viewer stopped returning content mid-session. It was checked structurally instead: 76 text
elements, zero canvas overflow, zero overlapping pairs. That check is real — it caught and
fixed three overlaps on the first pass — but it detects clipping and collision, not whether
the thing looks good. **Look at it before it goes near a deck.**
