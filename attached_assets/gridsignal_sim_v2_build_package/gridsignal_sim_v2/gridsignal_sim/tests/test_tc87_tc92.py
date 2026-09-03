"""
GS-CHG-2026-08-08 — Phase 3 test suite.

TC-87  P_served + explicit shed equals demand              (xfail — no producer)
TC-88  Supply shortfall co-occurs with frequency excursion (xfail — no producer)
TC-89  Unstaged collapse → supply shortfall stays visible  (xfail — no producer)
TC-90  Staged scenario → p_unserved_mw == 0              (xfail — no producer)
TC-91  Anchor clamp → remainder in p_unserved/p_imbalance (xfail — no producer)
TC-92  Presentation layer: no arithmetic on prohibited fields  (must PASS)

NOTE: TC-87–TC-91 are registered as strict xfail.  A test that unexpectedly
passes (xpass) is reported as an ERROR — it means a producer was wired without
updating this file.  Do NOT change strict=True.
"""

import pathlib
import re

import pytest

# ---------------------------------------------------------------------------
# Synthetic Phase-2 API tick dict — the minimal wire format produced by
# run_manager.py:_tick_result_to_dict() after GS-CHG-2026-08-08 Phase 2.
# All supply/served fields are null per spec §3.2 (no balance-solver producer).
# ---------------------------------------------------------------------------

_PHASE2_TICK = {
    "p_compute_demand_mw":  19.96,   # wired to existing producer
    "p_compute_served_mw":  None,    # no producer
    "p_compute_unserved_mw": None,   # no producer
    "p_cooling_demand_mw":  4.59,    # wired to existing producer
    "p_cooling_served_mw":  None,    # no producer
    "p_cooling_unserved_mw": None,   # no producer
    "p_demand_mw":          24.55,   # wired to existing producer
    "p_served_mw":          None,    # no producer
    "p_unserved_mw":        None,    # no producer
    "p_generation_mw":      None,    # no single-aggregate producer
    "p_imbalance_mw":       None,    # no producer
    "frequency_hz":         59.5,    # representative islanded tick
}


# ---------------------------------------------------------------------------
# TC-87  P_served + explicit shed == P_demand (load-side identity)
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason=(
        "No load-side served/shed producer in this synthetic Phase-2 payload. "
        "GS-CHG-2026-08-08 §TC-87 — wire both fields before expecting this to pass."
    ),
)
def test_tc87_served_plus_explicit_shed_equals_demand():
    """At every tick, P_served_mw + P_unserved_mw equals P_demand_mw.

    Explicit shed is a load-side control result, not a generation shortfall.
    Until the synthetic payload has these producers, the assertion below fails.
    """
    tick = _PHASE2_TICK
    assert tick["p_served_mw"] is not None, (
        "p_served_mw is null — no producer has been wired "
        "(GS-CHG-2026-08-08 Phase 2, §3.2)"
    )
    assert tick["p_unserved_mw"] is not None, (
        "p_unserved_mw is null — no producer has been wired "
        "(GS-CHG-2026-08-08 Phase 2, §3.2)"
    )
    delta = abs(
        tick["p_served_mw"] + tick["p_unserved_mw"] - tick["p_demand_mw"]
    )
    assert delta < 0.01, (
        f"Load-side identity violated: served({tick['p_served_mw']}) + "
        f"explicit_shed({tick['p_unserved_mw']}) != "
        f"demand({tick['p_demand_mw']}) by {delta:.4f} MW"
    )


# ---------------------------------------------------------------------------
# TC-88  Supply shortfall co-occurs with a frequency excursion
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason=(
        "p_imbalance_mw has no producer — cannot verify frequency co-occurrence. "
        "GS-CHG-2026-08-08 §TC-88."
    ),
)
def test_tc88_supply_shortfall_implies_frequency_excursion():
    """At every tick where p_imbalance_mw < -0.01, frequency is below nominal.

    A negative supply imbalance, rather than explicit protective shed, is the
    direct signal that active-power balance is broken.
    """
    # Construct a tick that WOULD represent a partial-supply event
    tick = dict(_PHASE2_TICK, frequency_hz=58.8)  # below nominal 60 Hz

    assert tick["p_imbalance_mw"] is not None, (
        "p_imbalance_mw is null — no producer; TC-88 cannot be evaluated."
    )
    if tick["p_imbalance_mw"] < -0.01:
        nominal_hz = 60.0
        uf_warning = 59.5
        assert tick["frequency_hz"] < uf_warning, (
            f"Supply shortfall ({tick['p_imbalance_mw']:.3f} MW) at tick where "
            f"frequency_hz={tick['frequency_hz']:.3f} Hz is above UF warning "
            f"threshold {uf_warning} Hz — physics inconsistency."
        )


