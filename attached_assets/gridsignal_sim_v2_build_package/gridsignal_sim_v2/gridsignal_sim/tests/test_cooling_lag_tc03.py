"""
tests/test_cooling_lag_tc03.py — TC-03 formal test: thermal lag convergence.

Spec requirement (TC-03):
  Hold constant IT load for ≥ Δt_thermal + 5τ (≥ 450 s) and confirm
  mechanical_load_mw (here: CoolingModule.output_mw()) converges to
  α_max × P_compute within 2 % of the asymptote value.

Test approach
─────────────
  • CoolingModule scalar path is used directly — it is deterministic and
    requires no noise suppression (noise lives in the GPU load module, not here).
  • 6 000 ticks at dt = 0.1 s → 600 s simulated wall time.
  • Constant P_compute = 10.0 MW from t = 0.
  • SiteConfig defaults: alpha_max=0.20, tau_seconds=20.0, dt_thermal_seconds=90.0
    giving an asymptote of 0.20 × 10.0 = 2.0 MW.
  • 5τ = 100 s; convergence window starts at dt_thermal + 5τ = 190 s.
    Test window is t ∈ [500 s, 600 s] (ticks 5 000–6 000), well inside it.

Assertions
──────────
  TC03-A  (convergence): every sample in [500, 600] s is within 2 % of
          α_max × P_compute (variance guard: < 0.1 % peak-to-peak spread).
  TC03-B  (zero-lag coupling): all output_mw samples in [0, 60) s are
          identically 0.0, confirming cooling does not track compute
          instantaneously (correlation guard without dividing by zero std).
"""
from __future__ import annotations

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import SiteConfig
from core.asset_modules import CoolingModule


# ---------------------------------------------------------------------------
# SiteConfig constants (kept in sync with SiteConfig defaults)
# ---------------------------------------------------------------------------
_ALPHA_MAX     = 0.20
_TAU_S         = 20.0
_DT_THERMAL_S  = 90.0


def _make_deterministic_cooling() -> CoolingModule:
    """CoolingModule with default SiteConfig — scalar path, fully deterministic."""
    site = SiteConfig(
        site_id="tc03-site",
        frequency_nominal_hz=60.0,
        power_factor=0.85,
        alpha_max=_ALPHA_MAX,
        tau_seconds=_TAU_S,
        dt_thermal_seconds=_DT_THERMAL_S,
    )
    return CoolingModule(asset_id="tc03-cooling", site=site)


def _run_tc03(
    *,
    p_compute_mw: float = 10.0,
    dt_s: float = 0.1,
    n_ticks: int = 6_000,
) -> list[tuple[float, float]]:
    """Drive CoolingModule with constant compute and return [(sim_time, output_mw)].

    Uses the scalar path: record_compute_sample → advance → output_mw.
    """
    cm = _make_deterministic_cooling()
    samples: list[tuple[float, float]] = []

    for i in range(n_ticks):
        t = round(i * dt_s, 9)
        cm.record_compute_sample(t, p_compute_mw)
        cm.advance(t, dt_s)
        samples.append((t, cm.output_mw()))

    return samples


# ---------------------------------------------------------------------------
# TC03-B  Zero-lag coupling guard
# ---------------------------------------------------------------------------

def test_tc03_b_no_zero_lag_coupling():
    """Output is identically 0 for all t < dt_thermal (first 60 s check).

    Cooling must not track compute instantaneously — if output_mw > 0 before
    the thermal dead-time expires, it means the lag was bypassed.
    """
    samples = _run_tc03()

    # Check every sample strictly before dt_thermal (90 s).
    # We use [0, 60) s as the task spec's correlation window.
    zero_lag_window = [(t, mw) for t, mw in samples if t < 60.0]
    assert zero_lag_window, "Expected samples in [0, 60) s — none found"

    for t, mw in zero_lag_window:
        assert mw == 0.0, (
            f"TC03-B FAIL: CoolingModule output non-zero at t={t:.2f} s "
            f"(output={mw:.6f} MW) — thermal dead-time not respected"
        )


# ---------------------------------------------------------------------------
# TC03-A  Convergence assertion
# ---------------------------------------------------------------------------

def test_tc03_a_convergence_within_2pct():
    """mechanical_load_mw at t ∈ [500, 600] s is within 2 % of the asymptote.

    Asymptote = α_max × P_compute.
    This window is well past dt_thermal + 5τ = 90 + 100 = 190 s, so αₖ has
    reached ≥ 99.3 % of α_max (1 − e⁻⁵ ≈ 0.993).

    Two sub-checks:
      (a) every point is within 2 % of the asymptote (tightest allowed gap).
      (b) peak-to-peak spread in the window is < 0.1 % of the asymptote
          (confirms the filter has truly settled; a still-climbing curve
          would have non-trivial within-window spread).
    """
    p_compute_mw = 10.0
    samples = _run_tc03(p_compute_mw=p_compute_mw)

    asymptote = _ALPHA_MAX * p_compute_mw   # 2.0 MW

    # Window: t ∈ [500, 600] s
    window = [mw for t, mw in samples if 500.0 <= t <= 600.0]
    assert len(window) >= 900, (
        f"TC03-A: expected ≥ 900 samples in [500, 600] s; got {len(window)}"
    )

    # (a) every point within 2 % of asymptote
    tol_2pct = 0.02 * asymptote
    for mw in window:
        gap = abs(mw - asymptote)
        assert gap <= tol_2pct, (
            f"TC03-A FAIL: output={mw:.6f} MW deviates {gap:.6f} MW "
            f"from asymptote {asymptote:.6f} MW "
            f"(limit {tol_2pct:.6f} MW = 2 %)"
        )

    # (b) variance guard: peak-to-peak < 0.1 % of asymptote
    spread = max(window) - min(window)
    spread_limit = 0.001 * asymptote
    assert spread <= spread_limit, (
        f"TC03-A FAIL: peak-to-peak spread in convergence window = "
        f"{spread:.6f} MW exceeds 0.1 % of asymptote ({spread_limit:.6f} MW) — "
        f"filter has not settled"
    )


# ---------------------------------------------------------------------------
# TC03-C  Monotonic approach (sanity: output must be non-decreasing during
#         the rise phase until it saturates near the asymptote)
# ---------------------------------------------------------------------------

def test_tc03_c_monotone_rise_until_convergence():
    """Output is non-decreasing from the moment it first becomes non-zero
    until it reaches 99 % of the asymptote.

    Ensures no spurious oscillation or direction reversals in the rise phase.
    """
    p_compute_mw = 10.0
    samples = _run_tc03(p_compute_mw=p_compute_mw)

    asymptote = _ALPHA_MAX * p_compute_mw
    threshold_99 = 0.99 * asymptote

    # Find the first non-zero sample.
    first_nonzero_idx = next(
        (i for i, (_, mw) in enumerate(samples) if mw > 0.0), None
    )
    assert first_nonzero_idx is not None, (
        "TC03-C: output never became non-zero — dt_thermal gate may be broken"
    )

    # Collect the rise phase: from first non-zero until 99 % of asymptote is reached.
    prev_mw = 0.0
    for t, mw in samples[first_nonzero_idx:]:
        assert mw >= prev_mw - 1e-12, (
            f"TC03-C FAIL: non-monotone rise at t={t:.2f} s — "
            f"output dropped from {prev_mw:.8f} to {mw:.8f} MW"
        )
        prev_mw = mw
        if mw >= threshold_99:
            break   # rise phase complete; convergence checks are in TC03-A
