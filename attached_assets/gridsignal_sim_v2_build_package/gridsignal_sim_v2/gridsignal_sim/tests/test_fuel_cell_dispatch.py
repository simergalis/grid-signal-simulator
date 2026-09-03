"""
tests/test_fuel_cell_dispatch.py — Black-box fuel cell dispatch test.

Verifies that the Fuel Cell Module Array delivers power whenever the droop-
adjusted dispatch target exceeds the joint output of turbines + BESS.

Background
----------
Dispatch rule:

    The scenario factory creates one aggregate FuelCellModule.  Each tick
    advances it at its fuel-cell-specific ramp rate and the wire field reports
    its measured output; the orchestration layer no longer computes a residual
    fuel-cell setpoint.

In scenario-kube-peak-overage only turbine-0 (25 MW) starts on bus.  BESS is
18 MW.  Before turbine-1 synchronises (~sim_t 1660 s) the joint ceiling is
43 MW.  Kube load peaks ~48 MW during phase-1, leaving a ~5 MW residual the
FC must cover.

The test observes raw tick wire fields:
  - p_compute_demand_mw  — total compute power demand this tick
  - turbine_output_mw    — actual turbine fleet output (arbitrator result)
  - bess_output_mw       — actual BESS fleet output (arbitrator result)
  - fuel_cell_output_mw  — FC output commanded this tick

Checks
------
  A. At every tick where  demand − turbine − BESS > RESIDUAL_THRESHOLD_MW,
     fuel_cell_output_mw must be > 0.
  B. At least REQUIRED_DISPATCH_EVENTS ticks with a non-zero FC output are
     observed within the run window (confirms the FC is genuinely exercised,
     not just passing on a quiet run).
  C. The peak FC output observed is ≤ the effective fleet rated MW (20 MW —
     4 stacks × 5 MW/stack).

Protocol
--------
  1. Mint a JWT from SESSION_SECRET.
  2. POST /runs with playback_speed=0 (max-speed run).
  3. Poll GET /runs/{run_id}/latest-tick at POLL_S intervals.
  4. Collect ticks until sim_time > RUN_WINDOW_S or ≥ REQUIRED_DISPATCH_EVENTS
     FC ticks are seen.
  5. Evaluate checks A, B, C.
  6. DELETE /runs/{run_id} to clean up.

Run
---
  cd gridsignal_sim
  SESSION_SECRET=<secret> python tests/test_fuel_cell_dispatch.py
  # or via pytest:
  SESSION_SECRET=<secret> python -m pytest tests/test_fuel_cell_dispatch.py -s -v
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from jose import jwt

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL    = "http://localhost:22126"
# Dedicated minimal scenario: turbine 5 MW + BESS 1 MW (joint ceiling 6 MW),
# 20 MW FC fleet.  Kube demand exceeds 6 MW by ~sim_t=70 s, forcing FC dispatch.
SCENARIO_ID = "test-fc-dispatch"
POLL_S      = 0.3       # seconds between polls — sim runs at max speed
TOTAL_TIMEOUT = 120.0   # real-clock budget; a max-speed 600 s run finishes < 30 s

# Collect ticks through the full scenario duration.
RUN_WINDOW_S = 600.0

# Residual threshold: demand − turbine − BESS must exceed this before we
# require FC > 0.  1 MW of slack absorbs droop corrections and rounding
# without letting a 0.2 MW rounding artefact falsely trigger the check.
RESIDUAL_THRESHOLD_MW = 1.0

# FC spec for test-fc-dispatch: 1 stack × 20.0 MW/stack = 20.0 MW fleet.
# (scenario_factory.py treats fuel_cell_rated_mw as per-stack rating.)
FC_STACK_RATED_MW  = 20.0
FC_STACK_COUNT     = 1
FC_FLEET_RATED_MW  = FC_STACK_RATED_MW * FC_STACK_COUNT   # 20.0 MW

# We require this many ticks with FC > 0 before declaring the check passed.
# With a 5 MW turbine and kube demand growing past 6 MW by ~t=70 s, FC should
# fire on several consecutive ticks through the rest of the run.
REQUIRED_DISPATCH_EVENTS = 3


# ── JWT helpers ───────────────────────────────────────────────────────────────
def _mint_token() -> str:
    secret = os.environ.get("SESSION_SECRET") or os.environ.get("JWT_SECRET", "")
    if not secret:
        raise RuntimeError(
            "Set SESSION_SECRET in the environment to match the running server."
        )
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {"sub": "1", "email": "test@gridsignal.test", "exp": expire}
    return jwt.encode(payload, secret, algorithm="HS256")


def _session(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        cookies={"gs_session": token},
        timeout=15.0,
    )


# ── Main test body ────────────────────────────────────────────────────────────
def _run_test() -> None:
    token  = _mint_token()
    sess   = _session(token)
    run_id: Optional[str] = None

    try:
        # ── Start run ─────────────────────────────────────────────────────────
        resp = sess.post("/runs", json={
            "scenario_id":    SCENARIO_ID,
            "playback_speed": 0.0,   # max speed
        })
        assert resp.status_code in (200, 201), (
            f"POST /runs failed: {resp.status_code} — {resp.text[:400]}"
        )
        run_id = resp.json().get("run_id")
        assert run_id, f"No run_id in response: {resp.json()}"
        print(f"[START]  run_id={run_id}  window={RUN_WINDOW_S:.0f} sim-s")

        # ── Wait for first tick ───────────────────────────────────────────────
        deadline = time.monotonic() + TOTAL_TIMEOUT
        tick: Optional[dict] = None
        while time.monotonic() < deadline:
            r = sess.get(f"/runs/{run_id}/latest-tick")
            if r.status_code == 200:
                tick = r.json()
                if tick:
                    break
            time.sleep(POLL_S)
        assert tick, "Never received a tick before timeout."

        # ── Collect ticks ─────────────────────────────────────────────────────
        # Each entry: (sim_t, demand, turb, bess, fc)
        seen_sim_t  = -1.0
        violations: list[tuple[float, float, float, float, float]] = []
        fc_events:  list[tuple[float, float]] = []   # (sim_t, fc_mw)
        max_fc_mw   = 0.0
        all_ticks:  list[tuple[float, float, float, float, float]] = []

        print("[POLL]   collecting ticks …")
        print(
            f"{'sim_t':>9}  {'demand':>8}  {'turb':>8}  {'bess':>8}  "
            f"{'residual':>10}  {'fc_out':>8}  status"
        )
        print("-" * 72)

        while time.monotonic() < deadline:
            r = sess.get(f"/runs/{run_id}/latest-tick")
            if r.status_code != 200:
                time.sleep(POLL_S)
                continue
            tick = r.json()
            if not tick:
                time.sleep(POLL_S)
                continue

            sim_t    = float(tick.get("sim_time_seconds", 0.0))
            demand   = float(tick.get("p_compute_demand_mw", 0.0))
            turb     = float(tick.get("turbine_output_mw", 0.0))
            bess     = float(tick.get("bess_output_mw", 0.0))
            fc       = float(tick.get("fuel_cell_output_mw", 0.0))

            if sim_t == seen_sim_t:
                time.sleep(POLL_S)
                continue
            seen_sim_t = sim_t

            residual = demand - turb - bess
            all_ticks.append((sim_t, demand, turb, bess, fc))

            # ── CHECK A inline: residual > threshold → FC must fire ────────
            flag = ""
            if residual > RESIDUAL_THRESHOLD_MW:
                if fc < 1e-9:
                    flag = "  ← FAIL-A: FC silent despite residual"
                    violations.append((sim_t, demand, turb, bess, fc))
                else:
                    flag = "  ← FC dispatching ✓"

            if fc > 1e-9:
                fc_events.append((sim_t, fc))
                max_fc_mw = max(max_fc_mw, fc)

            print(
                f"{sim_t:9.1f}  {demand:8.2f}  {turb:8.2f}  {bess:8.2f}  "
                f"{residual:10.2f}  {fc:8.2f}{flag}"
            )

            # Stop once past the run window
            if sim_t >= RUN_WINDOW_S:
                print(f"\n[INFO]   reached sim_t={sim_t:.1f} s — stopping collection.")
                break

            # Also stop if run ended
            status = tick.get("status") or tick.get("run_status", "")
            if status in ("completed", "cancelled", "failed"):
                print(f"[INFO]   run finished with status={status!r}")
                break

            time.sleep(POLL_S)

        # ── Post-collection analysis ──────────────────────────────────────────
        print("\n" + "=" * 72)

        saturated_ticks = [
            (sim_t, demand, turb, bess, fc)
            for (sim_t, demand, turb, bess, fc) in all_ticks
            if (demand - turb - bess) > RESIDUAL_THRESHOLD_MW
        ]

        print(f"[STATS]  total ticks observed  : {len(all_ticks)}")
        print(f"[STATS]  ticks with residual > {RESIDUAL_THRESHOLD_MW} MW: {len(saturated_ticks)}")
        print(f"[STATS]  ticks with FC > 0     : {len(fc_events)}")
        print(f"[STATS]  peak FC output        : {max_fc_mw:.3f} MW")
        print(f"[STATS]  FC fleet rated MW     : {FC_FLEET_RATED_MW:.1f} MW")
        print(f"[STATS]  violations (FAIL-A)   : {len(violations)}")
        print()

        # ── CHECK A: no saturated tick should have FC = 0 ─────────────────
        if violations:
            for v in violations:
                sim_t, demand, turb, bess, fc = v
                residual = demand - turb - bess
                print(
                    f"  [VIOLATION] sim_t={sim_t:.1f}s  demand={demand:.2f}  "
                    f"turb={turb:.2f}  bess={bess:.2f}  "
                    f"residual={residual:.2f}  fc={fc:.2f}"
                )
            assert False, (
                f"[FAIL-A] {len(violations)} tick(s) had residual > "
                f"{RESIDUAL_THRESHOLD_MW} MW but fuel_cell_output_mw = 0. "
                f"The FC dispatch block is not filling the shortfall."
            )
        print("[PASS-A] No saturated ticks with silent FC.")

        # ── CHECK B: we must have seen FC fire at least N times ───────────
        # If the kube load never saturated turbine+BESS the test is inconclusive,
        # not passing.  Require at least REQUIRED_DISPATCH_EVENTS FC ticks.
        if len(saturated_ticks) == 0:
            # The scenario produced zero saturated ticks — either the stochastic
            # kube scheduler didn't build enough load or something is wrong with
            # the demand model.  Flag as inconclusive so the caller knows this
            # run didn't actually stress the FC.
            assert False, (
                f"[INCONCLUSIVE] No tick had demand − turbine − BESS > "
                f"{RESIDUAL_THRESHOLD_MW} MW.  The run window ({RUN_WINDOW_S} s) "
                f"may be too short or the kube job queue did not saturate. "
                f"Re-run or increase RUN_WINDOW_S."
            )

        assert len(fc_events) >= REQUIRED_DISPATCH_EVENTS, (
            f"[FAIL-B] Only {len(fc_events)} FC dispatch event(s) observed; "
            f"need ≥ {REQUIRED_DISPATCH_EVENTS}.  The FC may be misconfigured "
            f"or the merit-order dispatch path has a gap."
        )
        print(
            f"[PASS-B] Observed {len(fc_events)} FC dispatch events "
            f"(≥ {REQUIRED_DISPATCH_EVENTS} required)."
        )

        # ── CHECK C: peak FC output ≤ fleet rated MW ──────────────────────
        assert max_fc_mw <= FC_FLEET_RATED_MW + 1e-6, (
            f"[FAIL-C] Peak FC output {max_fc_mw:.3f} MW exceeds fleet rated "
            f"{FC_FLEET_RATED_MW:.1f} MW — output is uncapped."
        )
        print(
            f"[PASS-C] Peak FC output {max_fc_mw:.3f} MW ≤ fleet rated "
            f"{FC_FLEET_RATED_MW:.1f} MW."
        )

        print("\n" + "=" * 72)
        print("RESULT: ALL FUEL CELL DISPATCH CHECKS PASSED ✓")
        print("=" * 72)

    finally:
        if run_id:
            try:
                sess.delete(f"/runs/{run_id}")
                print(f"\n[CLEANUP] run {run_id} cancelled.")
            except Exception:
                pass
        sess.close()


# ── pytest entry-point ────────────────────────────────────────────────────────
def test_fuel_cell_dispatch() -> None:
    _run_test()


if __name__ == "__main__":
    _run_test()