# ---------------------------------------------------------------------------
# TC-89  Unstaged islanded deficit → p_imbalance_mw < 0 at collapse
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason=(
        "p_imbalance_mw has no producer. "
        "TC-89 requires a balance solver to classify uncovered supply. "
        "GS-CHG-2026-08-08 §TC-89."
    ),
)
def test_tc89_unstaged_collapse_supply_shortfall():
    """Islanded, unstaged deficit: p_imbalance_mw remains negative at collapse.

    Scenario: demo islanded ramp, turbine commitment disabled so that no unit
    is synchronised when compute demand ramps.  Under-frequency protection
    operates at or below ufls_stage1_hz. The supply shortfall must remain visible
    in p_imbalance_mw; p_unserved_mw changes only if UFLS explicitly sheds load.

    Built against the demonstration scenario definition (islanded_8_60_10_ramp),
    not a separate fixture. Currently fails because p_imbalance_mw is null.
    """
    # Phase 2 wire tick at the collapse moment — p_imbalance_mw is null
    collapse_tick = dict(_PHASE2_TICK, frequency_hz=57.0)

    assert collapse_tick["p_imbalance_mw"] is not None, (
        "p_imbalance_mw is null at collapse tick — no producer (GS-CHG-2026-08-08 §3.2)."
    )
    assert collapse_tick["p_imbalance_mw"] < -0.01, (
        f"Expected supply shortfall at collapse, got "
        f"p_imbalance_mw={collapse_tick['p_imbalance_mw']:.3f} MW"
    )


# ---------------------------------------------------------------------------
# TC-90  Staged scenario → p_unserved_mw == 0 throughout
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason=(
        "p_unserved_mw has no producer. "
        "TC-90 requires a balance solver to confirm zero unserved demand. "
        "GS-CHG-2026-08-08 §TC-90."
    ),
)
def test_tc90_staged_no_unserved():
    """Staged islanded ramp: turbines committed before deficit → p_unserved_mw == 0.

    Same demand curve as TC-89 but with the full commitment engine active.
    Every tick must show p_unserved_mw == 0 (or None is prohibited).

    Currently fails because p_unserved_mw is null — the balance solver has not
    been wired.
    """
    # Representative tick from the staged demo scenario — normal operating state
    staged_tick = dict(_PHASE2_TICK, frequency_hz=59.97)

    assert staged_tick["p_unserved_mw"] is not None, (
        "p_unserved_mw is null — no producer; TC-90 cannot be evaluated. "
        "GS-CHG-2026-08-08 §3.2."
    )
    assert staged_tick["p_unserved_mw"] == 0.0, (
        f"Staged run should show zero unserved demand; got "
        f"p_unserved_mw={staged_tick['p_unserved_mw']:.3f} MW"
    )


# ---------------------------------------------------------------------------
# TC-91  BESS anchor clamp → uncovered remainder in p_imbalance_mw
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason=(
        "p_imbalance_mw has no producer. "
        "TC-91 requires a supply-clamped balance solver snapshot. "
        "GS-CHG-2026-08-08 §TC-91."
    ),
)
def test_tc91_anchor_clamp_supply_shortfall():
    """BESS at anchor reserve limit: supply term clamped → negative imbalance.

    When BESS output is capped by the anchor reserve (rated − anchor_mw), the
    dispatch setpoint cannot fully cover demand. The uncovered MW must appear
    in p_imbalance_mw; p_unserved_mw remains reserved for explicit shed.

    Currently fails because p_imbalance_mw is null.
    """
    # Tick where BESS is clamped at anchor limit (setpoint hits rated − 1.0 MW)
    clamped_tick = dict(_PHASE2_TICK, p_demand_mw=26.0)  # > feasible supply

    assert clamped_tick["p_imbalance_mw"] is not None, (
        "p_imbalance_mw is null when BESS is anchor-clamped. "
        "It must carry the uncovered supply shortfall. "
        "GS-CHG-2026-08-08 §TC-91."
    )
    assert clamped_tick["p_imbalance_mw"] < -0.01, (
        f"Expected negative supply imbalance at anchor clamp; "
        f"p_imbalance_mw={clamped_tick['p_imbalance_mw']:.3f} MW"
    )


