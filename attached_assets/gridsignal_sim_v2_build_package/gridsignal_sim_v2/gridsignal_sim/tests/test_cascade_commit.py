"""
tests/test_cascade_commit.py — Black-box cascade turbine commit test.

Verifies that the fixed fuel-cell baseload does not get mistaken for an
elastic residual dispatch command in scenario-kube-peak-overage.  Under the
measured FC ramp, this workload leaves turbine-0 below the 50% cascade
threshold, so the old cascade expectation has no valid equivalent in this
scenario.  The direct commitment tests cover the positive cascade path.

Protocol:
  1. Mint a JWT from SESSION_SECRET (no login flow required).
  2. POST /runs  with scenario_id="scenario-kube-peak-overage".
   3. Poll GET /runs/{run_id}/latest-tick every POLL_S seconds.
   4. Assert the completed fixed-baseload outcome.
   5. DELETE /runs/{run_id} to cancel when done.

Run:
  cd gridsignal_sim
  SESSION_SECRET=<secret> python -m pytest tests/test_cascade_commit.py -s -v

Or directly:
  SESSION_SECRET=<secret> python tests/test_cascade_commit.py
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pytest
from jose import jwt

# ── Config ──────────────────────────────────────────────────────────────────
BASE_URL          = "http://localhost:22126"
SCENARIO_ID       = "scenario-kube-peak-overage"
CASCADE_FRACTION  = 0.5            # must match scenario spec
POLL_S            = 0.5            # seconds between latest-tick polls
STAGE_TIMEOUT_S   = 360.0          # max real seconds to wait for run completion
# Unit order in the cascade
UNITS = ["turbine-0", "turbine-1", "turbine-2", "turbine-3"]
# Each lead unit triggers the next via cascade_commit_fraction × rated_mw.
# turbine-0 rated 25 MW → threshold 12.5 MW; same for all units in this scenario.


def _mint_token() -> str:
    """Create a 24-hour JWT using the server's SESSION_SECRET."""
    secret = os.environ.get("SESSION_SECRET") or os.environ.get("JWT_SECRET", "")
    if not secret:
        raise RuntimeError(
            "Set SESSION_SECRET (or JWT_SECRET) in the environment "
            "to match the running server's secret."
        )
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {"sub": "1", "email": "lloyd@workforcementor.com", "exp": expire}
    return jwt.encode(payload, secret, algorithm="HS256")


def _session(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        cookies={"gs_session": token},
        timeout=15.0,
    )


def _unit(tick: dict, asset_id: str) -> Optional[dict]:
    for u in tick.get("turbine_units", []):
        if u.get("asset_id") == asset_id:
            return u
    return None


def _rated_mw(tick: dict, asset_id: str) -> float:
    u = _unit(tick, asset_id)
    return float(u.get("rated_mw", 25.0)) if u else 25.0


def _output_mw(tick: dict, asset_id: str) -> float:
    u = _unit(tick, asset_id)
    return float(u.get("output_mw", 0.0)) if u else 0.0


def _fuel_cell_output_mw(tick: dict) -> float:
    return float(tick.get("fuel_cell_output_mw", 0.0))


def _state(tick: dict, asset_id: str) -> str:
    u = _unit(tick, asset_id)
    return str(u.get("state", "unknown")) if u else "unknown"


def _threshold_mw(tick: dict, asset_id: str) -> float:
    return CASCADE_FRACTION * _rated_mw(tick, asset_id)


