"""
Site seed configuration for the renewable-supply console.

These values close the §7.1.1 residual item ("default module/array sizing and an
irradiance-to-MW conversion for simulator seed configuration are not fixed here")
for simulator purposes only. They are defensible defaults, not measured
design-partner data, and every one of them is expected to be overridden per site.

Any change here must be mirrored in the CFG object inside the solar-console HTML,
and tests/test_solar_model.py will fail if the seed no longer reproduces the
reference operating point.

Seed topology (spec §3)
------------------------
  20 banks × 0.25 MW AC across 4 feeders (5 banks each)
  Plant rated AC = 5.00 MW                 (unchanged from original)
  Plant rated DC = 6.50 MWp (DC/AC 1.30)  (unchanged)
  Strings per bank = 6                     (120 strings plant-wide, unchanged)
  Seed output ≈ 4.29 MW                    (unchanged)
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Turbine:
    id: str
    mw: float
    online: bool
    ramp_mw_per_s: float = 0.2  # MVP default per §7.1


@dataclass
class SiteConfig:
    site_id: str = "datacenter-01"

    # --- PV plant -------------------------------------------------------
    # Spec §3: 20 banks × 0.25 MW across 4 feeders
    banks: int = 20
    bank_rated_ac_mw: float = 0.25
    feeder_ids: List[str] = field(
        default_factory=lambda: ["fdr-A", "fdr-B", "fdr-C", "fdr-D"]
    )
    dcac_ratio: float = 1.30
    strings_per_bank: int = 6          # 120 strings plant-wide
    mount: str = "fixed"

    # Irradiance-to-MW conversion terms (§7.1.1 residual)
    temp_derate_per_k: float = 0.0038  # fraction of rated per K above 25 °C
    temp_ref_c: float = 25.0
    soiling_loss: float = 0.030
    cloud_ramp_bound_mw_per_s: float = 0.42  # plant-wide, bounded by array diversity

    # --- dispatchable fleet ---------------------------------------------
    turbines: List[Turbine] = field(default_factory=lambda: [
        Turbine("gt-01", 5.0, True),
        Turbine("gt-02", 5.0, True),
        Turbine("gt-03", 5.0, False),
    ])
    bess_rated_mw: float = 10.0
    bess_mwh: float = 5.0
    bess_soc: float = 0.82
    bess_usable_fraction: float = 0.90
    anchor_reserve_mw: float = 2.0  # §7.1.2 grid-forming duty, islanded
    islanded: bool = True

    # --- load ------------------------------------------------------------
    p_compute_seed_mw: float = 10.40
    pue_cooling_fraction: float = 0.158  # delayed cooling component only (§8)

    # --- initial atmospheric state ---------------------------------------
    poa_seed: float = 969.0        # W/m² plane-of-array, measured
    clear_sky_poa_seed: float = 1005.0
    module_temp_c_seed: float = 48.0

    # --- derived properties ---------------------------------------------

    @property
    def plant_rated_ac_mw(self) -> float:
        return self.banks * self.bank_rated_ac_mw

    @property
    def plant_rated_dc_mwp(self) -> float:
        return self.plant_rated_ac_mw * self.dcac_ratio

    @property
    def banks_per_feeder(self) -> int:
        """Number of banks on each feeder (assumes equal split)."""
        return self.banks // len(self.feeder_ids) if self.feeder_ids else self.banks

    # --- backward-compat aliases (old 5-block API) ----------------------
    @property
    def blocks(self) -> int:
        return self.banks

    @property
    def block_rated_ac_mw(self) -> float:
        return self.bank_rated_ac_mw

    @property
    def strings_per_block(self) -> int:
        return self.strings_per_bank


CONFIG = SiteConfig()
