/**
 * PlantDiagram.tsx — one-line mimic diagram for the plant band (V-1).
 *
 * Layout: SVG viewBox 1200×440, preserveAspectRatio xMidYMid meet.
 * Flow lines are SVG paths; node boxes are <foreignObject> HTML overlays.
 *
 * Rules:
 *   · Flow width ∝ MW — nodes and flows bound to tickStore.
 *   · Grid connection always dashed + grey — never red.
 *   · Only clickable nodes respond to pointer events.
 *   · Lead-time callout on the far right (moves below on compact layout).
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useTickStore } from '../store/tickStore'
import { useScenarioStore } from '../store/scenarioStore'
import { NODES, FLOWS, LEADTIME_BOX, WATCHING_BOX, DIAGRAM_W, DIAGRAM_H } from './plantLayout'
import { FlowLine, FlowMarkers } from './FlowLine'
import { PlantNode } from './PlantNode'
import type { SolarPreview } from './PlantNode'
import type { TickPayload } from '../types'
import { SchedulerSummaryModal } from './SchedulerSummaryModal'
import type { FeedEntry } from './SchedulerSummaryModal'

interface PlantDiagramProps {
  /** Called when a clickable node is activated. Passes the node id. */
  onNodeClick: (nodeId: string) => void
  /** True when horizontal space is constrained (1024–1440 px). */
  compact?: boolean
  /** Solar forecast preview from GET /solar-preview — shown on the Solar PV node before a run. */
  solarPreview?: SolarPreview | null
  /**
   * Live solar output polled from GET /api/solar/state at 1.5 Hz.
   * Passed straight through to the solar-pv PlantNode so it stays in sync
   * with the Renewable Supply modal regardless of WebSocket tick age.
   */
  liveSolarMW?: number | null
}

function getMwForFlow(
  mwField: string | undefined,
  staticMW: number | undefined,
  tick: TickPayload | null,
): number {
  // No tick: use staticMW so solar (4.99) renders live and animated at rest.
  if (!tick) return staticMW ?? 0
  if (!mwField) return 0
  return Math.abs((tick as unknown as Record<string, unknown>)[mwField] as number) || 0
}

// ── Shared style constants ─────────────────────────────────────────────────
const _SANS: React.CSSProperties = { fontFamily: 'Inter,sans-serif' }
const _MONO: React.CSSProperties = {
  fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace",
}
const _RULE: React.CSSProperties = { height: 1, background: '#1e2a36', margin: '2px 0' }
const _BODY: React.CSSProperties = {
  ..._SANS, fontSize: 10, color: '#7d8b9c', lineHeight: 1.5, whiteSpace: 'pre-wrap' as const,
}
const _LABEL = (color: string): React.CSSProperties => ({
  ..._SANS, fontSize: 9, fontWeight: 700,
  letterSpacing: '0.12em', textTransform: 'uppercase' as const, color,
})


/**
 * WatchingCallout — centred box between Gas Turbine and Compute Racks.
 *
 * Idle  → "WHAT THIS DEMONSTRATES" (teal) — Claude-generated educational explanation.
 * Run   → "WHAT YOU ARE WATCHING"  (amber) — live narrative while it plays.
 *
 * In idle state, when a scenario is selected the component fetches the scenario
 * detail from /scenarios/:id, then POSTs to /api/ai/explain-scenario (Claude
 * claude-haiku-4-5) to generate a 4-sentence plain-English explanation for
 * new-hire operators.  Results are cached per scenario_id so switching back to
 * the same scenario does not re-generate.
 */
