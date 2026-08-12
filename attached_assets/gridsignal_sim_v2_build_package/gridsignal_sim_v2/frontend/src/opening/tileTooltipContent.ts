/**
 * tileTooltipContent.ts — authored plain-English copy for every tile tooltip.
 *
 * IDs must match what each component passes to useTooltipStore().open().
 */

export interface TooltipContent {
  title: string
  body:  string
}

export const TILE_TOOLTIPS: Record<string, TooltipContent> = {

  // ── Plant tiles ────────────────────────────────────────────────────────────

  'gas-turbine': {
    title: 'Gas Turbine Fleet',
    body:  'The on-site generators that supply power when demand outpaces solar and battery. GridSignal watches the job scheduler and starts extra turbines before the load hits, so the fleet is already spinning up when it\'s needed instead of scrambling after the fact.',
  },

  'solar-pv': {
    title: 'Solar PV',
    body:  'Rooftop or ground-mounted solar panels feeding the microgrid. Output swings with sunlight and cloud cover, so GridSignal treats it as a variable source and leans on turbines and battery to cover the gaps.',
  },

  'battery-bess': {
    title: 'Battery (BESS)',
    body:  'A battery energy storage system that can charge up and discharge in seconds. It\'s the fastest-reacting asset on site — it absorbs sudden spikes or fills short gaps while slower generators catch up.',
  },

  'grid-connection': {
    title: 'Grid Connection',
    body:  'The link (or lack of one) to the public utility. This site is "islanded," meaning it\'s running entirely on its own generation with no utility backup — every megawatt has to come from turbines, solar, or battery on-site.',
  },

  'switchgear-pms': {
    title: 'Switchgear / PMS',
    body:  'The physical power management system that actually opens and closes breakers and starts/stops equipment. GridSignal sends it recommendations and forecasts — it never issues those commands itself; a human-configured PMS makes the final call.',
  },

  'distribution': {
    title: 'Distribution',
    body:  'The wiring and transformers that carry power from generation down to a voltage the data centre can use (480 V here). This is the plumbing between "power made" and "power used."',
  },

  'pdu-rpp': {
    title: 'PDU / RPP',
    body:  'Power distribution units and remote power panels — the last stop before power reaches individual server racks. This is where rack-level demand actually shows up as electrical load.',
  },

  'compute-racks': {
    title: 'GPU Co-Location Data Center',
    body:  'A shared facility housing 33 tenant cages across 4 scheduler stacks (Slurm, Kubernetes, Ray). Each tenant operates independently — some share full job telemetry with GridSignal, others share only their circuit meter reading. GridSignal aggregates the total GPU IT load across all tenants and uses it as the demand signal for turbine commitment and BESS dispatch.',
  },

  'cooling-plant': {
    title: 'Cooling Plant',
    body:  'Chillers and cooling infrastructure that remove the heat the compute racks generate. Cooling load trails compute load by design (about 90 seconds here) since it takes a moment for heat to build up and for cooling to respond.',
  },

  'scheduler-feed': {
    title: 'Scheduler Feed',
    body:  'The live connection into the Kubernetes job scheduler. This is GridSignal\'s early-warning system — it reads which jobs are about to be assigned to which nodes, before those jobs actually start drawing power.',
  },

  // ── Status bar (VerdictBand) ───────────────────────────────────────────────

  'dispatchable': {
    title: 'Dispatchable',
    body:  'Megawatts available on demand from sources GridSignal can actually rely on for planning — turbines and battery. Unlike solar, these can be counted on to deliver power exactly when called for.',
  },

  'renewable': {
    title: 'Renewable',
    body:  'Megawatts currently coming from solar. Useful, but weather-dependent — it\'s a bonus on top of the dispatchable baseline, not something the system can bank on.',
  },

  'gen-trip-cover': {
    title: 'Gen-Trip Cover',
    body:  'A safety check: if the largest single generator tripped offline right now, could everything else pick up the slack without dropping load? "N-1 ready" means yes — the fleet has enough spare capacity to survive losing its biggest unit.',
  },

  'attention': {
    title: 'Attention',
    body:  'A flag for anything that needs a human look — a subsystem reading outside normal bounds, an uncalibrated sensor, or a forecast running with wider-than-usual error bands. Not necessarily an alarm, but worth checking.',
  },

  // ── System strip (SubsystemTile) ──────────────────────────────────────────

  'agents': {
    title: 'Optimisation Agents',
    body:  'Background processes continuously evaluating dispatch options — which generator to start, when, and how much battery to hold in reserve — so a decision is ready the instant it\'s needed rather than being computed from scratch under pressure.',
  },

  'gcc': {
    title: 'Generation Commitment Controller',
    body:  'The logic that decides when to commit to starting a turbine. Once armed, it\'s watching for the trigger conditions from the forecast engine and stages equipment ahead of the actual power need.',
  },

  'forecast-quality': {
    title: 'Forecast Quality',
    body:  'A confidence indicator for the power predictions being shown. "Uncalibrated site" means this particular site hasn\'t yet been tuned with real operating data, so GridSignal is deliberately widening its error margins rather than overstating confidence.',
  },
}