def run_test() -> None:
    print("\n" + "="*60)
    print("CASCADE COMMIT BLACK-BOX TEST")
    print("scenario:", SCENARIO_ID)
    print("="*60)

    token   = _mint_token()
    sess    = _session(token)

    # ── 1. Start the run ────────────────────────────────────────────────────
    resp = sess.post("/runs", json={"scenario_id": SCENARIO_ID})
    if resp.status_code != 201:
        raise AssertionError(
            f"POST /runs failed: {resp.status_code} — {resp.text[:300]}"
        )
    run_id = resp.json()["run_id"]
    print(f"\n[START] run_id={run_id}")

    def cleanup() -> None:
        try:
            sess.delete(f"/runs/{run_id}")
            print(f"\n[CANCEL] run {run_id} deleted.")
        except Exception:
            pass

    try:
        # ── 2. Wait for the first tick ────────────────────────────────────
        print("\n[WAIT] polling for first tick …")
        deadline = time.monotonic() + 30.0
        tick: dict = {}
        while time.monotonic() < deadline:
            r = sess.get(f"/runs/{run_id}/latest-tick")
            if r.status_code == 200:
                tick = r.json()
                if "turbine_units" in tick:
                    break
            time.sleep(POLL_S)
        else:
            raise AssertionError("Timed out waiting for first tick with turbine_units")

        print(f"[TICK]  sim_time={tick.get('sim_time_seconds', '?'):.1f}s  "
              f"turbine_units count={len(tick.get('turbine_units', []))}")

        # ── 3. Assert initial state ───────────────────────────────────────
        t0_state = _state(tick, "turbine-0")
        assert t0_state == "synchronised", (
            f"turbine-0 should start SYNCHRONISED (on bus), got {t0_state!r}"
        )
        initial_released = [
            uid for uid in UNITS[1:] if _state(tick, uid) != "offline"
        ]
        assert len(initial_released) <= 1, (
            "Before the cascade threshold is reached, at most the independent "
            f"contingency policy may release one standby; got {initial_released}"
        )
        print(
            "\n[PASS]  Initial states correct — turbine-0 online; "
            f"contingency releases={initial_released or 'none'}"
        )

        # ── 4. Let the authored workload finish ───────────────────────────
        # The old test waited for an impossible 12.5 MW lead output and then
        # timed out.  The FC now follows a 20 MW aggregate target, so the
        # correct black-box assertion is that this scenario stays below the
        # cascade threshold instead of manufacturing turbine demand.
        deadline = time.monotonic() + STAGE_TIMEOUT_S
        while time.monotonic() < deadline:
            r = sess.get(f"/runs/{run_id}/latest-tick")
            if r.status_code == 200:
                tick = r.json()
                sim_t = float(tick.get("sim_time_seconds", 0))
                if sim_t >= 3600.0:
                    break
            elif r.status_code == 404:
                raise AssertionError(f"Run {run_id!r} disappeared before completion")
            time.sleep(POLL_S)
        else:
            raise AssertionError(
                "Timed out waiting for scenario-kube-peak-overage to finish"
            )

        fc_output = _fuel_cell_output_mw(tick)
        assert fc_output == pytest.approx(20.0, abs=1e-6), (
            "The aggregate fuel-cell module should settle at its 20 MW "
            "nameplate target rather than being residual-filled."
        )
        assert _output_mw(tick, UNITS[0]) < _threshold_mw(tick, UNITS[0]), (
            "Fixed FC baseload must not be converted into enough residual "
            "demand to trigger the first cascade stage."
        )
        released_followers = [
            uid for uid in UNITS[1:] if _state(tick, uid) != "offline"
        ]
        assert len(released_followers) <= 1, (
            "Below-threshold cascade logic must not step through the standby "
            "fleet. One follower may be released by the separately tested "
            f"contingency policy; got {released_followers}."
        )

        # ── 5. Final snapshot ─────────────────────────────────────────────
        r = sess.get(f"/runs/{run_id}/latest-tick")
        if r.status_code == 200:
            tick = r.json()
            print(f"\n[FINAL SNAPSHOT] sim_time={tick.get('sim_time_seconds', '?'):.0f}s")
            for uid in UNITS:
                print(f"  {uid:12s}  state={_state(tick, uid):14s}  "
                      f"output={_output_mw(tick, uid):.2f} MW")

        print("\n" + "="*60)
        print("RESULT: FIXED-BASELOAD CASCADE GUARD PASSED")
        print("="*60 + "\n")

    finally:
        cleanup()


# ── pytest entry point ────────────────────────────────────────────────────────
def test_cascade_commit_sequence() -> None:
    """pytest wrapper — runs the full cascade black-box test."""
    run_test()


if __name__ == "__main__":
    try:
        run_test()
        sys.exit(0)
    except AssertionError as exc:
        print(f"\n{'='*60}\nRESULT: FAIL — {exc}\n{'='*60}\n", file=sys.stderr)
        sys.exit(1)
