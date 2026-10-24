# Opt-in operating-cost accounting (DR D6-F)

`operating_cost_inputs` is an optional scenario-level accounting block. It is
consumed after a run and never participates in dispatch, commitment, reserve
calculation, or the simulator's existing `cost_breakdown`. If the block is
absent, the `operating_cost` section is omitted and existing cost and physics
outputs remain unchanged.

Every configured input requires its own `*_provenance` string. An unset price
is represented by a null line amount, not by an inferred price. The separate
`operating_cost` output contains each line's quantity, unit, unit price,
provenance, amount, and any conversion note. Its total is the sum of
non-null line amounts; `total_includes` and `total_excludes` identify the
accounted and excluded items.

## Inputs and formulas

| Input | Formula / quantity | Provenance status for the S10 candidate |
|---|---|---|
| `gas_price_usd_per_mmbtu`, `gas_price_basis` | Turbine fuel MMBtu, converted per unit to the configured price basis, times price. | CITED: EIA industrial natural-gas price and EIA heat-content data (sources below). |
| `diesel_price_usd_per_gal` | Measured diesel gallons times price. | CITED: EIA U.S. on-highway No. 2 diesel, week of 2026-10-19; includes road taxes, which off-road fuel may not incur. |
| `turbine_variable_om_usd_per_mwh` | Integrated measured turbine MWh times price. | CITED proxy: EIA AEO2025, Table 1-2, Case 3, 4 × 54 MW simple-cycle aeroderivative CTs; larger units than S10. |
| `turbine_fixed_om_usd_per_kw_yr` | Rated turbine kW × run hours / 8,760 × annual price. | CITED proxy: same EIA AEO2025 case, 2023 USD. |
| `turbine_start_cost_usd_per_start` | Completed-run start count times non-fuel price. Start fuel is already included in turbine fuel and is not counted again here. | Null for S10; no cited non-fuel start-cost source. |
| `bess_degradation_usd_per_mwh` | Absolute signed AC-side BESS output integrated over the run (charge plus discharge) times price. | Null for S10; no cited degradation-cost source. The AC-throughput quantity convention is PROPOSED_HERE. |
| `unserved_energy_value_usd_per_mwh` | D7 unserved MWh times price. | Null for S10; no cited value-of-lost-load source. |
| `currency_year` | Descriptive year/basis for supplied prices; no automatic inflation normalization. | Mixed: 2023 USD O&M and 2026 USD fuel prices. |

The gas price recorded for S10 is `$5.1407907425/MMBtu HHV`: the EIA Aug-2025–Jul-2026 mean `$5.331/Mcf` divided by EIA's 2025 average heat content `1,037 Btu/cf` (`1.037 MMBtu/Mcf`). July-2026 sensitivity is `$4.58/Mcf ÷ 1.037 = $4.4165863/MMBtu HHV`. The generated candidate records both its price and provenance.

The S10 turbine curve uses an assumed LHV basis because the Siemens brochure's
extracted SGT-400 specification does not state LHV/HHV. When a fuel basis and
price basis differ, the implementation uses `1.108 MMBtu(HHV)/MMBtu(LHV)`,
PROPOSED_HERE, based on the natural-gas LHV/HHV distinction in the DOE Hydrogen
Analysis Resource Center. The factor and conversion note are returned on the
gas-fuel line.

## S10 fuel curve

The generator's opt-in `siemens-sgt-400-proxy` fuel option records the full-load
source and the curve provenance on each generated turbine:

- CITED full-load point: Siemens Energy Gas Turbine Portfolio Brochure 2024,
  SGT-400 15 MW simple-cycle configuration at 14.3 MW(e), 10,103 kJ/kWh,
  and 35.6% gross efficiency. The basis is not stated by the OEM; S10
  equipment remains unknown, so this is labelled a 15 MW-class proxy.
- Conversion: `10,103 × 0.947817 = 9,575.795151 Btu/kWh`, rounded to
  `9,576 Btu/kWh`.
- PROPOSED_HERE part-load points: the in-repository aeroderivative curve
  `11,000 / 9,800 / 9,000 / 8,500 Btu/kWh` at `25 / 50 / 75 / 100%`,
  scaled by `9,576 / 8,500 = 1.1265882353`; rounded values are
  `12,392 / 11,041 / 10,139 / 9,576 Btu/kWh`.
- PROPOSED_HERE unscaled defaults: no-load `1.20 MMBtu/h`, hot standby
  `0.25 MMBtu/h`, and hot/warm/cold starts `8 / 12 / 20 MMBtu`.

## Cost scope and exclusions

The total is itemized run operating cost for configured inputs, not a complete
customer bill or full lifecycle cost. Grid imports, fuel-cell fuel, solar/PPA
contracts, cooling labor, other site O&M, and any line whose required
quantity or price is null are explicitly excluded. The legacy dispatch
ranking values and §21.2 `cost_breakdown` remain untouched and are never added
to this total.

## Sources

- Siemens Energy, *Gas Turbine Portfolio Brochure 2024*, SGT-400:
  https://assets.siemens-energy.com/dam/d7e01f44-f091-44f2-bf71-b20b010483e1/GT-Portfolio-Brochure-2024__FINAL_Low_Resolution-pdf_Original%20file.pdf
- Siemens Energy, SGT-400 product page:
  https://siemens-energy.com/us/en/home/products-services/product/sgt-400.html
- EIA, U.S. Natural Gas Industrial Price:
  https://www.eia.gov/dnav/ng/hist/n3035us3m.htm
- EIA, average heat content of natural gas:
  https://www.eia.gov/tools/faqs/faq.php?id=45&t=5
- EIA, U.S. on-highway diesel prices:
  https://www.eia.gov/petroleum/gasdiesel/
- EIA, *Capital Cost and Performance Characteristics for Utility Scale Electric
  Power Generating Technologies*, AEO2025, Table 1-2:
  https://www.eia.gov/analysis/studies/powerplants/capitalcost/pdf/capital_cost_AEO2025.pdf
- DOE Hydrogen Analysis Resource Center, lower and higher heating values:
  https://h2tools.org/hyarc/calculator-tools/lower-and-higher-heating-values-fuels
