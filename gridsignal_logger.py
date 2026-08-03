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
    "gt_setpoint_mw",         # dispatch target before ramp filter (§11.3 setpoint split)
    "gt_mode",                # "ramping" | "at_target"
    # Solar PV
    "solar_output_mw",
    "solar_irradiance_fraction",
    "solar_cell_temp_c",
    # Battery Energy Storage (BESS)
    "bess_soc_pct",
    "bess_power_mw",          # positive = discharging, negative = charging
    "bess_terminal_voltage_v",
    "bess_setpoint_mw",       # commanded BESS output before SOC/filter clipping
    # Compute Racks
    "compute_cpu_load_pct",
    "compute_mem_util_pct",
    "compute_inlet_temp_c",
    "compute_load_mw",        # total compute electrical draw (restored field)
    # Cooling Plant
    "cooling_chws_temp_c",    # chilled water supply temperature
    "cooling_pump_flow_ls",   # litres per second
    "cooling_cop",            # coefficient of performance
    # Tier 1 — Power Balance
    "site_total_load_mw",     # total site load measured at PCC (IT + mechanical)
    "it_load_mw",             # IT critical load only
    "mechanical_load_mw",     # cooling, pumps, fans (thermally lagged — §8)
    "grid_import_mw",         # signed: positive = importing, negative = exporting
    "islanded",               # 1 when operating in island mode, 0 = grid-connected
    "balance_residual_mw",    # gen − load − losses; should be ~0; spikes flag bugs
    "binding_constraint",     # "ramp_limit" | "soc_limit" | "none"
    # Forecast / advisory
    "forecast_mw",            # short-horizon site-load forecast (§11.1 aligned)
    # Scheduler diagnostics
    "step_event",             # 1 when a training-step boundary falls in this tick window
    # Run metadata
    "scenario_id",            # scenario name tag
    "rng_seed",               # RNG seed used for this run (reproducibility)
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

    # ---- Compute Racks: 300 MW hyperscale AI cluster -----------------------
    COMPUTE_RATED_MW     = 300.0   # electrical nameplate for the whole cluster
    COMPUTE_LOAD_PCT_MIN = 40.0
    COMPUTE_LOAD_PCT_MAX = 98.0

    # ---- Cooling: scaled for 300 MW IT load --------------------------------
    COOLING_CHWS_SETPOINT = 7.0    # °C chilled-water supply setpoint
    COOLING_MAX_FLOW_LS   = 5000.0 # litres per second (large chilled-water loop)

    # ---- Step-event clock (drives compute load pulses) ---------------------
    STEP_PERIOD_S       = 0.7   # mean training-step period (s)
    STEP_JITTER_S       = 0.05  # straggler / network-contention jitter (std dev)
    STEP_LOAD_BOOST_PCT = 30.0  # CPU % boost during the step computation window
    STEP_DURATION_S     = 0.12  # how long the spike lasts (s)

    # ---- Power balance ------------------------------------------------------
    SITE_LOSS_FACTOR = 0.005       # 0.5 % transmission + distribution losses

    def __init__(self, step_period: float = STEP_PERIOD_S) -> None:
        self._step_period = step_period

        # RNG seed — captured once for reproducibility metadata
        self._rng_seed = random.randint(0, 2**32 - 1)

        # Gas turbines — start near steady-state demand (~240 MW).
        # tau=8 s is the turbine thermal response; the ramp rate is enforced
        # separately via GT_RAMP_MW_S (Issue 2 fix: the filter alone does not
        # limit dP/dt — an explicit clamp is applied each tick in tick()).
        self._gt_mw      = _FirstOrderFilter(240.0, tau=8.0)
        # Exhaust temperature: thermal lag of exhaust plenum (tau = 60 s)
        self._gt_exhaust = _FirstOrderFilter(568.0, tau=60.0)

        # Solar
        self._solar_frac = _FirstOrderFilter(0.6, tau=30.0)

        # BESS — tau=0.3 s so it bridges the 90 MW step within ~3 ticks and
        # the balance_residual does not carry a standing 110 MW error (Issue 1).
        self._soc     = 72.0
        self._bess_mw = _FirstOrderFilter(0.0, tau=0.3)

        # Compute load
        self._cpu = _FirstOrderFilter(65.0, tau=15.0)
        # Memory utilisation: tau=30 s with direct noise so the signal is not
        # constant (Issue: tau=60 s + round-to-1dp → sd=0 regression fix).
        self._mem = _FirstOrderFilter(55.0, tau=30.0)
        # Rack inlet temperature: thermal lag of air mass (tau = 30 s)
        self._inlet_temp = _FirstOrderFilter(25.8, tau=30.0)

        # GPU step-spike low-pass filter — tau = 0.3 s smooths the square-wave
        # boost so there are visible transitional samples instead of infinite
        # dP/dt (Issue 4 fix: tau_gpu smoothing).
        self._cpu_spike = _FirstOrderFilter(0.0, tau=0.3)

        # Cooling thermal lag — §8 / Section 8 specifies a 90 s onset delay
        # before chiller heat rises.  A first-order filter with tau = 90 s
        # approximates that: output < 63 % of steady-state for the first 90 s,
        # and lag-1 autocorrelation ≈ 0.9989 at 10 Hz.
        # This decouples mechanical_load_mw from the instantaneous IT square
        # wave (Issue 3 fix: P_cooling(t) thermal lag).
        self._chiller_heat = _FirstOrderFilter(0.0, tau=90.0)

        # Cooling — chilled water supply temp has thermal inertia
        self._chws = _FirstOrderFilter(self.COOLING_CHWS_SETPOINT + 1.0, tau=20.0)

        # Grid import: PCC meter + grid response lag (tau = 2 s).
        # Initialise near expected steady-state (~−110 MW export) so the startup
        # transient doesn't inflate balance_residual for the first few seconds.
        self._grid_import = _FirstOrderFilter(-110.0, tau=2.0)

        # Tick counter and cumulative elapsed time
        self._tick      = 0
        self._elapsed_t = 0.0

        # Step-event clock
        self._next_step_t          = self._step_period
        self._step_boost_remaining = 0.0

        # Grid islanding state — rare simulated event
        self._islanded        = False
        self._islanding_timer = 0

    # ------------------------------------------------------------------
    def tick(self, dt: float = 1.0) -> dict:
        """Advance all subsystems by dt seconds and return a metric dict."""
        self._tick      += 1
        self._elapsed_t += dt

        # -- Step-event clock (drives compute load pulses) ----------------
        # Steps have jitter so the period is not perfectly regular.
        step_event = 0
        if self._elapsed_t >= self._next_step_t:
            step_event = 1
            self._step_boost_remaining = self.STEP_DURATION_S
            jitter = random.gauss(0, self.STEP_JITTER_S)
            self._next_step_t = self._elapsed_t + max(0.1, self._step_period + jitter)

        step_boost_raw = self.STEP_LOAD_BOOST_PCT if self._step_boost_remaining > 0 else 0.0
        self._step_boost_remaining = max(0.0, self._step_boost_remaining - dt)

        # -- Compute Racks (evaluated first — IT load drives GT dispatch) -
        # Background CPU trend is filtered (tau = 15 s).
        # Issue 4 fix: the step spike is routed through _cpu_spike (tau = 0.3 s)
        # so transitions have finite rise/fall time instead of infinite dP/dt.
        # This produces visible intermediate samples at 10 Hz (the "zero samples
        # between states" regression is resolved).
        cpu_target = max(self.COMPUTE_LOAD_PCT_MIN,
                         min(self.COMPUTE_LOAD_PCT_MAX,
                             self._cpu.value + random.gauss(0, 2)))
        cpu_base       = self._cpu.step(cpu_target, dt=dt)
        smoothed_boost = self._cpu_spike.step(step_boost_raw, dt=dt)
        cpu_load       = min(self.COMPUTE_LOAD_PCT_MAX, cpu_base + smoothed_boost)

        # Memory utilisation: tau=30 s + direct noise so the signal is non-
        # constant (regression fix: tau=60 s + round-to-1dp produced sd=0).
        mem_target = max(30.0, min(95.0, self._mem.value + random.gauss(0, 3)))
        mem_util   = round(
            self._mem.step(mem_target, dt=dt) + random.gauss(0, 0.2), 1)
        mem_util   = max(30.0, min(95.0, mem_util))

        it_load_mw = cpu_load / 100.0 * self.COMPUTE_RATED_MW

        # Inlet temperature: thermally lagged (tau = 30 s), not instantaneous.
        # Noise sigma kept small (0.02 °C) so filter autocorrelation is visible.
        inlet_target = 18.0 + (cpu_load / 100.0) * 12.0   # 18–30 °C range
        inlet_temp   = round(
            self._inlet_temp.step(inlet_target, dt=dt) + random.gauss(0, 0.02), 2)

        # -- Cooling Plant ------------------------------------------------
        # Issue 3 fix (TC-02 / TC-03): chiller heat input is thermally lagged
        # via _chiller_heat (tau = 90 s), so mechanical_load_mw does NOT pulse
        # in lockstep with the IT load.  lag-1 autocorr at 10 Hz ≈ 0.9989 vs.
        # the previous 0.9968 AT ZERO LAG (which was a flat-out model error).
        # The filter starts at 0 and rises; for the first ~90 s output is < 63 %
        # of steady state, approximating the Section 8 onset delay.
        it_frac          = cpu_load / 100.0
        heat_kw_instant  = it_load_mw * 1000.0
        heat_kw          = self._chiller_heat.step(heat_kw_instant, dt=dt)
        chws_target      = self.COOLING_CHWS_SETPOINT + it_frac * 2.0
        chws_temp        = self._chws.step(chws_target, dt=dt)
        flow             = round(
            self.COOLING_MAX_FLOW_LS * (0.4 + it_frac * 0.6) + random.gauss(0, 10), 1)
        flow             = max(0.0, min(self.COOLING_MAX_FLOW_LS, flow))
        cop              = round(
            4.5 - (chws_temp - self.COOLING_CHWS_SETPOINT) * 0.3
            + random.gauss(0, 0.05), 2)

        chiller_mw   = heat_kw / 1000.0 / max(cop, 0.5)   # chiller electrical draw
        pump_mw      = flow * 0.001                          # ~1 kW per L/s
        mech_load_mw = chiller_mw + pump_mw
        site_total_mw = it_load_mw + mech_load_mw
        losses_mw    = site_total_mw * self.SITE_LOSS_FACTOR

        # -- Gas Turbine (demand-following; causally coupled to IT load) --
        gt_target  = max(self.GT_MIN_MW,
                         min(self.GT_RATED_MW,
                             site_total_mw + random.gauss(0, 5.0)))
        # Issue 2 fix: the _FirstOrderFilter alone does not enforce GT_RAMP_MW_S.
        # Capture the pre-step value, advance the filter, then clamp the actual
        # change to ±GT_RAMP_MW_S × dt.  This brings peak ramp from ~15 MW/s
        # back within the 4 MW/s spec (Section 28.1 band).
        gt_prev        = self._gt_mw.value
        gt_filtered    = self._gt_mw.step(gt_target, dt=dt)
        max_gt_delta   = self.GT_RAMP_MW_S * dt
        actual_gt_chg  = gt_filtered - gt_prev
        gt_ramp_limited = abs(actual_gt_chg) > max_gt_delta
        if gt_ramp_limited:
            gt_mw = gt_prev + math.copysign(max_gt_delta, actual_gt_chg)
            self._gt_mw.value = round(gt_mw, 3)
        else:
            gt_mw = gt_filtered
        gt_load_f  = gt_mw / self.GT_RATED_MW
        gt_hr      = round(9800 + (1 - gt_load_f) * 2200 + random.gauss(0, 30), 1)
        # Exhaust temp has real thermal inertia (tau = 60 s — exhaust plenum).
        # Noise sigma kept small (0.05 °C) so filter autocorrelation is visible.
        gt_exhaust_target = 520.0 + gt_load_f * 80.0
        gt_exhaust = round(
            self._gt_exhaust.step(gt_exhaust_target, dt=dt) + random.gauss(0, 0.05), 2)
        gt_mode = "ramping" if abs(gt_mw - gt_target) > 1.0 else "at_target"

        # -- Solar PV -----------------------------------------------------
        sol_target  = max(0.0, min(1.0, self._solar_frac.value + random.gauss(0, 0.02)))
        sol_frac    = self._solar_frac.step(sol_target, dt=dt)
        sol_mw      = round(self.SOLAR_RATED_MW * sol_frac + random.gauss(0, 0.5), 2)
        sol_mw      = max(0.0, sol_mw)
        sol_cell_t  = round(25.0 + sol_frac * 30.0 + random.gauss(0, 0.3), 1)

        # -- BESS (smooths surplus/deficit between GT+solar and site load) -
        # With tau=0.3 s the BESS responds in ~3 ticks, covering the 90 MW step
        # and reducing balance_residual sd from 48 MW to ~1–2 MW (Issue 1 fix).
        net_gap     = site_total_mw - gt_mw - sol_mw
        bess_target = max(-self.BESS_RATED_MW, min(self.BESS_RATED_MW, net_gap))
        bess_mw     = self._bess_mw.step(bess_target, dt=dt)
        # SOC limits
        soc_limited = (
            (self._soc <= self.BESS_MIN_SOC + 1.0 and bess_target > 0) or
            (self._soc >= self.BESS_MAX_SOC - 1.0 and bess_target < 0)
        )
        # Negative bess_mw = charging (SoC rises); positive = discharging (SoC falls)
        self._soc  -= bess_mw / 3600.0 * dt * 100.0 / 200.0
        self._soc   = max(self.BESS_MIN_SOC, min(self.BESS_MAX_SOC, self._soc))
        soc_f       = self._soc / 100.0
        bess_v      = round(
            self.BESS_RATED_V * (0.90 + 0.12 * soc_f) + random.gauss(0, 1.0), 1)

        # Binding constraint diagnostic
        if soc_limited:
            binding_constraint = "soc_limit"
        elif gt_ramp_limited:
            binding_constraint = "ramp_limit"
        else:
            binding_constraint = "none"

        # -- Power Balance ------------------------------------------------
        bess_source = max(0.0, bess_mw)
        bess_sink   = max(0.0, -bess_mw)
        # grid_import: independently lagged PCC meter — NOT the slack variable.
        # Because it lags the true balance by ~2 s, the residual is non-trivially
        # non-zero and becomes a real diagnostic signal.
        grid_import_true = (site_total_mw + bess_sink + losses_mw
                            - gt_mw - sol_mw - bess_source)
        grid_import_mw = (self._grid_import.step(grid_import_true, dt=dt)
                          + random.gauss(0, 0.1))
        balance_residual = (gt_mw + sol_mw + bess_source + grid_import_mw
                            - site_total_mw - bess_sink - losses_mw)

        # Forecast: expected site load at the next step boundary, using lagged
        # cooling + current compute as the short-horizon prediction (§11.1).
        forecast_mw = round(
            cpu_target / 100.0 * self.COMPUTE_RATED_MW
            + self._chiller_heat.value / 1000.0, 3)

        # Islanding: rare simulated events (0.1 % chance / tick, 5–20 s)
        if not self._islanded:
            if random.random() < 0.001:
                self._islanded        = True
                self._islanding_timer = random.randint(50, 200)
        else:
            self._islanding_timer -= 1
            if self._islanding_timer <= 0:
                self._islanded = False

        return {
            "timestamp":                 datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "gt_power_mw":               round(gt_mw, 2),
            "gt_heat_rate_btu_kwh":      gt_hr,
            "gt_exhaust_temp_c":         gt_exhaust,
            "gt_setpoint_mw":            round(gt_target, 2),
            "gt_mode":                   gt_mode,
            "solar_output_mw":           sol_mw,
            "solar_irradiance_fraction": round(sol_frac, 4),
            "solar_cell_temp_c":         sol_cell_t,
            "bess_soc_pct":              round(self._soc, 2),
            "bess_power_mw":             round(bess_mw, 2),
            "bess_terminal_voltage_v":   bess_v,
            "bess_setpoint_mw":          round(bess_target, 2),
            "compute_cpu_load_pct":      round(cpu_load, 1),
            "compute_mem_util_pct":      mem_util,
            "compute_inlet_temp_c":      inlet_temp,
            "compute_load_mw":           round(it_load_mw, 3),
            "cooling_chws_temp_c":       round(chws_temp, 2),
            "cooling_pump_flow_ls":      flow,
            "cooling_cop":               cop,
            # Tier 1 — Power Balance
            "site_total_load_mw":        round(site_total_mw, 3),
            "it_load_mw":                round(it_load_mw, 3),
            "mechanical_load_mw":        round(mech_load_mw, 3),
            "grid_import_mw":            round(grid_import_mw, 3),
            "islanded":                  int(self._islanded),
            "balance_residual_mw":       round(balance_residual, 4),
            "binding_constraint":        binding_constraint,
            # Forecast / advisory
            "forecast_mw":               forecast_mw,
            # Scheduler diagnostics — step_event now generated internally
            "step_event":                step_event,
            # Run metadata
            "scenario_id":               "demo_v2",
            "rng_seed":                  self._rng_seed,
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
                        help="Seconds between rows (default: 1.0)")
    parser.add_argument("--step-period", type=float, default=0.7,
                        help="Scheduler training-step period in seconds (default: 0.7). "
                             "step_event=1 is written whenever a step boundary falls "
                             "inside the current tick window. Set to 0 to disable.")
    parser.add_argument("--fast", action="store_true",
                        help="Skip inter-tick sleep — generate all rows immediately. "
                             "Use for export/download; omit for live monitoring.")
    args = parser.parse_args()

    output_path = Path(args.out)

    # --- open CSV ---------------------------------------------------------
    try:
        writer, fh = open_csv(output_path)
    except OSError as exc:
        print(f"[ERROR] Cannot open {output_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    sim   = SimulatedGrid(step_period=args.step_period)
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
                row = sim.tick(dt=args.interval)
            except Exception as exc:          # pragma: no cover
                print(f"[WARN] Simulation error at tick {count}: {exc}", file=sys.stderr)
                time.sleep(args.interval)
                continue

            # Replace wall-clock timestamp with elapsed time "xx.y s"
            row["timestamp"] = f"{count * args.interval:.1f}"

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

            if not args.fast:
                time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\nInterrupted after {count} row(s).")
    finally:
        fh.close()
        print(f"Saved to '{output_path}'.")


if __name__ == "__main__":
    main()