# ---------------------------------------------------------------------------
# TC-92  Presentation layer: no arithmetic on prohibited fields  (must PASS)
# ---------------------------------------------------------------------------

def test_tc92_no_presentation_arithmetic():
    """Static inspection: prohibited fields are read-only in the presentation layer.

    The presentation layer must NOT compute any difference, sum, clamp, min/max,
    or numeric fallback (e.g. ?? 0) on:
      p_demand_mw, p_served_mw, p_unserved_mw, p_generation_mw, p_imbalance_mw

    Inspect every TypeScript / TSX source file under frontend/src/.
    """
    frontend_root = (
        pathlib.Path(__file__).parents[2]  # gridsignal_sim_v2/
        / "frontend" / "src"
    )
    assert frontend_root.exists(), (
        f"Frontend source directory not found at {frontend_root}. "
        "Adjust the path if the workspace layout has changed."
    )

    # Fields that must never be involved in arithmetic in the presentation layer
    prohibited_fields = [
        "p_demand_mw",
        "p_served_mw",
        "p_unserved_mw",
        "p_generation_mw",
        "p_imbalance_mw",
    ]

    # Patterns that indicate arithmetic (not string formatting or null checks)
    # Each pattern is parameterised per field name.
    #
    # Captured patterns:
    #   field OP expr       e.g.  tick.p_demand_mw + 3
    #   expr OP field       e.g.  4 - tick.p_demand_mw
    #   field ?? <number>   fallback to a numeric literal
    #   Math.min/max(..,field..)  numeric extremum
    #
    # NOT captured (these are intentional and allowed):
    #   .toFixed()          string formatting
    #   !== null / == null  null guard / conditional
    #   ?? 'string'         string-constant fallback for display
    #   ?? null             null propagation

    def build_patterns(field: str) -> list[re.Pattern]:
        f = re.escape(field)
        return [
            # field OP number-or-identifier (arithmetic operator)
            re.compile(rf'\b{f}\b\s*[+\-*/]'),
            # number-or-identifier OP field
            re.compile(rf'[+\-*/]\s*(?:\w+\.)*{f}\b'),
            # field ?? <numeric literal>
            re.compile(rf'\b{f}\b\s*\?\?\s*[\d\-]'),
            # Math extremum involving the field
            re.compile(rf'Math\s*\.\s*(?:min|max|abs)\s*\([^)]*\b{f}\b'),
        ]

    violations: list[str] = []

    for ts_file in sorted(frontend_root.rglob("*.ts")) + sorted(frontend_root.rglob("*.tsx")):
        try:
            src = ts_file.read_text(encoding="utf-8")
        except OSError:
            continue

        # Strip single-line comments so that comment text cannot trigger
        # false positives.  Multi-line /* */ comments are not used on the
        # relevant lines in this project.
        src_no_comments = "\n".join(
            line for line in src.splitlines()
            if not line.lstrip().startswith("//")
        )

        for field in prohibited_fields:
            for pattern in build_patterns(field):
                for match in pattern.finditer(src_no_comments):
                    # Find the line number
                    line_no = src[:match.start()].count("\n") + 1
                    line = src.splitlines()[line_no - 1].strip()
                    rel = ts_file.relative_to(frontend_root.parent.parent)
                    violations.append(f"{rel}:{line_no}: {line}")

    assert not violations, (
        "TC-92 FAIL — arithmetic found on prohibited fields in the presentation layer:\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\n\nProhibited fields: " + ", ".join(prohibited_fields)
        + "\nAllowed: .toFixed(), !== null, ?? 'string constant', ternary for display."
    )
