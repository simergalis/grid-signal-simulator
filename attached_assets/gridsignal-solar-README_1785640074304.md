# GridSignal — Renewable Supply Console

A tick-driven operator console for a non-dispatchable PV plant, and the reserve
arithmetic that decides whether losing it would matter.

Single process. No external services. Python + FastAPI serving a static console.

---

## Import into Replit

**Option A — upload the zip**

1. Create a new Repl, template **Python**.
2. In the Files pane, use the three-dot menu → **Upload folder** (or upload the zip
   and unzip in the shell: `unzip gridsignal-solar.zip && mv gridsignal-solar/* . && rmdir gridsignal-solar`).
3. Make sure `.replit` and `replit.nix` landed at the repo root — Replit hides
   dotfiles by default; toggle **Show hidden files** in the Files pane to confirm.
4. Press **Run**.

**Option B — from a Git repo**

1. `git init && git add -A && git commit -m "renewable supply console"` locally, push to GitHub.
2. In Replit: **Create Repl → Import from GitHub**.
3. Press **Run**.

Replit installs from `requirements.txt` on first run. The console is served at the
webview root; the API is under `/api`.

**Verify the import worked.** The pill in the header should read
`SERVER · wenatchee-02` in teal. If it reads `LOCAL SIM` in grey, the page loaded
but could not reach `/api/solar/state` — the console fell back to its in-browser
model, which is a legitimate mode but means the server is not wired up.

---

## Run and test locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000    # http://localhost:8000
pytest                                    # 37 tests
```

`static/index.html` also runs standalone — open it directly from disk with no
server at all. It detects the missing API and runs its own physics.

---

## Layout

```
main.py              FastAPI app, 1 Hz background tick, static mount
app/config.py        SiteConfig — array sizing, fleet constants, seed atmosphere
app/solar.py         reference implementation: physics + §7.2 step 4 reserve check
static/index.html    the console — modal + four screens, self-contained, no build step
tests/test_solar.py  pytest: seed operating point, anchor constraint, reserve semantics
.replit / replit.nix Replit run + Nix environment
```

### Where the numbers come from

`app/solar.py` is authoritative. The console carries a mirror of the same formulas
so the file works offline, but **whenever the server is reachable it consumes the
scalars the server computed** rather than recomputing them — `blockOutput`,
`bessBridging`, and `pCooling` all short-circuit to the snapshot. There is one
authority at runtime.

The duplication is still a real risk on the calibration path. If you change a
coefficient in `config.py`, change the matching value in the `CFG` object at the
top of `static/index.html`, and `pytest` will catch the seed drift either way.
Collapsing the mirror entirely (server pushes every derived scalar, client renders
only) is the obvious next refactor and is listed below.

---

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | the console |
| `GET` | `/healthz` | liveness, current tick, site id |
| `GET` | `/api/solar/state` | full snapshot: atmosphere, power, fleet, blocks, exposure, reserve, log |
| `GET` | `/api/solar/config` | site constants only |
| `POST` | `/api/solar/inject/{kind}` | stressor injection |

Stressors: `cloud`, `cloud_clear`, `trip`, `poi`, `soil`, `spike`, `turbine`,
`bess`, `reset`.

```bash
curl -s localhost:8000/api/solar/state | jq '.power'
curl -X POST localhost:8000/api/solar/inject/poi
```

---

## The model, briefly

**Plant.** 5 × 1.00 MW AC inverter blocks, 6.50 MWp DC (1.30 DC/AC), fixed mount,
24 strings per block. Seed point: 4.29 MW output, 93.5% performance ratio,
35.6% of site draw.

**Net dispatch requirement** (§7.1.1) — `P_dispatch_required = P_total − P_renewable`.
Solar is subtracted from the load the fleet must serve and is never added to ramp
capability. `test_solar_never_contributes_to_ramp_capability` asserts this directly.

**Three distinct loss modes**, which the console refuses to sum into one number:

| Mode | Shape | Δt_lead | Sizes the reserve? |
|---|---|---|---|
| N−1 inverter block trip | step | 0 s | yes — the probable case |
| Plant loss at the POI | step | 0 s | yes — the sizing case |
| Cloud transient | ramp, bounded 0.42 MW/s by array diversity | ~90 s, low confidence | no |

**Anchor constraint** (§7.1.2) — the site is islanded, so 2.0 MW is withheld from
the BESS for grid-forming duty before anything else. Usable bridging therefore
falls faster than state of charge does; the tests pin that relationship.

**Reserve check** (§7.2 step 4) — the shortfall declines linearly as turbines ramp
rather than sitting flat, and sustainable discharge is compared as a *duration*
against the gap window, never as an energy-like product.

**Two alert tiers.** A hard alert fires when the contingency the site is exposed
to right now cannot be covered. The compound case — a plant loss coincident with a
6 MW compute step — is a planning figure and renders as an amber advisory. At the
seed point the site passes the first and fails the second, which is the intended
demo state.

---

## Known open items

- **SI-1 — Array sizing is invented.** The values in `config.py` close the §7.1.1
  residual for simulator purposes only. Nothing here is measured design-partner data.
- **SI-2 — The client mirrors the server's formulas.** One authority at runtime,
  two implementations in the repo. Collapse to server-computed scalars only.
- **SI-3 — History and MAPE figures are static.** The 30-day chart is seeded from a
  deterministic PRNG and the accuracy table is hardcoded. Both need a persistence
  layer (Phase 1 of the Replit build plan) before they mean anything.
- **SI-4 — No persistence.** Simulation state is in-process and dies with the Repl.
  One instance, one client's actions visible to every other viewer.
- **SI-5 — Comms loss is not distinguished from generation loss.** The June 14 row
  in the loss-event table is a real gap: a plant-controller comms failure presents
  identically to an array failure and is currently handled as one.
- **SI-6 — The cloud ramp bound is a constant, not a model.** 0.42 MW/s is a
  plausible plant-wide figure for five blocks at this spacing; it should be derived
  from array geometry and observed transients.

---

## What this is not

Not the real-time control loop. The tick loop here is wall-clock convenience for a
demo instrument, and nothing in this process belongs on the edge appliance path
described in §18.7. There is also no control surface on any solar screen, by
construction — solar is a passive collector, and a control that does nothing is
worse than no control at all.