function WatchingCallout({ tick }: { tick: TickPayload | null }) {
  const watchingText = useScenarioStore(s => s.watchingText)
  const selectedId   = useScenarioStore(s => s.selectedId)
  const isRunning    = tick !== null
  const accent       = isRunning ? '#e0a458' : '#3fb6a8'
  const heading      = isRunning ? 'WHAT YOU ARE WATCHING' : 'WHAT THIS DEMONSTRATES'

  // Cache: "${scenarioId}:${mode}" → generated text
  const cache       = useRef<Record<string, string>>({})
  const [idleText,     setIdleText]     = useState<string | null>(null)
  const [runningText,  setRunningText]  = useState<string | null>(null)
  const [generating,   setGenerating]   = useState(false)

  const generate = useCallback(async (scenarioId: string, mode: 'demonstrates' | 'watching') => {
    const cacheKey = `${scenarioId}:${mode}`
    const setter   = mode === 'watching' ? setRunningText : setIdleText

    // Return cached result immediately if available
    if (cache.current[cacheKey]) {
      setter(cache.current[cacheKey])
      return
    }
    setGenerating(true)
    setter(null)
    try {
      // Fetch full scenario spec so we can pass rich parameters to Claude
      const detail = await fetch(`/scenarios/${scenarioId}`).then(r => r.ok ? r.json() : null)
      if (!detail) { setGenerating(false); return }
      const spec    = detail.spec ?? {}
      const turbines: {rated_mw?: number}[]                    = spec.turbine_units  ?? []
      const bess:     {rated_mw?: number; usable_mwh?: number}[] = spec.bess_units   ?? []
      const events:   {node_count?: number}[]                   = spec.workload_events ?? []
      const nodeMax   = events.reduce((m, e) => Math.max(m, e.node_count ?? 0), 0)

      const resp = await fetch('/api/ai/explain-scenario', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_name:        detail.name          ?? '',
          scenario_description: detail.description   ?? '',
          turbine_count:        turbines.length,
          turbine_rated_mw:     turbines[0]?.rated_mw  ?? 0,
          bess_rated_mw:        bess[0]?.rated_mw       ?? 0,
          bess_usable_mwh:      bess[0]?.usable_mwh     ?? 0,
          solar_rated_mw:       spec.solar_rated_mw     ?? 0,
          node_count_max:       nodeMax,
          run_duration_s:       spec.end_sim_time        ?? 300,
          island_mode:          spec.island_mode         ?? true,
          dt_lead_seconds:      spec.dt_lead_seconds     ?? 60,
          demo_description:     spec.demo_description    ?? '',
          mode,
        }),
      })
      if (resp.ok) {
        const data = await resp.json()
        cache.current[cacheKey] = data.explanation
        setter(data.explanation)
      }
    } catch (_) {
      // silently fall back to static text
    } finally {
      setGenerating(false)
    }
  }, [])

  // Pre-run: generate "demonstrates" when selected scenario changes
  useEffect(() => {
    if (isRunning || !selectedId) return
    generate(selectedId, 'demonstrates')
  }, [isRunning, selectedId, generate])

  // Run start: generate "watching" narrative from the scenario spec
  useEffect(() => {
    if (!isRunning || !selectedId) return
    generate(selectedId, 'watching')
  }, [isRunning, selectedId, generate])

  // What to show in the body
  const body = isRunning
    ? (runningText || watchingText || null)
    : (idleText    || watchingText || 'GridSignal reads the job scheduler, not the power meter. It knows a step-load is coming 30–60 s before it arrives, and stages generation and storage before the load lands.')

  const { x, y, w, h } = WATCHING_BOX
  return (
    <foreignObject x={x} y={y} width={w} height={h}>
      <div
        // @ts-expect-error — xmlns required for SVG foreignObject HTML
        xmlns="http://www.w3.org/1999/xhtml"
        style={{
          width: '100%', height: '100%', boxSizing: 'border-box',
          borderRadius: 6, border: `1.5px solid ${accent}`,
          background: '#0d1721', padding: '9px 14px',
          display: 'flex', flexDirection: 'column', gap: 4,
          transition: 'border-color 0.4s',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={_LABEL(accent)}>{heading}</div>
          {/* Subtle pulsing dot while Claude is generating */}
          {generating && !isRunning && (
            <div style={{
              width: 5, height: 5, borderRadius: '50%',
              background: accent, opacity: 0.7, flexShrink: 0,
              animation: 'pulse 1.2s ease-in-out infinite',
            }} />
          )}
        </div>
        <div style={_RULE} />
        <div style={{
          ..._BODY,
          flex: 1,
          overflowY: 'auto',
          scrollbarWidth: 'thin' as const,
          scrollbarColor: '#2a3a4a transparent',
          color: generating && !body ? '#3a5a6a' : '#c8d6e5',
          lineHeight: 1.6, whiteSpace: 'normal',
          transition: 'color 0.3s',
          paddingRight: 2,
        }}>
          {generating && !body
            ? 'Generating explanation…'
            : (body ?? '')
          }
        </div>
      </div>
    </foreignObject>
  )
}

/**
 * LeadTimeCallout — four-state operational panel (ISA-101 colour discipline).
 *
 * Spec vocabulary: "step-load" (37× in spec), "Δt_lead".
 * "load event" and "next load event" do not appear in the spec.
 *
 * State 1  AT REST       grey  — "NO STEP-LOAD INCOMING"
 * State 2  COUNTING DOWN amber — "STEP-LOAD INCOMING / 23 s / Nothing required"
 * State 3  RESERVE SHORT red   — "STEP-LOAD INCOMING — RESERVE SHORT / Acknowledge"
 * State 4  LANDED        teal  — "STEP-LOAD LANDED / Staged X s ahead" (30 s hold)
 *
 * ISA-101: permanently-amber trains operators to stop seeing amber.
 * The panel is muted at rest and gains colour only when action matters.
 *
 * "last event X min ago" in the at-rest body proves the scheduler feed is
 * alive — a dead integration and an empty queue look identical otherwise.
 *
 * Pitch copy belongs in the "How it works" topology explainer (onboarding,
 * opened deliberately). An operator running a plant should not see it.
 */
function LeadTimeCallout({
  tick,
  compact,
}: {
  tick: TickPayload | null
  compact?: boolean
}) {
  const latchedAlert     = useTickStore(s => s.latchedAlert)
  const acknowledgeAlert = useTickStore(s => s.acknowledgeAlert)

  // ── Landing-state tracking ─────────────────────────────────────────────────
  // When Δt_lead transitions from > 0 to 0, show STEP-LOAD LANDED for 30 s.
  const [landedUntil,      setLandedUntil]      = useState(0)
  const [stagedSecs,       setStagedSecs]       = useState(45)
  const [turbineAtLanding, setTurbineAtLanding] = useState(0)
  const prevDtLead  = useRef(0)
  const maxDtLead   = useRef(0)            // peak Δt_lead during current ramp
  const lastLandedAt = useRef<number>(0)  // wall-clock of most recent landing

  // ── NO STEP-LOAD INCOMING scrolling log ───────────────────────────────────
  const [atRestLog, setAtRestLog] = useState<Array<{ ts: string; body: string }>>([])
  const [showFeedTip, setShowFeedTip] = useState(false)
  const [showSummaryModal, setShowSummaryModal] = useState(false)
  const atRestScrollRef  = useRef<HTMLDivElement>(null)
  // Track State-1 transitions so we log only on entry, not every render.
  const prevIsState1    = useRef<boolean | null>(null)  // null = not yet evaluated
  const prevWasLanded   = useRef(false)
  const prevWasRunning  = useRef(false)
  // Snapshot refs so the transition effect captures fresh values without
  // re-firing when lastEventStr ticks (every minute) or stagedSecs changes.
  const tickRef         = useRef(tick)
  const stagedSecsRef   = useRef(stagedSecs)
  const lastEventStrRef = useRef('')
  // Track kube admission + queue state across ticks so we detect rising edges.
  // null = no kube scenario running (kube_metrics absent from tick).
  const prevActiveJobsRef    = useRef<number | null>(null)
  const prevAdmittedNodesRef = useRef<number | null>(null)
  const prevQueuedJobsRef    = useRef<number | null>(null)
  const prevIsRunningRef     = useRef(false)
  // BESS and power-cap transition tracking for feed entries.
  const prevBessOutputRef    = useRef<number>(0)
  const prevPowerCapRef      = useRef<boolean>(false)

  useEffect(() => {
    if (!tick) return
    const cur  = tick.dt_lead_next_s
    const prev = prevDtLead.current
    if (cur > maxDtLead.current) maxDtLead.current = cur
    // Rising-to-falling edge: step-load just landed
    if (prev > 0 && cur <= 0) {
      const now = Date.now()
      setLandedUntil(now + 30_000)
      setStagedSecs(Math.round(maxDtLead.current))
      setTurbineAtLanding(tick.turbine_output_mw)
      lastLandedAt.current = now
      maxDtLead.current = 0
    }
    prevDtLead.current = cur
  }, [tick])

  // Clear the landed banner after 30 s
  useEffect(() => {
    if (!landedUntil) return
    const ms = landedUntil - Date.now()
    if (ms <= 0) { setLandedUntil(0); return }
    const id = setTimeout(() => setLandedUntil(0), ms)
    return () => clearTimeout(id)
  }, [landedUntil])

  // ── Derive state ───────────────────────────────────────────────────────────
  const isLanded  = landedUntil > 0 && Date.now() < landedUntil
  const isRunning = tick !== null && tick.dt_lead_next_s > 0
  const hasAlert  = latchedAlert !== null

  // "last event X min ago" — proves scheduler feed is alive at rest
  const lastEventStr = (() => {
    if (!lastLandedAt.current) return 'no events this session'
    const minsAgo = Math.floor((Date.now() - lastLandedAt.current) / 60_000)
    return minsAgo < 1 ? 'last event < 1 min ago' : `last event ${minsAgo} min ago`
  })()

  // ── Keep snapshot refs current so the transition effect captures fresh
  //    values without re-firing when lastEventStr or stagedSecs change.
  tickRef.current         = tick
  stagedSecsRef.current   = stagedSecs
  lastEventStrRef.current = lastEventStr

  // ── Detect transitions INTO State 1 (AT REST) and append a log entry ──────
  useEffect(() => {
    const nowState1 = !isLanded && !isRunning
    const wasState1 = prevIsState1.current

    if (nowState1 && wasState1 !== true) {
      // Format a timestamp: sim time if a tick exists, else wall clock.
      const t = tickRef.current
      let ts: string
      if (t) {
        ts = `t=${Math.round(t.sim_time_seconds)}s`
      } else {
        const d = new Date()
        ts = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
      }

      // Describe what just happened.
      let body: string
      if (wasState1 === null) {
        body = 'Scheduler online.'
      } else if (prevWasLanded.current) {
        body = `Step-load absorbed — staged ${stagedSecsRef.current}s ahead. System returned to rest.`
      } else if (prevWasRunning.current) {
        body = 'Countdown cleared — system returned to rest.'
      } else {
        body = `Scheduler healthy — ${lastEventStrRef.current}.`
      }

      setAtRestLog(prev => [...prev, { ts, body }])
    }

    prevIsState1.current   = nowState1
    prevWasLanded.current  = isLanded
    prevWasRunning.current = isRunning
  }, [isLanded, isRunning])

  // Auto-scroll the log to the bottom whenever a new entry is appended.
  useEffect(() => {
    const el = atRestScrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [atRestLog])

  // ── Kube scheduler admission detection ────────────────────────────────────
  // Fires on every tick. Detects rising edges (queue, admission), falling edges
  // (job completion), and power-cap pauses so the feed covers the full lifecycle.
  useEffect(() => {
    const kube = tick?.kube_metrics ?? null
    if (!kube) {
      // No kube scenario — reset so next run starts clean.
      prevActiveJobsRef.current    = null
      prevAdmittedNodesRef.current = null
      prevQueuedJobsRef.current    = null
      prevPowerCapRef.current      = false
      return
    }
    const prevJobs      = prevActiveJobsRef.current
    const prevNodes     = prevAdmittedNodesRef.current
    const prevQueued    = prevQueuedJobsRef.current
    const prevPowerCap  = prevPowerCapRef.current
    const ts         = `t=${Math.round(tick!.sim_time_seconds)}s`
    const forecastMw = tick!.confidence_upper_mw   // site-wide step-load forecast

    // ── First kube tick (page loaded mid-run): emit a catch-up snapshot ───
    if (prevJobs === null) {
      const parts: string[] = []
      if (kube.active_jobs > 0) {
        const jw = kube.active_jobs === 1 ? 'job' : 'jobs'
        parts.push(`${kube.active_jobs} ${jw} running · ${kube.admitted_nodes} nodes`)
      }
      if ((kube.queued_jobs ?? 0) > 0) {
        const qw = kube.queued_jobs === 1 ? 'job' : 'jobs'
        parts.push(`${kube.queued_jobs} ${qw} queued`)
      }
      const body = parts.length > 0
        ? `Kube: connected — ${parts.join(' · ')}.`
        : `Kube: connected — no jobs running.`
      setAtRestLog(prev => [...prev, { ts, body }])
    }

    // ── Rising edge: new job(s) entered the reorder buffer ────────────────
    if (prevQueued !== null && kube.queued_jobs > (prevQueued ?? 0) && kube.queued_jobs > 0) {
      const delta   = kube.queued_jobs - prevQueued
      const jobWord = delta === 1 ? 'job' : 'jobs'
      const qWord   = kube.queued_jobs === 1 ? 'job' : 'jobs'
      const body = `Kube: ${delta} ${jobWord} received — `
        + `${kube.queued_jobs} ${qWord} waiting for admission.`
      setAtRestLog(prev => [...prev, { ts, body }])
    }

    // ── Rising edge: job(s) admitted from the queue ───────────────────────
    // "217-node GPU workload" uses singular noun in compound-adjective position.
    // runWord covers the total now running (independent of how many were just admitted).
    if (prevJobs !== null && kube.active_jobs > prevJobs) {
      const admittedJobs  = kube.active_jobs - prevJobs
      const admittedNodes = prevNodes !== null
        ? Math.max(0, kube.admitted_nodes - prevNodes)
        : kube.admitted_nodes
      const jobWord  = admittedJobs    === 1 ? 'job'  : 'jobs'
      const runWord  = kube.active_jobs === 1 ? 'job'  : 'jobs'   // total running
      const mwSuffix = forecastMw > 0.1
        ? ` — forecast +${forecastMw.toFixed(1)} MW at full draw`
        : ''
      const body = admittedNodes > 0
        ? `Kube: ${admittedNodes}-node GPU workload admitted (${admittedJobs} ${jobWord})${mwSuffix}. `
          + `${kube.active_jobs} ${runWord} now running, ${kube.admitted_nodes} nodes total.`
        : `Kube: ${admittedJobs} GPU ${jobWord} admitted${mwSuffix}. `
          + `${kube.active_jobs} ${runWord} now running, ${kube.admitted_nodes} nodes total.`
      setAtRestLog(prev => [...prev, { ts, body }])
    }

    // ── Falling edge: job(s) completed ────────────────────────────────────
    if (prevJobs !== null && kube.active_jobs < prevJobs) {
      const completedJobs = prevJobs - kube.active_jobs
      const jobWord = completedJobs   === 1 ? 'job' : 'jobs'
      const remWord = kube.active_jobs === 1 ? 'job' : 'jobs'
      const body = kube.active_jobs > 0
        ? `Kube: ${completedJobs} ${jobWord} completed — ${kube.active_jobs} ${remWord} still running.`
        : `Kube: ${completedJobs} ${jobWord} completed — no jobs running.`
      setAtRestLog(prev => [...prev, { ts, body }])
    }

    // ── Power cap: admission paused / cleared ─────────────────────────────
    if (tick!.power_cap_active && !prevPowerCap && (kube.queued_jobs ?? 0) > 0) {
      const body = `Kube: admission paused — power cap active, waiting for turbine headroom.`
      setAtRestLog(prev => [...prev, { ts, body }])
    }
    if (!tick!.power_cap_active && prevPowerCap) {
      const body = `Kube: power cap cleared — admission window open.`
      setAtRestLog(prev => [...prev, { ts, body }])
    }

    prevActiveJobsRef.current    = kube.active_jobs
    prevAdmittedNodesRef.current = kube.admitted_nodes
    prevQueuedJobsRef.current    = kube.queued_jobs
    prevPowerCapRef.current      = tick!.power_cap_active
  }, [tick])

  // ── Gas turbine start detection ───────────────────────────────────────────
  // Rising edge of isRunning → step-load countdown just began → log it.
  // Uses turbine_ramp_credit_mw (what this asset contributes) and
  // confidence_upper_mw (total site forecast) so both numbers are attributed.
  useEffect(() => {
    if (!tick) return
    const nowRunning = tick.dt_lead_next_s > 0
    if (nowRunning && !prevIsRunningRef.current) {
      const ts         = `t=${Math.round(tick.sim_time_seconds)}s`
      const forecast   = tick.confidence_upper_mw      // site-wide step-load forecast
      const rampCredit = tick.turbine_ramp_credit_mw   // MW this turbine covers in dt_lead
      const body = rampCredit > 0.1
        ? `Gas turbine ramping — ramp credit +${rampCredit.toFixed(1)} MW `
          + `of +${forecast.toFixed(1)} MW forecast step-load.`
        : `Gas turbine starting — forecast step-load +${forecast.toFixed(1)} MW.`
      setAtRestLog(prev => [...prev, { ts, body }])
    }
    prevIsRunningRef.current = nowRunning
  }, [tick])

  // ── BESS discharge / charge / standby detection ───────────────────────────
  // Emits a feed entry whenever the BESS transitions between standby, discharge,
  // and absorb states so the feed accounts for what the BESS is actually doing.
  useEffect(() => {
    if (!tick) { prevBessOutputRef.current = 0; return }
    const bess = tick.bess_output_mw
    const prev = prevBessOutputRef.current
    const ts   = `t=${Math.round(tick.sim_time_seconds)}s`
    const THR  = 0.5   // MW — below this magnitude is standby / anchor noise
    // Standby → discharge
    if (bess >= THR && prev < THR) {
      setAtRestLog(p => [...p, {
        ts, body: `BESS: discharging at ${bess.toFixed(1)} MW to bridge supply gap.`,
      }])
    }
    // Standby / discharge → absorbing surplus
    if (bess <= -THR && prev > -THR) {
      setAtRestLog(p => [...p, {
        ts, body: `BESS: absorbing ${Math.abs(bess).toFixed(1)} MW — storing surplus generation.`,
      }])
    }
    // Return to standby from either direction
    if (Math.abs(bess) < THR && (prev >= THR || prev <= -THR)) {
      setAtRestLog(p => [...p, { ts, body: `BESS: returned to standby.` }])
    }
    prevBessOutputRef.current = bess
  }, [tick])

  // ISA-101 colour by state
  const accent =
    isLanded   ? '#3fb6a8' :
    !isRunning ? '#2a3a4a' :
    hasAlert   ? '#f85149' :
    /* ok */    '#e0a458'

  // Geometry
  const box = LEADTIME_BOX
  const x   = compact ? DIAGRAM_W - box.w - 4 : box.x
  const y   = compact ? DIAGRAM_H - box.h - 4 : box.y

  return (
    <foreignObject x={x} y={y} width={box.w} height={box.h}>
      <div
        // @ts-expect-error — xmlns required for SVG foreignObject HTML
        xmlns="http://www.w3.org/1999/xhtml"
        style={{
          width: '100%', height: '100%', boxSizing: 'border-box',
          borderRadius: 8, border: `1.5px solid ${accent}`,
          background: '#0f1a22', padding: '14px 16px',
          display: 'flex', flexDirection: 'column', gap: 5,
          transition: 'border-color 0.35s',
        }}
      >

        {/* ── STATE 4: STEP-LOAD LANDED ────────────────────────────────── */}
        {isLanded && <>
          <div style={_LABEL(accent)}>STEP-LOAD LANDED</div>
          <div style={_RULE} />
          <div style={{ ..._MONO, fontSize: 20, fontWeight: 600, color: '#e6edf3', lineHeight: 1.25 }}>
            Staged {stagedSecs} s ahead of arrival
          </div>
          <div style={_BODY}>
            Turbine {turbineAtLanding.toFixed(2)} MW · BESS standby
          </div>
        </>}

        {/* ── STATE 3: RESERVE SHORT ───────────────────────────────────── */}
        {!isLanded && isRunning && hasAlert && (() => {
          const secs      = Math.max(0, Math.round(tick!.dt_lead_next_s))
          const predicted = tick!.confidence_upper_mw
          const avail     = tick!.turbine_output_mw + tick!.bess_output_mw + tick!.p_renewable_mw
          const shortfall = Math.max(0, predicted - avail)
          const lastEntry = atRestLog.length > 0 ? atRestLog[atRestLog.length - 1] : null
          return <>
            <div style={_LABEL(accent)}>STEP-LOAD INCOMING — RESERVE SHORT</div>
            <div style={_RULE} />
            <div style={{ ..._SANS, fontSize: 28, fontWeight: 500, color: accent, lineHeight: 1 }}>{secs} s</div>
            <div style={{ ..._BODY, color: '#e6edf3' }}>
              {`until racks reach full draw\n+${predicted.toFixed(1)} MW · ${
                shortfall > 0.1
                  ? `${shortfall.toFixed(1)} MW will be uncovered`
                  : 'insufficient reserve'
              }`}
            </div>
            <button
              onClick={() => latchedAlert && acknowledgeAlert(latchedAlert.tick_index)}
              style={{
                marginTop: 4, padding: '3px 10px', borderRadius: 4,
                border: `1px solid ${accent}`, background: 'transparent',
                color: accent, cursor: 'pointer', alignSelf: 'flex-start',
                ..._MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.06em',
              }}
            >
              Acknowledge
            </button>
            {lastEntry && <>
              <div style={{ ..._RULE, marginTop: 2 }} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 1, overflow: 'hidden' }}>
                <span style={{ ..._MONO, fontSize: 8, color: '#3a5a6a', lineHeight: 1.3 }}>
                  {lastEntry.ts} · SCHEDULER FEED
                </span>
                <span style={{ ..._BODY, color: '#4b5764', lineHeight: 1.4,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {lastEntry.body}
                </span>
              </div>
            </>}
          </>
        })()}

        {/* ── STATE 2: COUNTING DOWN ───────────────────────────────────── */}
        {!isLanded && isRunning && !hasAlert && (() => {
          const secs      = Math.max(0, Math.round(tick!.dt_lead_next_s))
          const predicted = tick!.confidence_upper_mw
          return <>
            <div style={_LABEL(accent)}>STEP-LOAD INCOMING</div>
            <div style={_RULE} />
            <div style={{ ..._SANS, fontSize: 28, fontWeight: 500, color: accent, lineHeight: 1 }}>{secs} s</div>
            <div style={{ ..._BODY, color: '#e6edf3' }}>
              {`until racks reach full draw\n+${predicted.toFixed(1)} MW · turbine ramping · BESS armed`}
            </div>
            <div style={{ ..._BODY, color: '#3fb6a8', fontWeight: 600 }}>Nothing required</div>
            {/* ── SCHEDULER FEED log (live during countdown) ────────────── */}
            {atRestLog.length > 0 && <>
              <div style={{ ..._RULE, marginTop: 2 }} />
              <div style={{
                display: 'flex', alignItems: 'center',
                justifyContent: 'space-between', marginBottom: -2,
              }}>
                <span style={{ ..._MONO, fontSize: 8, color: '#3a5a6a' }}>SCHEDULER FEED</span>
                <button
                  onClick={() => setShowSummaryModal(true)}
                  style={{
                    background: 'transparent', border: '1px solid #1e3a4a',
                    borderRadius: 3, color: '#3fb6a8', cursor: 'pointer',
                    ..._MONO, fontSize: 7, fontWeight: 700,
                    letterSpacing: '0.04em', padding: '1px 5px', lineHeight: 1.4,
                    flexShrink: 0,
                  }}
                >
                  AI SUMMARY
                </button>
              </div>
              <div
                ref={atRestScrollRef}
                style={{
                  flex: 1, overflowY: 'auto',
                  display: 'flex', flexDirection: 'column', gap: 5,
                  paddingRight: 2,
                  scrollbarWidth: 'thin' as const,
                  scrollbarColor: '#2a3a4a transparent',
                }}
              >
                {atRestLog.map((entry, i) => (
                  <div key={i} style={{
                    display: 'flex', flexDirection: 'column', gap: 1,
                    borderLeft: `2px solid ${i === atRestLog.length - 1 ? '#2a5060' : '#1e2a36'}`,
                    paddingLeft: 6,
                  }}>
                    <span style={{ ..._MONO, fontSize: 8, color: '#3a5a6a', lineHeight: 1.4 }}>
                      {entry.ts}
                    </span>
                    <span style={{ ..._BODY, lineHeight: 1.5,
                      color: i === atRestLog.length - 1 ? '#7d9ab0' : '#4b5764' }}>
                      {entry.body}
                    </span>
                  </div>
                ))}
              </div>
            </>}
          </>
        })()}

        {/* ── STATE 1: AT REST — scrolling event log ──────────────────── */}
        {!isLanded && !isRunning && <>
          {/* Title row: label + tooltip + AI Summary button */}
          <div style={{ position: 'relative' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 4 }}>
              <div
                style={{ ..._LABEL(accent), cursor: 'default', display: 'inline-block' }}
                onMouseEnter={() => setShowFeedTip(true)}
                onMouseLeave={() => setShowFeedTip(false)}
              >
                SCHEDULER FEED
              </div>
              <button
                onClick={() => setShowSummaryModal(true)}
                title="Ask Claude to summarise the feed in plain language"
                style={{
                  background: 'rgba(63,182,168,0.07)',
                  border: '1px solid #2a4a5a',
                  borderRadius: 4,
                  color: '#3fb6a8',
                  cursor: 'pointer',
                  ..._MONO, fontSize: 8, fontWeight: 700,
                  letterSpacing: '0.05em',
                  padding: '2px 7px',
                  lineHeight: 1.5,
                  flexShrink: 0,
                  transition: 'background 0.15s, border-color 0.15s',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.background = 'rgba(63,182,168,0.16)'
                  e.currentTarget.style.borderColor = '#3fb6a8'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = 'rgba(63,182,168,0.07)'
                  e.currentTarget.style.borderColor = '#2a4a5a'
                }}
              >
                AI SUMMARY
              </button>
            </div>
            {showFeedTip && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, zIndex: 10,
                marginTop: 4, width: 220,
                background: '#162130', border: '1px solid #2a4a5a',
                borderRadius: 5, padding: '7px 10px',
                ..._BODY, color: '#9ab4c8', lineHeight: 1.6,
                boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
                pointerEvents: 'none',
              }}>
                This feed comes from the <strong style={{ color: '#c8d6e5' }}>scheduler</strong> — the software that decides which jobs run and when — not from a power sensor. It records both <strong style={{ color: '#c8d6e5' }}>GPU job admissions</strong> (Kubernetes) and <strong style={{ color: '#c8d6e5' }}>step-load countdowns</strong>, and stays live even when nothing is happening.
              </div>
            )}
          </div>
          <div style={_RULE} />

          {/* AI Summary modal — rendered via portal so it escapes the SVG foreignObject */}
          {showSummaryModal && (
            <SchedulerSummaryModal
              feedEntries={atRestLog as FeedEntry[]}
              tick={tick}
              onClose={() => setShowSummaryModal(false)}
            />
          )}
          {/* Scrolling vbox: one entry per transition into AT REST state.
              flex:1 fills whatever height remains after the label+rule.
              overflowY:'auto' enables scrolling; auto-scroll keeps the
              latest entry visible without the operator having to scroll. */}
          <div
            ref={atRestScrollRef}
            style={{
              flex: 1,
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
              paddingRight: 2,
              // Thin scrollbar so it doesn't crowd the 280 px box.
              scrollbarWidth: 'thin' as const,
              scrollbarColor: '#2a3a4a transparent',
            }}
          >
            {atRestLog.length === 0 && (
              <div style={{ ..._BODY, color: '#2a3a4a', fontStyle: 'italic' }}>
                Awaiting first event…
              </div>
            )}
            {atRestLog.map((entry, i) => (
              <div
                key={i}
                style={{
                  display: 'flex', flexDirection: 'column', gap: 1,
                  borderLeft: `2px solid #1e2a36`,
                  paddingLeft: 6,
                  // Highlight the most-recent entry
                  ...(i === atRestLog.length - 1
                    ? { borderLeftColor: '#2a5060' }
                    : {}),
                }}
              >
                <span style={{ ..._MONO, fontSize: 8, color: '#3a5a6a', lineHeight: 1.4 }}>
                  {entry.ts}
                </span>
                <span style={{ ..._BODY, color: i === atRestLog.length - 1 ? '#7d9ab0' : '#4b5764', lineHeight: 1.5 }}>
                  {entry.body}
                </span>
              </div>
            ))}
          </div>
        </>}

      </div>
    </foreignObject>
  )
}

