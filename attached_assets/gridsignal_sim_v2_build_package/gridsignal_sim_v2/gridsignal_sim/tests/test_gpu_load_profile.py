"""
tests/test_gpu_load_profile.py — Black-box GPU load profile test.

Verifies that scenario-kube-peak-overage applies the three-phase
zero-order-hold load profile correctly:

  Phase 1: sim_time  <  720 s  →  gpu_load_fraction == 1.00
  Phase 2: sim_time  < 2400 s  →  gpu_load_fraction == 0.50
  Phase 3: sim_time >= 2400 s  →  gpu_load_fraction == 0.10

Checks:
  A. Every observed tick has the correct fraction for its phase.
  B. The fraction step happens on the right sim_time tick, not before.
  C. p_compute_demand_mw in phase 2 is lower than phase 1 mean
     (stochastic load, so we assert phase2_mean < phase1_mean × 0.9
      to give ample slack while still catching a broken multiplier).
  D. p_compute_demand_mw in phase 3 is lower still
     (assert phase3_mean < phase2_mean × 0.5 — same slack approach).

Protocol:
  1. Mint a JWT from SESSION_SECRET.
  2. POST /runs with playback_speed=0 (max-speed run).
  3. Poll GET /runs/{run_id}/latest-tick at POLL_S intervals.
  4. Bucket ticks into three phases; assert invariants after each
     boundary is crossed.
  5. DELETE /runs/{run_id} to cancel.

Run:
  cd gridsignal_sim
  SESSION_SECRET=<secret> python tests/test_gpu_load_profile.py
  # or via pytest:
  SESSION_SECRET=<secret> python -m pytest tests/test_gpu_load_profile.py -s -v
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from jose import jwt

# ── Config ───────────────────────────────────────────────────────────────────
BASE_URL       = "http://localhost:22126"
SCENARIO_ID    = "scenario-kube-peak-overage"
POLL_S         = 0.3       # fast poll — sim runs at max speed
TOTAL_TIMEOUT  = 300.0     # real seconds; a max-speed 3600 s run finishes in < 60 s

# Profile boundaries (sim-seconds) and expected fractions — must match the spec.
PHASE1_END   = 720.0    # fraction switches from 1.0 → 0.5 at this sim_time
PHASE2_END   = 2400.0   # fraction switches from 0.5 → 0.1 at this sim_time
FRAC_P1      = 1.0
FRAC_P2      = 0.5
FRAC_P3      = 0.1
TOLERANCE    = 1e-6     # float comparison tolerance for exact fraction checks


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


def _expected_fraction(sim_t: float) -> float:
    if sim_t >= PHASE2_END:
        return FRAC_P3
    if sim_t >= PHASE1_END:
        return FRAC_P2
    return FRAC_P1


def _phase_name(sim_t: float) -> str:
    if sim_t >= PHASE2_END:
        return "phase-3"
    if sim_t >= PHASE1_END:
        return "phase-2"
    return "phase-1"


def _run_test() -> None:
    token  = _mint_token()
    sess   = _session(token)
    run_id: Optional[str] = None

    try:
        # ── Start run ────────────────────────────────────────────────────────
        resp = sess.post("/runs", json={
            "scenario_id":    SCENARIO_ID,
            "playback_speed": 0.0,           # max speed
        })
        assert resp.status_code in (200, 201), (
            f"POST /runs failed: {resp.status_code} — {resp.text[:400]}"
        )
        run_id = resp.json().get("run_id")
        assert run_id, f"No run_id in response: {resp.json()}"
        print(f"[START]  run_id={run_id}")

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

        # ── Phase tracking ────────────────────────────────────────────────────
        # Buckets: lists of (sim_time, gpu_load_fraction, p_compute_demand_mw)
        phase_samples: dict[int, list[tuple[float, float, float]]] = {1: [], 2: [], 3: []}

        # Boundary-crossing check: track last tick before each crossing.
        last_before_p2: Optional[tuple[float, float]] = None  # (sim_t, frac)
        last_before_p3: Optional[tuple[float, float]] = None

        crossed_p2 = False
        crossed_p3 = False
        seen_sim_t: float = -1.0

        print(f"[POLL]   collecting ticks across all three phases …")

        while time.monotonic() < deadline:
            r = sess.get(f"/runs/{run_id}/latest-tick")
            if r.status_code != 200:
                time.sleep(POLL_S)
                continue
            tick = r.json()
            if not tick:
                time.sleep(POLL_S)
                continue

            sim_t = float(tick.get("sim_time_seconds", 0.0))
            frac  = float(tick.get("gpu_load_fraction", 1.0))
            pload = float(tick.get("p_compute_demand_mw", 0.0))

            # Skip duplicate ticks (sim advances in 5 s steps at max speed)
            if sim_t == seen_sim_t:
                time.sleep(POLL_S)
                continue
            seen_sim_t = sim_t

            phase = _phase_name(sim_t)
            expected_frac = _expected_fraction(sim_t)

            print(
                f"  {phase}  sim_t={sim_t:7.1f}s  "
                f"frac={frac:.2f} (expect {expected_frac:.2f})  "
                f"p_compute={pload:.2f} MW"
            )

            # ── CHECK A: fraction must match expected at every tick ─────────
            assert abs(frac - expected_frac) < TOLERANCE, (
                f"[FAIL-A] {phase} sim_t={sim_t:.1f}s: "
                f"gpu_load_fraction={frac} expected {expected_frac}"
            )

            # Track boundary-crossing evidence
            if sim_t < PHASE1_END:
                last_before_p2 = (sim_t, frac)
            if sim_t < PHASE2_END and sim_t >= PHASE1_END:
                last_before_p3 = (sim_t, frac)

            # Record into bucket
            if sim_t < PHASE1_END:
                phase_samples[1].append((sim_t, frac, pload))
            elif sim_t < PHASE2_END:
                if not crossed_p2:
                    crossed_p2 = True
                    if last_before_p2:
                        lt, lf = last_before_p2
                        print(
                            f"\n[TRANSITION 1→2]  last-before={lt:.1f}s frac={lf:.2f} "
                            f"→ first-after={sim_t:.1f}s frac={frac:.2f}"
                        )
                        # ── CHECK B1: fraction before crossing was 1.0 ────────
                        assert abs(lf - FRAC_P1) < TOLERANCE, (
                            f"[FAIL-B1] last tick before phase-2 boundary had "
                            f"frac={lf} (expected {FRAC_P1})"
                        )
                        print("[PASS-B1] fraction was 1.0 immediately before phase-2 boundary")
                    print(f"[PASS-A]  fraction correctly stepped to 0.5 at sim_t={sim_t:.1f}s\n")
                phase_samples[2].append((sim_t, frac, pload))
            else:
                if not crossed_p3:
                    crossed_p3 = True
                    if last_before_p3:
                        lt, lf = last_before_p3
                        print(
                            f"\n[TRANSITION 2→3]  last-before={lt:.1f}s frac={lf:.2f} "
                            f"→ first-after={sim_t:.1f}s frac={frac:.2f}"
                        )
                        # ── CHECK B2: fraction before crossing was 0.5 ────────
                        assert abs(lf - FRAC_P2) < TOLERANCE, (
                            f"[FAIL-B2] last tick before phase-3 boundary had "
                            f"frac={lf} (expected {FRAC_P2})"
                        )
                        print("[PASS-B2] fraction was 0.5 immediately before phase-3 boundary")
                    print(f"[PASS-A]  fraction correctly stepped to 0.1 at sim_t={sim_t:.1f}s\n")
                phase_samples[3].append((sim_t, frac, pload))

            # Stop once we have ≥10 samples in phase 3 (confirms sustained behaviour)
            if len(phase_samples[3]) >= 10:
                break

            # Also stop if the run is done
            status = tick.get("status") or tick.get("run_status", "")
            if status in ("completed", "cancelled", "failed"):
                print(f"[INFO]   run finished with status={status!r}")
                break

            time.sleep(POLL_S)

        # ── Coverage check ────────────────────────────────────────────────────
        assert len(phase_samples[1]) > 0, "[FAIL] No phase-1 ticks observed."
        assert len(phase_samples[2]) > 0, "[FAIL] No phase-2 ticks observed (profile never reached 720 s?)."
        assert len(phase_samples[3]) > 0, "[FAIL] No phase-3 ticks observed (profile never reached 2400 s?)."

        # ── CHECK C: phase-2 mean compute < 90% of phase-1 mean ─────────────
        mean1 = sum(p for _, _, p in phase_samples[1]) / len(phase_samples[1])
        mean2 = sum(p for _, _, p in phase_samples[2]) / len(phase_samples[2])
        mean3 = sum(p for _, _, p in phase_samples[3]) / len(phase_samples[3])

        print(f"\n[STATS]  phase-1 mean p_compute={mean1:.2f} MW  (n={len(phase_samples[1])})")
        print(f"[STATS]  phase-2 mean p_compute={mean2:.2f} MW  (n={len(phase_samples[2])})")
        print(f"[STATS]  phase-3 mean p_compute={mean3:.2f} MW  (n={len(phase_samples[3])})")

        if mean1 > 0.5:   # only meaningful once jobs have built up
            assert mean2 < mean1 * 0.9, (
                f"[FAIL-C] phase-2 mean ({mean2:.2f} MW) not below 90% of "
                f"phase-1 mean ({mean1:.2f} MW). Profile multiplier may not be applied."
            )
            print("[PASS-C] phase-2 p_compute is below 90% of phase-1 mean")

        # ── CHECK D: phase-3 mean compute < 50% of phase-2 mean ─────────────
        if mean2 > 0.5:
            assert mean3 < mean2 * 0.5, (
                f"[FAIL-D] phase-3 mean ({mean3:.2f} MW) not below 50% of "
                f"phase-2 mean ({mean2:.2f} MW). Profile multiplier may not be applied."
            )
            print("[PASS-D] phase-3 p_compute is below 50% of phase-2 mean")

        print("\n" + "=" * 60)
        print("RESULT: ALL GPU LOAD PROFILE CHECKS PASSED ✓")
        print("=" * 60)

    finally:
        if run_id:
            try:
                sess.delete(f"/runs/{run_id}")
                print(f"\n[CLEANUP] run {run_id} cancelled.")
            except Exception:
                pass
        sess.close()


# ── pytest entry-point ────────────────────────────────────────────────────────
def test_gpu_load_profile() -> None:
    _run_test()


if __name__ == "__main__":
    _run_test()
