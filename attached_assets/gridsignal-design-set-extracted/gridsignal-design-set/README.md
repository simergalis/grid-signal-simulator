# GridSignal Console — Design Set

**13 current views. `REPLIT-UI-HIERARCHY.md` is the work order.**

| # | View | Level | Purpose |
|---|---|---|---|
| **01** | `gs-01-opening-rest` | 0 | **Opening screen at rest** — verdict + one-line mimic + system strip |
| **02** | `gs-02-opening-live` | 0 | Same screen during a run — countdown, live flows |
| 03 | `gs-03-run-overview` | 2 | The 2×2 run view — hero, forecast chart, reserve, alert dock |
| 04 | `gs-04-topology-explainer` | 1a | "How it works" — where GridSignal sits. Onboarding, not operations |
| 05 | `gs-05-generation` | 1 | Turbine detail — ramp capability vs required |
| 06 | `gs-06-storage` | 1 | BESS detail — power ceiling, anchor reserve, bridge duration |
| 07 | `gs-07-renewable` | 1 | Solar detail — the exposure if it vanishes |
| 08 | `gs-08-thermal` | 1 | Cooling detail — the 90 s lag |
| 09 | `gs-09-compute` | 1 | Workload detail — per-job attribution |
| 10 | `gs-10-grid` | 1 | Grid detail — firmness classes |
| 11 | `gs-11-forecast-quality` | 1 | **Trust panel** — bands, tags, calibration state |
| 12 | `gs-12-network` | 1 | Fabric detail — read-only by contract |
| 13 | `gs-13-agents` | 1 | Optimisation agents — LP-1 |

SVG is the source of truth: vector, and it carries SMIL flow animation. Open in a browser to see
supply lines pulse. PNG at 1× and 2× for decks.

## Hierarchy

```
LEVEL 0   opening screen        01 · 02
LEVEL 1   detail modals         05 – 13     (from any Level 0 element)
LEVEL 1a  topology explainer    04          (from the ⓘ header control)
LEVEL 2   full pages            03 + existing routes
```

## Superseded — `deprecated/`

| File | Replaced by |
|---|---|
| `gridsignal-01-ready` | `gs-01-opening-rest` |
| `gridsignal-03-annotated` | annotations moved to `MOCKUP-NOTES.md` |
| `gridsignal-05-readiness` | `gs-01` — the tile grid is retained in code as the sub-768 px fallback |
| `gridsignal-06-modal` | duplicate of `gs-06-storage` |

Kept for reference. The tile-grid layout is **not** dead — it is the mobile breakpoint.

## Grounding

Every number traces to a live `TickResult` field. `example_usage.py` prints
`P_total=23.954 MW` for demo-20mw; the screens say 23.95. Where a value does not exist, the panel
says so — `not enforced`, `not instrumented`, `not configured` — never a plausible placeholder.

Four requested elements are deliberately absent because no model backs them: **state of health**,
**24-hour BESS forecast**, **wind**, **thermal heatmap**. See `MOCKUP-NOTES.md` §4.

## Verification caveat

The image viewer stopped returning content partway through this design session. Views 04–13 and
01–02 were checked **structurally only** — text overflow and collision, with the checker catching
and fixing five real issues including a duplicated subtitle on 04. That check does not tell you
whether the result looks good. **Review before use.**