export function PlantDiagram({ onNodeClick, compact, solarPreview, liveSolarMW }: PlantDiagramProps) {
  const tick = useTickStore(s => s.latestTick)

  return (
    <svg
      viewBox={`0 0 ${DIAGRAM_W} ${DIAGRAM_H}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: '100%', height: '100%', display: 'block', overflow: 'visible' }}
      aria-label="Plant one-line mimic diagram"
    >
      <FlowMarkers />

      {/* ── Flow lines (behind nodes) ───────────────────────────────────── */}
      {FLOWS.map(flow => (
        <FlowLine
          key={flow.id}
          d={flow.d}
          mwValue={getMwForFlow(flow.mwField, flow.staticMW, tick)}
          maxMW={flow.maxMW}
          color={flow.color}
          isGrid={flow.isGrid}
          marker={flow.marker}
        />
      ))}

      {/* ── Nodes ───────────────────────────────────────────────────────── */}
      {NODES.map(node => (
        <PlantNode
          key={node.id}
          def={node}
          tick={tick}
          onClick={onNodeClick}
          solarPreview={node.id === 'solar-pv' ? solarPreview : null}
          liveSolarMW={liveSolarMW}
        />
      ))}

      {/* ── Watching callout — centred between Gen & Compute ──────────── */}
      <WatchingCallout tick={tick} />

      {/* ── Lead-time callout ─────────────────────────────────────────── */}
      <LeadTimeCallout tick={tick} compact={compact} />
    </svg>
  )
}
