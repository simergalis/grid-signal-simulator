"""
Renewable-supply simulation and reserve arithmetic.

This module is the reference implementation. The browser console mirrors these
formulas for offline rendering, but whenever the server is reachable the client
consumes the scalars computed here rather than recomputing them, so there is
exactly one authority while the app is running.

Spec anchors:
  §7.1.1  non-dispatchable supply, net dispatch requirement
  §7.1.2  grid-forming anchor constraint on BESS bridging
  §7.2    dispatch arbitration, step 4 insufficient-reserve check
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from renewable.config import CONFIG, SiteConfig


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

@dataclass
class BlockState:
    id: str
    rated_mw: float
    state: str = "ok"          # ok | fault
    derate: float = 1.0        # re-rating applied per §27.4, not exclusion
    strings_out: int = 0
    inverter_temp_c: float = 41.0
    soil_bias: float = 1.0     # per-block soiling/mismatch spread


@dataclass
class PlantState:
    poa: float
    clear_sky_poa: float
    module_temp_c: float
    soiling: float
    cloud_factor: float = 1.0
    cloud_target: float = 1.0
    p_compute_mw: float = 0.0
    p_compute_target_mw: float = 0.0
    bess_soc: float = 0.82
    blocks: List[BlockState] = field(default_factory=list)
    t: int = 0


@dataclass
class ReserveResult:
    """Outcome of the §7.2 step 4 check for a single contingency."""
    delta_p_mw: float
    dt_lead_s: float
    ramp_time_s: float
    gap_s: float
    peak_shortfall_mw: float
    bridging_available_mw: float
    energy_needed_mwh: float
    sustainable_duration_s: float
    passes: bool
    deficit_mw: float
    deficit_s: float

    def to_dict(self) -> Dict:
        """JSON-safe form.

        ramp_time_s and sustainable_duration_s are legitimately infinite when no
        turbine is online or when the shortfall is zero. Infinity is not valid
        JSON, so it is emitted as null and the console renders it as the
        unbounded symbol rather than as a number.
        """
        return {k: (None if isinstance(v, float) and not math.isfinite(v) else v)
                for k, v in asdict(self).items()}


# ---------------------------------------------------------------------------
# physics
# ---------------------------------------------------------------------------

def temp_derate(cfg: SiteConfig, module_temp_c: float) -> float:
    return 1.0 - cfg.temp_derate_per_k * max(0.0, module_temp_c - cfg.temp_ref_c)


def block_output_mw(cfg: SiteConfig, st: PlantState, b: BlockState) -> float:
    """Instantaneous AC output of one inverter block, clipped at nameplate."""
    if b.state == "fault":
        return 0.0
    irradiance = st.poa * st.cloud_factor / 1000.0
    string_loss = 1.0 - (b.strings_out / cfg.strings_per_block)
    raw = (b.rated_mw
           * irradiance
           * (1.0 - st.soiling)
           * temp_derate(cfg, st.module_temp_c)
           * string_loss
           * b.derate
           * b.soil_bias)
    return max(0.0, min(raw, b.rated_mw))


def clear_sky_block_mw(cfg: SiteConfig, st: PlantState, b: BlockState) -> float:
    """Expected output under the clear-sky model. Excludes soiling and string
    faults deliberately: performance ratio must be able to expose them."""
    irradiance = st.clear_sky_poa / 1000.0
    return max(0.0, min(b.rated_mw * irradiance * temp_derate(cfg, st.module_temp_c),
                        b.rated_mw))


def p_renewable_mw(cfg: SiteConfig, st: PlantState) -> float:
    return sum(block_output_mw(cfg, st, b) for b in st.blocks)


def p_clear_sky_mw(cfg: SiteConfig, st: PlantState) -> float:
    return sum(clear_sky_block_mw(cfg, st, b) for b in st.blocks)


def p_cooling_mw(cfg: SiteConfig, st: PlantState) -> float:
    return st.p_compute_mw * cfg.pue_cooling_fraction


def p_total_mw(cfg: SiteConfig, st: PlantState) -> float:
    return st.p_compute_mw + p_cooling_mw(cfg, st)


def p_dispatch_required_mw(cfg: SiteConfig, st: PlantState) -> float:
    """§7.1.1  P_dispatch_required(t) = P_total(t) - P_renewable(t)"""
    return p_total_mw(cfg, st) - p_renewable_mw(cfg, st)


def largest_block_mw(cfg: SiteConfig, st: PlantState) -> float:
    """The N-1 contingency: the single largest block currently producing."""
    outs = [block_output_mw(cfg, st, b) for b in st.blocks]
    return max(outs) if outs else 0.0


# ---------------------------------------------------------------------------
# fleet capability
# ---------------------------------------------------------------------------

def fleet_ramp_mw_per_s(cfg: SiteConfig) -> float:
    return sum(t.ramp_mw_per_s for t in cfg.turbines if t.online)


def bess_bridging_mw(cfg: SiteConfig, st: PlantState) -> float:
    """§7.1.2  BESS_bridging_available(t)
              = min(rated, usable SoC) - P_anchor_reserve

    The anchor reserve is withheld before anything else, which is why usable
    bridging falls faster than state of charge does.
    """
    anchor = cfg.anchor_reserve_mw if cfg.islanded else 0.0
    return max(0.0, min(cfg.bess_rated_mw, cfg.bess_rated_mw * st.bess_soc) - anchor)


def bess_usable_mwh(cfg: SiteConfig, st: PlantState) -> float:
    return cfg.bess_mwh * st.bess_soc * cfg.bess_usable_fraction


# ---------------------------------------------------------------------------
# reserve check
# ---------------------------------------------------------------------------

def reserve_check(cfg: SiteConfig, st: PlantState,
                  delta_p_mw: float, dt_lead_s: float = 0.0) -> ReserveResult:
    """§7.2 step 4.

    A supply-side loss carries dt_lead = 0: there is no advance signal for an
    inverter trip or a severed feeder. A compute step-load carries the 30-60 s
    of queue warning the product exists to exploit. A compound event carries
    the shorter of the two, which is zero.

    The shortfall the BESS must cover declines linearly as the turbines ramp;
    it is not a flat draw. Sustainable duration is compared as a duration
    against the gap window, never as an energy-like product.
    """
    r = fleet_ramp_mw_per_s(cfg)
    ramp_time = delta_p_mw / r if r > 0 else math.inf
    gap = max(0.0, ramp_time - dt_lead_s)
    peak = max(0.0, delta_p_mw - r * dt_lead_s)

    bridging = bess_bridging_mw(cfg, st)
    usable = bess_usable_mwh(cfg, st)

    # triangle under the declining shortfall
    energy_needed = (peak * gap / 2.0) / 3600.0 if math.isfinite(gap) else math.inf
    sustainable_s = (usable / peak) * 3600.0 if peak > 0 else math.inf

    power_ok = peak <= bridging
    energy_ok = energy_needed <= usable

    return ReserveResult(
        delta_p_mw=delta_p_mw,
        dt_lead_s=dt_lead_s,
        ramp_time_s=ramp_time,
        gap_s=gap,
        peak_shortfall_mw=peak,
        bridging_available_mw=bridging,
        energy_needed_mwh=energy_needed,
        sustainable_duration_s=sustainable_s,
        passes=power_ok and energy_ok,
        deficit_mw=max(0.0, peak - bridging),
        deficit_s=0.0 if energy_ok else max(0.0, gap - sustainable_s),
    )


# ---------------------------------------------------------------------------
# simulator
# ---------------------------------------------------------------------------

class SolarSim:
    """Tick-driven simulation of the PV plant and its supply exposure.

    One instance per process. Ticked at 1 Hz from a background task in
    api/app.py lifespan.
    """

    def __init__(self, cfg: SiteConfig = CONFIG, seed: Optional[int] = None):
        self.cfg = cfg
        self.rng = random.Random(seed)
        self.log: List[Dict] = []
        self.state = self._seed_state()
        self._log("Session started. Seed: clear afternoon, %d blocks online, %s."
                  % (cfg.blocks,
                     "islanded with BESS as grid-forming anchor" if cfg.islanded
                     else "grid-connected"), "")

    # -- lifecycle ------------------------------------------------------
    def _seed_state(self) -> PlantState:
        cfg = self.cfg
        blocks = []
        mid = (cfg.blocks - 1) / 2.0
        for i in range(cfg.blocks):
            blocks.append(BlockState(
                id="inv-%02d" % (i + 1),
                rated_mw=cfg.block_rated_ac_mw,
                inverter_temp_c=41.0 + i,
                soil_bias=1.0 + (i - mid) * 0.006,
            ))
        return PlantState(
            poa=cfg.poa_seed,
            clear_sky_poa=cfg.clear_sky_poa_seed,
            module_temp_c=cfg.module_temp_c_seed,
            soiling=cfg.soiling_loss,
            p_compute_mw=cfg.p_compute_seed_mw,
            p_compute_target_mw=cfg.p_compute_seed_mw,
            bess_soc=cfg.bess_soc,
            blocks=blocks,
        )

    def reset(self) -> None:
        for t in self.cfg.turbines:
            t.online = t.id in ("gt-01", "gt-02")
        self.state = self._seed_state()
        self._log("Reset to nominal seed state.", "")

    # -- tick -----------------------------------------------------------
    def tick(self) -> None:
        st, cfg, rng = self.state, self.cfg, self.rng
        st.t += 1

        st.cloud_factor += (st.cloud_target - st.cloud_factor) * 0.12
        if abs(st.cloud_target - st.cloud_factor) < 0.004:
            st.cloud_factor = st.cloud_target

        st.p_compute_mw += (st.p_compute_target_mw - st.p_compute_mw) * 0.18

        # gentle afternoon decline plus pyranometer noise
        st.poa = _clamp(st.poa - 0.06 + (rng.random() - 0.5) * 1.6, 300, 1050)
        st.clear_sky_poa = _clamp(st.clear_sky_poa - 0.06, 320, 1100)
        st.module_temp_c = _clamp(
            st.module_temp_c + (0.01 if st.cloud_factor > 0.9 else -0.05)
            + (rng.random() - 0.5) * 0.1, 20, 70)
        for b in st.blocks:
            b.inverter_temp_c = _clamp(b.inverter_temp_c + (rng.random() - 0.5) * 0.3, 25, 85)

    # -- stressors ------------------------------------------------------
    def inject(self, kind: str) -> Dict:
        st, cfg = self.state, self.cfg

        if kind == "cloud":
            st.cloud_target = 0.42
            self._log("Cloud transient injected — POA falling to ~42%%. Plant-wide ramp "
                      "bounded at %.2f MW/s by array diversity; this is not a step change."
                      % cfg.cloud_ramp_bound_mw_per_s, "warn")

        elif kind == "cloud_clear":
            st.cloud_target = 1.0
            self._log("Cloud field cleared. Output recovering.", "")

        elif kind == "trip":
            live = [b for b in st.blocks if b.state != "fault"]
            if not live:
                self._log("All blocks already offline.", "bad")
            else:
                b = self.rng.choice(live)
                b.state = "fault"
                self._log("%s tripped — DC arc-fault. %.2f MW step change, "
                          "Δt_lead = 0. BESS bridging engaged." % (b.id, b.rated_mw), "bad")

        elif kind == "poi":
            for b in st.blocks:
                b.state = "fault"
            self._log("POI breaker open — entire array disconnected. This is the sizing "
                      "contingency: a step change with no advance signal.", "bad")

        elif kind == "soil":
            st.soiling = _clamp(st.soiling + 0.035, 0, 0.25)
            self.rng.choice(st.blocks).strings_out += 2
            self._log("Soiling stepped to %.1f%% and two strings opened. Degraded, not "
                      "unavailable — the block is counted at re-rated capability (§27.4)."
                      % (st.soiling * 100), "warn")

        elif kind == "spike":
            st.p_compute_target_mw = st.p_compute_mw + 6.0
            self._log("Compute step-load +6.00 MW staged from queue telemetry. "
                      "Δt_lead = 30 s on this term only.", "warn")

        elif kind == "turbine":
            on = [t for t in cfg.turbines if t.online]
            if len(on) <= 1:
                self._log("Cannot take the last turbine offline while islanded.", "bad")
            else:
                on[-1].online = False
                self._log("%s offline. Fleet ramp now %.2f MW/s — every gap window "
                          "lengthens." % (on[-1].id, fleet_ramp_mw_per_s(cfg)), "bad")

        elif kind == "bess":
            st.bess_soc = 0.30 if st.bess_soc > 0.4 else cfg.bess_soc
            self._log("BESS state of charge set to %.0f%%. Anchor-adjusted bridging is now "
                      "%.2f MW — the anchor duty is withheld first, so usable bridging "
                      "falls faster than SoC."
                      % (st.bess_soc * 100, bess_bridging_mw(cfg, st)),
                      "bad" if st.bess_soc < 0.4 else "")

        elif kind == "reset":
            self.reset()

        else:
            return {"ok": False, "error": "unknown stressor: %s" % kind}

        return {"ok": True, "kind": kind}

    # -- snapshot -------------------------------------------------------
    def snapshot(self) -> Dict:
        cfg, st = self.cfg, self.state
        solar = p_renewable_mw(cfg, st)
        clear_sky = p_clear_sky_mw(cfg, st)
        total = p_total_mw(cfg, st)
        n1 = largest_block_mw(cfg, st)

        rc_plant = reserve_check(cfg, st, solar, 0.0)
        rc_n1 = reserve_check(cfg, st, n1, 0.0)
        rc_compound = reserve_check(cfg, st, solar + 6.0, 0.0)

        return {
            "t": st.t,
            "wall_clock": time.strftime("%H:%M:%S"),
            "site": {
                "id": cfg.site_id,
                "islanded": cfg.islanded,
                "plant_rated_ac_mw": cfg.plant_rated_ac_mw,
                "plant_rated_dc_mwp": cfg.plant_rated_dc_mwp,
                "blocks": cfg.blocks,
                "block_rated_ac_mw": cfg.block_rated_ac_mw,
                "dcac_ratio": cfg.dcac_ratio,
                "strings_per_block": cfg.strings_per_block,
                "mount": cfg.mount,
                "cloud_ramp_bound_mw_per_s": cfg.cloud_ramp_bound_mw_per_s,
                "bess_rated_mw": cfg.bess_rated_mw,
                "bess_mwh": cfg.bess_mwh,
                "anchor_reserve_mw": cfg.anchor_reserve_mw,
            },
            "atmosphere": {
                "poa": st.poa * st.cloud_factor,
                "poa_clear_sky": st.clear_sky_poa,
                "cloud_factor": st.cloud_factor,
                "module_temp_c": st.module_temp_c,
                "soiling": st.soiling,
            },
            "power": {
                "p_renewable_mw": solar,
                "p_clear_sky_mw": clear_sky,
                "performance_ratio": (solar / clear_sky * 100.0) if clear_sky else 0.0,
                "p_compute_mw": st.p_compute_mw,
                "p_cooling_mw": p_cooling_mw(cfg, st),
                "p_total_mw": total,
                "p_dispatch_required_mw": p_dispatch_required_mw(cfg, st),
                "share_of_site_draw_pct": (solar / total * 100.0) if total else 0.0,
                "clipping": solar >= cfg.plant_rated_ac_mw * 0.995,
            },
            "fleet": {
                "turbines": [{"id": t.id, "mw": t.mw, "online": t.online,
                              "ramp_mw_per_s": t.ramp_mw_per_s} for t in cfg.turbines],
                "fleet_ramp_mw_per_s": fleet_ramp_mw_per_s(cfg),
                "bess_soc": st.bess_soc,
                "bess_bridging_mw": bess_bridging_mw(cfg, st),
                "bess_usable_mwh": bess_usable_mwh(cfg, st),
            },
            "blocks": [{
                "id": b.id,
                "state": ("fault" if b.state == "fault"
                          else "derated" if (b.derate < 1.0 or b.strings_out > 0)
                          else "ok"),
                "rated_mw": b.rated_mw,
                "output_mw": block_output_mw(cfg, st, b),
                "expected_mw": clear_sky_block_mw(cfg, st, b),
                "strings_out": b.strings_out,
                "strings_total": cfg.strings_per_block,
                "inverter_temp_c": b.inverter_temp_c,
            } for b in st.blocks],
            "exposure": {
                "n1_block_mw": n1,
                "plant_loss_mw": solar,
                "cloud_ramp_mw_per_s": cfg.cloud_ramp_bound_mw_per_s,
            },
            "reserve": {
                "n1": rc_n1.to_dict(),
                "plant": rc_plant.to_dict(),
                "compound": rc_compound.to_dict(),
            },
            "log": self.log[:40],
        }

    # -- internals ------------------------------------------------------
    def _log(self, msg: str, kind: str = "") -> None:
        self.log.insert(0, {"ts": time.strftime("%H:%M:%S"), "msg": msg, "kind": kind})
        del self.log[60:]


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)
