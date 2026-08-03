"""
gridsignal_logger.py
====================
Logs real-time statistics for five GridSignal subsystems to a CSV file
at 1-second intervals.

Systems logged
--------------
  Gas Turbine Fleet   — aggregate power output (MW), heat rate (BTU/kWh), exhaust temp (°C)
  Solar PV            — array output (MW), irradiance fraction (0–1), cell temp (°C)
  Battery (BESS)      — state of charge (%), charge/discharge rate (MW), voltage (V)
  Compute Racks       — CPU load (%), memory utilisation (%), inlet air temp (°C)
  Cooling Plant       — chilled water supply temp (°C), pump flow (L/s), COP

Usage
-----
  python gridsignal_logger.py                  # runs until Ctrl-C
  python gridsignal_logger.py --rows 30        # stops after 30 rows
  python gridsignal_logger.py --out my.csv     # custom output file

Dependencies
------------
  pip install pandas
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# CSV schema
# Column order is the source of truth — keep in sync with _row_dict() below.
# ---------------------------------------------------------------------------
CSV_COLUMNS: list[str] = [
    "timestamp",
    # Gas Turbine Fleet
    "gt_power_mw",
    "gt_heat_rate_btu_kwh",
    "gt_exhaust_temp_c",
    # Solar PV
    "solar_output_mw",
    "solar_irradiance_fraction",
    "solar_cell_temp_c",
    # Battery Energy Storage (BESS)
    "bess_soc_pct",
    "bess_power_mw",          # positive = discharging, negative = charging
    "bess_terminal_voltage_v",
    # Compute Racks
    "compute_cpu_load_pct",
    "compute_mem_util_pct",
    "compute_inlet_temp_c",
    # Cooling Plant
    "cooling_chws_temp_c",    # chilled water supply temperature
    "cooling_pump_flow_ls",   # litres per second
    "cooling_cop",            # coefficient of performance
]


# ---------------------------------------------------------------------------
# Physics-inspired simulation helpers
# ---------------------------------------------------------------------------

class _FirstOrderFilter:
    """Simple IIR low-pass filter that adds inertia to a simulated signal."""

    def __init__(self, initial: float, tau: float = 5.0) -> None:
        self.value = initial
        self.tau   = tau       # time constant in seconds

    def step(self, target: float, dt: float = 1.0) -> float:
        """Advance the filter by `dt` seconds toward `target`."""
        alpha = 1.0 - math.exp(-dt / self.tau)
        self.value += alpha * (target - self.value)
        return round(self.value, 3)


class SimulatedGrid:
    """
    Maintains state for all five subsystems and advances them each tick.

    Each subsystem uses a random walk inside physical bounds so that
    successive rows look like real telemetry rather than independent samples.
    """

    # ---- Gas Turbine: 4-unit fleet, ~120 MW per unit rated ---------------
    GT_RATED_MW   = 480.0
    GT_MIN_MW     = 200.0
    GT_RAMP_MW_S  = 4.0       # max ramp rate, MW per second

    # ---- Solar PV: 200 MW DC nameplate ------------------------------------
    SOLAR_RATED_MW  = 200.0

    # ---- BESS: 50 MW / 200 MWh ---------------------------------------------
    BESS_RATED_MW   = 50.0
    BESS_MAX_SOC    = 98.0
    BESS_MIN_SOC    = 5.0
    BESS_RATED_V    = 1500.0   # nominal DC link voltage

    # ---- Compute Racks: ~5 MW total load -----------------------------------
    COMPUTE_LOAD_PCT_MIN = 40.0
    COMPUTE_LOAD_PCT_MAX = 98.0

    # ---- Cooling: 10 chiller units, 6 MW_th each ---------------------------
    COOLING_CHWS_SETPOINT = 7.0    # °C chilled-water supply setpoint
    COOLING_MAX_FLOW_LS   = 800.0  # litres per second

    def __init__(self) -> None:
        # Gas turbines — start near 60 % load
        self._gt_mw    = _FirstOrderFilter(280.0, tau=8.0)
        self._gt_noise = 0.0

        # Solar — current irradiance fraction (changes slowly, ≈ cloud cover)
        self._solar_frac = _FirstOrderFilter(0.6, tau=30.0)

        # BESS
        self._soc     = 72.0    # start at 72 % SoC
        self._bess_mw = _FirstOrderFilter(0.0, tau=3.0)

        # Compute load
        self._cpu  = _FirstOrderFilter(65.0, tau=15.0)
        self._mem  = _FirstOrderFilter(55.0, tau=60.0)

        # Cooling — chilled water supply temp has thermal inertia
        self._chws = _FirstOrderFilter(self.COOLING_CHWS_SETPOINT + 1.0, tau=20.0)

        # Tick counter (used for pseudo-diurnal solar curve)
        self._tick = 0

    # ------------------------------------------------------------------
    def tick(self) -> dict:
        """Advance all subsystems by 1 second and return a metric dict."""
        self._tick += 1
        t = self._tick

        # -- Gas Turbine --------------------------------------------------
        gt_target  = self.GT_MIN_MW + random.gauss(0, self.GT_RAMP_MW_S * 3)
        gt_target  = max(self.GT_MIN_MW,
                         min(self.GT_RATED_MW,
                             self._gt_mw.value + gt_target * 0.1))
        gt_mw      = self._gt_mw.step(gt_target)
        gt_load_f  = gt_mw / self.GT_RATED_MW
        # Heat rate degrades at partial load (higher = less efficient)
        gt_hr      = round(9800 + (1 - gt_load_f) * 2200 + random.gauss(0, 30), 1)
        gt_exhaust = round(520 + gt_load_f * 80 + random.gauss(0, 2), 1)

        # -- Solar PV -----------------------------------------------------
        # Slow-moving irradiance target (simulates cloud transients)
        sol_target  = max(0.0, min(1.0, self._solar_frac.value
                                        + random.gauss(0, 0.02)))
        sol_frac    = self._solar_frac.step(sol_target, dt=1.0)
        sol_mw      = round(self.SOLAR_RATED_MW * sol_frac
                            + random.gauss(0, 0.5), 2)
        sol_mw      = max(0.0, sol_mw)
        # Cell temperature: ambient (~25 °C) + irradiance-driven rise
        sol_cell_t  = round(25.0 + sol_frac * 30.0 + random.gauss(0, 0.3), 1)

        # -- BESS ---------------------------------------------------------
        # Dispatch: BESS smooths the gap between load and (GT + solar)
        demand_mw   = 300.0 + random.gauss(0, 10)   # simulated demand
        net_gap     = demand_mw - gt_mw - sol_mw
        bess_target = max(-self.BESS_RATED_MW,
                          min(self.BESS_RATED_MW, net_gap))
        bess_mw     = self._bess_mw.step(bess_target)
        # Update SoC: positive bess_mw = discharge, negative = charge
        self._soc  -= bess_mw / 3600.0 * 100.0 / 200.0  # 200 MWh battery
        self._soc   = max(self.BESS_MIN_SOC, min(self.BESS_MAX_SOC, self._soc))
        # Terminal voltage sags slightly at high current
        soc_f       = self._soc / 100.0
        bess_v      = round(self.BESS_RATED_V * (0.90 + 0.12 * soc_f)
                            + random.gauss(0, 1.0), 1)

        # -- Compute Racks ------------------------------------------------
        cpu_target  = max(self.COMPUTE_LOAD_PCT_MIN,
                          min(self.COMPUTE_LOAD_PCT_MAX,
                              self._cpu.value + random.gauss(0, 3)))
        cpu_load    = self._cpu.step(cpu_target)
        mem_target  = max(30.0, min(95.0, self._mem.value + random.gauss(0, 1)))
        mem_util    = self._mem.step(mem_target)
        # Inlet temperature rises with CPU load
        inlet_temp  = round(18.0 + cpu_load * 0.07 + random.gauss(0, 0.2), 1)

        # -- Cooling Plant ------------------------------------------------
        # Setpoint deviation caused by compute heat load
        heat_kw     = cpu_load * 50.0   # rough compute → thermal load proxy
        chws_target = self.COOLING_CHWS_SETPOINT + heat_kw / 20000.0 * 2.0
        chws_temp   = self._chws.step(chws_target)
        # Pump speed proportional to heat load
        flow        = round(self.COOLING_MAX_FLOW_LS * (0.4 + heat_kw / 5000.0 * 0.6)
                            + random.gauss(0, 2), 1)
        flow        = max(0.0, min(self.COOLING_MAX_FLOW_LS, flow))
        # COP: refrigeration efficiency (typical range 3–5)
        cop         = round(4.5 - (chws_temp - self.COOLING_CHWS_SETPOINT) * 0.3
                            + random.gauss(0, 0.05), 2)

        return {
            "timestamp":                 datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "gt_power_mw":               round(gt_mw, 2),
            "gt_heat_rate_btu_kwh":      gt_hr,
            "gt_exhaust_temp_c":         gt_exhaust,
            "solar_output_mw":           sol_mw,
            "solar_irradiance_fraction": round(sol_frac, 4),
            "solar_cell_temp_c":         sol_cell_t,
            "bess_soc_pct":              round(self._soc, 2),
            "bess_power_mw":             round(bess_mw, 2),
            "bess_terminal_voltage_v":   bess_v,
            "compute_cpu_load_pct":      round(cpu_load, 1),
            "compute_mem_util_pct":      round(mem_util, 1),
            "compute_inlet_temp_c":      inlet_temp,
            "cooling_chws_temp_c":       round(chws_temp, 2),
            "cooling_pump_flow_ls":      flow,
            "cooling_cop":               cop,
        }


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

def open_csv(path: Path) -> csv.DictWriter:
    """
    Open (or create) the CSV file and write the header row.

    If the file already exists, it is overwritten so sample runs start clean.
    Raises OSError if the directory is not writable.
    """
    fh = path.open("w", newline="", encoding="utf-8")
    # QUOTE_NONNUMERIC forces string fields (including timestamp) to be quoted.
    # Excel/Sheets then treats them as plain text and shows the full
    # HH:MM:SS value rather than silently dropping the seconds.
    writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS,
                            quoting=csv.QUOTE_NONNUMERIC)
    writer.writeheader()
    fh.flush()
    return writer, fh


def log_row(writer: csv.DictWriter, fh, row: dict) -> None:
    """Append one row to the CSV and flush immediately so data is not lost
    if the process is interrupted."""
    writer.writerow(row)
    fh.flush()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="GridSignal subsystem telemetry logger")
    parser.add_argument("--out",  default="system_stats.csv",
                        help="Output CSV file path (default: system_stats.csv)")
    parser.add_argument("--rows", type=int, default=0,
                        help="Stop after N rows (0 = run until Ctrl-C)")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="Seconds between rows (default: 1.0; use 0.05 for fast test mode)")
    args = parser.parse_args()

    output_path = Path(args.out)

    # --- open CSV ---------------------------------------------------------
    try:
        writer, fh = open_csv(output_path)
    except OSError as exc:
        print(f"[ERROR] Cannot open {output_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    sim   = SimulatedGrid()
    count = 0

    print(f"Logging to '{output_path}' every 1 second.  Press Ctrl-C to stop.")
    print(f"{'Tick':<6} {'Timestamp':<21} {'GT MW':>8} {'Solar MW':>9} "
          f"{'BESS SoC':>9} {'CPU %':>7} {'CHWS °C':>8}")
    print("-" * 72)

    try:
        while True:
            # Collect data — wrap in try/except so a transient error
            # doesn't crash the whole logger
            try:
                row = sim.tick()
            except Exception as exc:          # pragma: no cover
                print(f"[WARN] Simulation error at tick {count}: {exc}", file=sys.stderr)
                time.sleep(1)
                continue

            # Write to CSV
            try:
                log_row(writer, fh, row)
            except OSError as exc:
                print(f"[ERROR] Write failed at tick {count}: {exc}", file=sys.stderr)
                # Try to re-open the file (e.g. if it was deleted under us)
                try:
                    fh.close()
                    writer, fh = open_csv(output_path)
                    log_row(writer, fh, row)
                except OSError as exc2:
                    print(f"[FATAL] Cannot recover file: {exc2}", file=sys.stderr)
                    sys.exit(1)

            count += 1

            # Progress line
            print(f"{count:<6} {row['timestamp']:<21} "
                  f"{row['gt_power_mw']:>8.1f} "
                  f"{row['solar_output_mw']:>9.1f} "
                  f"{row['bess_soc_pct']:>8.1f}% "
                  f"{row['compute_cpu_load_pct']:>7.1f} "
                  f"{row['cooling_chws_temp_c']:>8.2f}")

            if args.rows and count >= args.rows:
                print(f"\nReached {args.rows} rows — stopping.")
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\nInterrupted after {count} row(s).")
    finally:
        fh.close()
        print(f"Saved to '{output_path}'.")


if __name__ == "__main__":
    main()
