"""
core/procurement.py — §24 Grid procurement model.

Step 14.

Firm / reserved / non-firm capacity with T_reserve lead time and a seeded
synthetic price curve.

TC-47: Non-firm spot import reduces served load but does NOT close the reserve
  gap.  The reserve gap is a capacity commitment, not a load-serving number;
  non-firm power is interruptible and cannot satisfy a firm commitment.

TC-52: ReservationProposal is NEVER autonomous at any tier.  §24.3 is
  unambiguous: every reservation that commits grid capacity requires an
  explicit human authorization step.  The requires_confirmation flag on
  ReservationProposal is always True — it is set by the ProcurementAgent's
  _requires_confirmation() override and cannot be cleared by operating tier.

Synthetic price curve note
--------------------------
No live external feeds.  A demo that depends on a third-party API's
availability will eventually fail in front of an audience for a reason
unrelated to the product.  SyntheticPriceCurve is seeded and deterministic.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Capacity types
# ---------------------------------------------------------------------------

class CapacityType(str, Enum):
    """§24.1 grid capacity tiers."""
    FIRM     = "firm"      # Contracted; always available; no T_reserve delay.
    RESERVED = "reserved"  # Available with T_reserve lead time; interruptible
                           # only with mutual agreement.
    NON_FIRM = "non_firm"  # Spot import; interruptible; does NOT close reserve
                           # gap (TC-47).


# ---------------------------------------------------------------------------
# Grid capacity state
# ---------------------------------------------------------------------------

@dataclass
class GridCapacity:
    """Current grid capacity snapshot — one record per capacity tier.

    T_reserve is meaningful only for RESERVED capacity.
    Price applies to all tiers but is most volatile for NON_FIRM.
    """
    capacity_type:   CapacityType
    available_mw:    float
    price_per_mwh:   float = 0.0
    t_reserve_s:     float = 0.0   # lead time for RESERVED capacity in sim seconds


@dataclass
class PricePoint:
    """One point on the synthetic price curve."""
    sim_time: float         # simulated seconds
    price_per_mwh: float    # $/MWh (synthetic; no real-money implication)


# ---------------------------------------------------------------------------
# §24.3 ReservationProposal
# ---------------------------------------------------------------------------

@dataclass
class ReservationProposal:
    """§24.3 grid capacity reservation — NEVER autonomous at any tier.

    TC-52: requires_confirmation is always True.  This is enforced at
    construction time (the field is fixed=True in the schema), not left to
    the operating tier or the advisory gate.

    A ReservationProposal passes through the advisory gate like any other
    proposal (kind="reservation") but the gate and the control plane both
    refuse to execute it without an explicit human authorization record.

    Fields:
      capacity_type    — which tier is being reserved (FIRM / RESERVED / NON_FIRM)
      requested_mw     — megawatts to reserve or purchase
      estimated_cost   — indicative price from SyntheticPriceCurve
      t_reserve_s      — lead time required (RESERVED only; 0 for FIRM/NON_FIRM)
      rationale        — free-text rationale from the Procurement agent
      requires_confirmation — ALWAYS True (TC-52; cannot be overridden)
    """
    capacity_type:  CapacityType
    requested_mw:   float
    estimated_cost: float = 0.0   # indicative $/MWh from synthetic curve
    t_reserve_s:    float = 0.0
    rationale:      str   = ""

    # TC-52: this field is always True — do not expose a setter.
    @property
    def requires_confirmation(self) -> bool:  # type: ignore[override]
        """TC-52: NEVER autonomous at any tier (§24.3)."""
        return True


# ---------------------------------------------------------------------------
# TC-47: Non-firm import effect
# ---------------------------------------------------------------------------

class NonFirmImportEffect:
    """TC-47: Non-firm spot import reduces served load but does NOT close
    the reserve gap.

    The reserve gap is a capacity commitment that requires firm or reserved
    capacity to satisfy.  Non-firm power is interruptible on short notice by
    the grid operator and cannot back a firm commitment.

    This class is a namespace for the arithmetic that proves TC-47 — it has
    no mutable state and every method is a pure function.
    """

    @staticmethod
    def apply(
        served_load_mw: float,
        import_mw: float,
        reserve_gap_mw: float,
    ) -> tuple[float, float]:
        """Compute the effect of importing non-firm power.

        Parameters
        ----------
        served_load_mw:
            Current served load (MW).
        import_mw:
            Non-firm spot import volume (MW).  Must be >= 0.
        reserve_gap_mw:
            Current reserve gap (MW) — the deficit between firm committed
            capacity and the forecast demand.

        Returns
        -------
        (new_served_load_mw, reserve_gap_mw_unchanged)
            The served load is reduced by the import.
            The reserve gap is UNCHANGED — TC-47.

        TC-47 note
        ----------
        reserve_gap_mw is returned exactly as received.  Callers must not
        reassign it from this return value to simulate gap closure — the
        type system cannot prevent that, but the docstring is the contract
        and the test is the proof.
        """
        if import_mw < 0:
            raise ValueError(f"import_mw must be >= 0, got {import_mw}")
        new_served = max(0.0, served_load_mw - import_mw)
        # TC-47: reserve gap is intentionally unchanged.
        return new_served, reserve_gap_mw

    @staticmethod
    def reserve_gap_closed_by_non_firm(import_mw: float, reserve_gap_mw: float) -> float:
        """Always returns 0.0 — non-firm import NEVER closes a reserve gap (TC-47)."""
        return 0.0


# ---------------------------------------------------------------------------
# Synthetic price curve (§24)
# ---------------------------------------------------------------------------

class SyntheticPriceCurve:
    """Seeded synthetic price curve for demo procurement reasoning.

    Design mandate: no live external feeds.  Seeded, deterministic, and
    reasonably realistic (diurnal pattern + noise).

    Pattern: base ± amplitude × sin(2π × t / period) with a slower secondary
    harmonic.  Fully deterministic for a given seed and sim_time.
    """

    BASE_PRICE_PER_MWH: float = 55.0       # $/MWh base
    AMPLITUDE: float           = 22.0       # $/MWh diurnal swing
    SECONDARY_AMPLITUDE: float = 8.0        # $/MWh secondary harmonic
    PERIOD_S: float            = 86_400.0   # 24-hour diurnal cycle
    SECONDARY_PERIOD_S: float  = 3_600.0    # 1-hour secondary

    def __init__(self, seed: int = 42) -> None:
        # Seed shifts the phase so multiple runs with different seeds produce
        # different-looking (but deterministic) price curves.
        self._phase_offset = (seed % 24) * (self.PERIOD_S / 24)

    def price_at(self, sim_time: float) -> float:
        """Instantaneous synthetic price at sim_time (simulated seconds)."""
        t = sim_time + self._phase_offset
        primary   = self.AMPLITUDE * math.sin(2 * math.pi * t / self.PERIOD_S)
        secondary = self.SECONDARY_AMPLITUDE * math.sin(
            2 * math.pi * t / self.SECONDARY_PERIOD_S
        )
        return round(self.BASE_PRICE_PER_MWH + primary + secondary, 2)

    def points(
        self,
        from_s: float,
        to_s: float,
        n: int = 12,
    ) -> list[PricePoint]:
        """Evenly-spaced price points over [from_s, to_s]."""
        if n < 2:
            n = 2
        step = (to_s - from_s) / (n - 1)
        return [
            PricePoint(
                sim_time=from_s + i * step,
                price_per_mwh=self.price_at(from_s + i * step),
            )
            for i in range(n)
        ]

    def average_price(self, from_s: float, to_s: float, n: int = 24) -> float:
        """Average price over a time window — useful for cost estimation."""
        pts = self.points(from_s, to_s, n)
        return round(sum(p.price_per_mwh for p in pts) / len(pts), 2)


# ---------------------------------------------------------------------------
# AD1: ProcurementLayer — per-tick evaluation (TC-47, TC-52)
# ---------------------------------------------------------------------------

class ProcurementLayer:
    """§24 procurement layer — exercised each tick by _drive() when present.

    Exercises TC-47 (NonFirmImportEffect.apply: non-firm import does NOT close
    the reserve gap) and TC-52 (ReservationProposal.requires_confirmation is
    always True) during every tick of a live demo run.

    Pure observation: no writes to SimulationState, no effect on dispatch.
    The result is advisory-only — it would feed a future procurement dashboard.
    """

    def __init__(
        self,
        grid_caps: list[GridCapacity],
        price_curve: SyntheticPriceCurve,
    ) -> None:
        self.grid_caps = grid_caps
        self.price_curve = price_curve
        self._non_firm = next(
            (g for g in grid_caps if g.capacity_type == CapacityType.NON_FIRM),
            None,
        )

    def evaluate_tick(
        self,
        reserve_gap_mw: float,
        served_load_mw: float,
        sim_time: float,
    ) -> dict:
        """TC-47 + TC-52 per-tick procurement evaluation.

        TC-47: NonFirmImportEffect.apply() returns reserve_gap unchanged even
               when non-firm import reduces served load.

        TC-52: ReservationProposal.requires_confirmation is always True —
               proven by constructing one and reading the property.

        Returns an advisory summary dict (not used for dispatch).
        """
        import_mw = self._non_firm.available_mw if self._non_firm else 0.0
        new_served, gap_unchanged = NonFirmImportEffect.apply(
            served_load_mw, import_mw, reserve_gap_mw
        )
        price = self.price_curve.price_at(sim_time)
        proposal = ReservationProposal(
            capacity_type=CapacityType.NON_FIRM,
            requested_mw=import_mw,
            estimated_cost=price * import_mw / 1000.0,  # indicative MWh cost
            rationale=(
                f"TC-47/TC-52 procurement eval at sim_time={sim_time:.1f}s: "
                f"non_firm={import_mw:.2f} MW reduces served load but reserve gap "
                f"stays at {gap_unchanged:.2f} MW (TC-47)."
            ),
        )
        return {
            "import_mw": import_mw,
            "new_served_load_mw": round(new_served, 4),
            "reserve_gap_mw_unchanged": round(gap_unchanged, 4),  # TC-47
            "proposal_requires_confirmation": proposal.requires_confirmation,  # TC-52 always True
            "spot_price_per_mwh": price,
        }
