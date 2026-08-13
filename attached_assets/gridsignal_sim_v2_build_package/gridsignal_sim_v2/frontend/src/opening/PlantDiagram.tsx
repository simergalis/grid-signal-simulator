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
import { useBessConfigStore } from '../store/bessConfigStore'
import { NODES, FLOWS, LEADTIME_BOX, WATCHING_BOX, DIAGRAM_W, DIAGRAM_H, FUEL_CELL_NODE, FUEL_CELL_FLOW } from './plantLayout'
import { FlowLine, FlowMarkers } from './FlowLine'
import { PlantNode } from './PlantNode'
import type { SolarPreview } from './PlantNode'
import type { TickPayload } from '../types'
import { SchedulerSummaryModal } from './SchedulerSummaryModal'
import type { FeedEntry } from './SchedulerSummaryModal'
import { InfoBtn } from './TileTooltip'

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
  /**
   * When provided, renders a cyan selection outline around all power-supply
   * source nodes and a "Select Power Supply" tag at the bottom-left corner.
   * Clicking the tag calls this handler to open the modal.
   */
  onSelectPowerSupply?: () => void
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


/** Renders bullet lines (starting with •) as styled chevron bullets, or plain text fallback. */
function BulletBody({ text, accent }: { text: string; accent: string }) {
  const lines   = text.split('\n').map(l => l.trim()).filter(Boolean)
  const bullets = lines.filter(l => l.startsWith('•'))
  if (bullets.length >= 2) {
    return (
      <>
        {bullets.map((line, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 6, lineHeight: 1.45 }}>
            <span style={{ color: accent, flexShrink: 0, fontSize: 10, marginTop: 1 }}>▸</span>
            <span>{line.replace(/^•\s*/, '')}</span>
          </div>
        ))}
      </>
    )
  }
  return <span style={{ lineHeight: 1.6, whiteSpace: 'normal' }}>{text}</span>
}

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
          solar_rated_mw:        spec.solar_rated_mw        ?? 0,
          node_count_max:        nodeMax,
          run_duration_s:        spec.end_sim_time          ?? 300,
          island_mode:           spec.island_mode            ?? true,
          dt_lead_seconds:       spec.dt_lead_seconds        ?? 60,
          demo_description:      spec.demo_description       ?? '',
          frequency_nominal_hz:  spec.frequency_nominal_hz  ?? 60.0,
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
          transition: 'color 0.3s',
          paddingRight: 2,
          display: 'flex', flexDirection: 'column', gap: 5,
          justifyContent: 'center',
        }}>
          {generating && !body
            ? <span style={{ lineHeight: 1.6 }}>Generating explanation…</span>
            : <BulletBody text={body ?? ''} accent={accent} />
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
  const appendGccEvent   = useTickStore(s => s.appendGccEvent)
  const triggerGccFlash  = useTickStore(s => s.triggerGccFlash)
  const selectedId       = useScenarioStore(s => s.selectedId)
  const applyBessPreset  = useBessConfigStore(s => s.applyPreset)

  // ── Landing-state tracking ─────────────────────────────────────────────────
  // When Δt_lead transitions from > 0 to 0, show STEP-LOAD LANDED for 30 s.
  const [landedUntil, setLandedUntil] = useState(0)
  const [stagedSecs,  setStagedSecs]  = useState(45)
  const prevDtLead  = useRef(0)
  const maxDtLead   = useRef(0)            // peak Δt_lead during current ramp
  const lastLandedAt = useRef<number>(0)  // wall-clock of most recent landing

  // ── NO STEP-LOAD INCOMING scrolling log ───────────────────────────────────
  const [atRestLog, setAtRestLog] = useState<Array<{ ts: string; body: string }>>([])
  const [showSummaryModal, setShowSummaryModal] = useState(false)
  // Solar PV rated capacity — fetched from scenario spec when selection changes,
  // passed to the scheduler-summary modal so Claude can reason about solar headroom.
  const [solarRatedMw, setSolarRatedMw] = useState<number>(0)

  // Fetch spec fields whenever the selected scenario changes:
  //   • solar_rated_mw   — passed to the scheduler-summary modal for Claude headroom reasoning
  //   • ui_bess_rated_mw / ui_bess_usable_mwh — seeds the BESS config widget with the
  //     scenario's preferred starting values (falls back to global default 30/30 when absent)
  useEffect(() => {
    if (!selectedId) {
      setSolarRatedMw(0)
      applyBessPreset('freq-anchor', 30, 30)
      return
    }
    let cancelled = false
    fetch(`/scenarios/${selectedId}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!cancelled) {
          if (data?.spec?.solar_rated_mw != null) setSolarRatedMw(data.spec.solar_rated_mw)
          // Seed BESS widget: use scenario ui_bess_* if present, else global default
          const mw  = data?.spec?.ui_bess_rated_mw  ?? 30
          const mwh = data?.spec?.ui_bess_usable_mwh ?? 30
          applyBessPreset('freq-anchor', mw, mwh)
        }
      })
      .catch(() => {/* silently ignore — solar context is enhancement only */})
    return () => { cancelled = true }
  }, [selectedId, applyBessPreset])
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
  // Per-unit turbine state tracking (asset_id → last known state string).
  const prevTurbineStatesRef = useRef<Record<string, string>>({})
  // GCC commitment block action tracking — null = no tick seen yet.
  const prevCommitActionRef  = useRef<string | null>(null)

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
    if (kube.power_cap_active && !prevPowerCap && (kube.queued_jobs ?? 0) > 0) {
      const body = `Kube: admission paused — power cap active, waiting for turbine headroom.`
      setAtRestLog(prev => [...prev, { ts, body }])
    }
    if (!kube.power_cap_active && prevPowerCap) {
      const body = `Kube: power cap cleared — admission window open.`
      setAtRestLog(prev => [...prev, { ts, body }])
    }

    prevActiveJobsRef.current    = kube.active_jobs
    prevAdmittedNodesRef.current = kube.admitted_nodes
    prevQueuedJobsRef.current    = kube.queued_jobs
    prevPowerCapRef.current      = kube.power_cap_active
  }, [tick])

  // ── GCC commitment block decision tracking ───────────────────────────────
  // Emits a feed entry each time commitment_block.action changes so operators
  // see the GCC's commit / decommit / hold decisions as they happen.
  // • commit   → GCC decided to start a standby unit (with reason + utilisation)
  // • decommit → GCC decided to release an on-bus unit
  // • hold     → only logged when transitioning BACK from commit/decommit so the
  //              feed isn't flooded on every steady-state tick
  useEffect(() => {
    if (!tick) { prevCommitActionRef.current = null; return }
    const cb = tick.commitment_block
    if (!cb) return

    const action = cb.action
    const prev   = prevCommitActionRef.current

    // First tick seen — record without emitting (no "previous" to compare against).
    if (prev === null) {
      prevCommitActionRef.current = action
      return
    }

    if (action !== prev) {
      const ts     = `t=${Math.round(tick.sim_time_seconds)}s`
      const util   = (cb.utilisation * 100).toFixed(1)
      const unit   = cb.target_unit_id ? cb.target_unit_id.toUpperCase() : null
      const reason = cb.reason ?? ''

      let body = ''
      if (action === 'commit') {
        const unitPart = unit ? ` ${unit}` : ''
        body = `GCC: COMMIT${unitPart} — ${reason} (fleet utilisation ${util}%).`
      } else if (action === 'decommit') {
        const unitPart = unit ? ` ${unit}` : ''
        body = `GCC: DECOMMIT${unitPart} — ${reason}.`
      } else {
        // hold — only emit when transitioning out of an active decision
        if (prev === 'commit' || prev === 'decommit') {
          const blockedNote = cb.blocked_by ? ` Held by: ${cb.blocked_by}.` : ''
          body = `GCC: HOLD — ${reason}.${blockedNote}`
        }
      }

      if (body) {
        setAtRestLog(p => [...p, { ts, body }])
        appendGccEvent({ ts, body })
        triggerGccFlash()
      }
    }

    prevCommitActionRef.current = action
  }, [tick])

  // ── Gas turbine start detection ───────────────────────────────────────────
  // Rising edge of isRunning → step-load countdown just began → log the GCC
  // dispatch outcome (ramp credit vs forecast step-load size).
  useEffect(() => {
    if (!tick) return
    const nowRunning = tick.dt_lead_next_s > 0
    if (nowRunning && !prevIsRunningRef.current) {
      const ts         = `t=${Math.round(tick.sim_time_seconds)}s`
      const forecast   = tick.confidence_upper_mw
      const rampCredit = tick.turbine_ramp_credit_mw
      const body = rampCredit > 0.1
        ? `GCC dispatch: ramp credit +${rampCredit.toFixed(1)} MW`
          + ` of +${forecast.toFixed(1)} MW forecast step-load.`
        : `GCC dispatch: turbine committed — step-load +${forecast.toFixed(1)} MW incoming.`
      setAtRestLog(prev => [...prev, { ts, body }])
      appendGccEvent({ ts, body })
      triggerGccFlash()
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

  // ── Gas turbine per-unit start-sequence detection ────────────────────────
  // Watches state on each TurbineUnitSpec in tick.turbine_units.
  // • "starting" rising edge  → unit just began its start sequence (spinning up).
  // • "synchronised" from "starting" → unit closed its breaker and came on bus.
  // Skips first-seen ticks (prev === undefined) to avoid false positives on
  // page-load mid-run, and skips units that lack the live state overlay.
  useEffect(() => {
    if (!tick) return
    const units = tick.turbine_units ?? []
    if (units.length === 0) return
    const ts = `t=${Math.round(tick.sim_time_seconds)}s`

    for (const unit of units) {
      const id    = unit.asset_id
      const state = unit.state   // undefined when live overlay absent (Phase 0 only)
      if (!state) continue       // no live state field — skip

      const prev = prevTurbineStatesRef.current[id]  // undefined = first tick for this unit

      // Rising edge: unit begins start sequence.
      // Guard: prev must exist and must not already be "starting" to avoid
      // re-firing on every tick while the start sequence is in progress.
      if (state === 'starting' && prev !== undefined && prev !== 'starting') {
        const thermal    = unit.thermal_state ?? 'cold'
        const startDurS  = thermal === 'hot'  ? unit.hot_start_s
                         : thermal === 'warm' ? unit.warm_start_s
                         : unit.cold_start_s
        const eta = unit.time_to_online_s != null
          ? `~${Math.round(unit.time_to_online_s)} s to online`
          : startDurS != null
            ? `~${startDurS} s to online`
            : null
        const phase   = unit.start_phase ? ` · ${unit.start_phase}` : ''
        const etaPart = eta ? `, ${eta}` : ''
        const body = `${id.toUpperCase()}: start sequence initiated — ${thermal} start${phase}${etaPart}.`
        setAtRestLog(p => [...p, { ts, body }])
      }

      // Completion edge: unit closes breaker and comes on bus.
      if (state === 'synchronised' && prev === 'starting') {
        const mwPart = unit.output_mw != null && unit.output_mw > 0.05
          ? ` at ${unit.output_mw.toFixed(1)} MW`
          : ''
        const body = `${id.toUpperCase()}: synchronised to bus${mwPart} — online and generating.`
        setAtRestLog(p => [...p, { ts, body }])
      }

      prevTurbineStatesRef.current[id] = state
    }
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
            Step-load absorbed — staged {stagedSecs}s ahead.
          </div>
          <div style={_BODY}>
            System returned to rest.
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
            <div style={{ ..._BODY, color: accent, whiteSpace: 'normal' }}>
              {`${secs} s until racks reach full draw +${predicted.toFixed(1)} MW · ${
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
            <div style={{ ..._BODY, color: accent, whiteSpace: 'normal' }}>
              {`${secs} s until racks reach full draw +${predicted.toFixed(1)} MW · turbine ramping · BESS armed`}
            </div>
            <div style={{ ..._BODY, color: '#3fb6a8', fontWeight: 600 }}>Nothing required</div>
            {/* ── SCHEDULER FEED log (live during countdown) ────────────── */}
            {atRestLog.length > 0 && <>
              <div style={{ ..._RULE, marginTop: 2 }} />
              <div style={{
                display: 'flex', alignItems: 'center',
                justifyContent: 'space-between', marginBottom: -2,
              }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ ..._MONO, fontSize: 8, color: '#3a5a6a' }}>SCHEDULER FEED</span>
                  <InfoBtn id="scheduler-feed" />
                </span>
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
                {atRestLog.map((entry, i) => {
                  const isGcc    = entry.body.startsWith('GCC')
                  const isNewest = i === atRestLog.length - 1
                  const borderCol = isGcc
                    ? (isNewest ? 'rgba(224,164,88,0.75)' : 'rgba(224,164,88,0.30)')
                    : (isNewest ? '#2a5060' : '#1e2a36')
                  const textCol = isGcc
                    ? (isNewest ? '#e0a458' : '#7a6030')
                    : (isNewest ? '#7d9ab0' : '#4b5764')
                  return (
                    <div key={i} style={{
                      display: 'flex', flexDirection: 'column', gap: 1,
                      borderLeft: `2px solid ${borderCol}`,
                      paddingLeft: 6,
                    }}>
                      <span style={{ ..._MONO, fontSize: 8, color: '#3a5a6a', lineHeight: 1.4 }}>
                        {entry.ts}
                      </span>
                      <span style={{ ..._BODY, lineHeight: 1.5, color: textCol }}>
                        {entry.body}
                      </span>
                    </div>
                  )
                })}
              </div>
            </>}
          </>
        })()}

        {/* ── STATE 1: AT REST — scrolling event log ──────────────────── */}
        {!isLanded && !isRunning && <>
          {/* Title row: label + ⓘ + AI Summary button */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ ..._LABEL(accent), cursor: 'default' }}>
                SCHEDULER FEED
              </div>
              <InfoBtn id="scheduler-feed" />
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
          <div style={_RULE} />

          {/* AI Summary modal placeholder — actual portal is rendered below, outside all
              state guards, so it mounts regardless of which state (1/2/3/4) is active. */}
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
            {atRestLog.map((entry, i) => {
              const isGcc    = entry.body.startsWith('GCC')
              const isNewest = i === atRestLog.length - 1
              const borderCol = isGcc
                ? (isNewest ? 'rgba(224,164,88,0.75)' : 'rgba(224,164,88,0.30)')
                : (isNewest ? '#2a5060' : '#1e2a36')
              const textCol = isGcc
                ? (isNewest ? '#e0a458' : '#7a6030')
                : (isNewest ? '#7d9ab0' : '#4b5764')
              return (
                <div
                  key={i}
                  style={{
                    display: 'flex', flexDirection: 'column', gap: 1,
                    borderLeft: `2px solid ${borderCol}`,
                    paddingLeft: 6,
                  }}
                >
                  <span style={{ ..._MONO, fontSize: 8, color: '#3a5a6a', lineHeight: 1.4 }}>
                    {entry.ts}
                  </span>
                  <span style={{ ..._BODY, color: textCol, lineHeight: 1.5 }}>
                    {entry.body}
                  </span>
                </div>
              )
            })}
          </div>
        </>}

        {/* AI Summary modal — outside all state-conditional blocks so it mounts
            in State 1 (at-rest), State 2 (countdown) and State 3 (reserve-short).
            createPortal escapes the SVG foreignObject and renders into document.body. */}
        {showSummaryModal && (
          <SchedulerSummaryModal
            feedEntries={atRestLog as FeedEntry[]}
            tick={tick}
            solarRatedMw={solarRatedMw}
            onClose={() => setShowSummaryModal(false)}
          />
        )}

      </div>
    </foreignObject>
  )
}

export function PlantDiagram({ onNodeClick, compact, solarPreview, liveSolarMW, onSelectPowerSupply }: PlantDiagramProps) {
  const tick       = useTickStore(s => s.latestTick)
  const selectedId = useScenarioStore(s => s.selectedId)

  // Fetch scenario spec to determine which power supply sources are enabled.
  // This drives both the Fuel Cell tile visibility and the dynamic outline.
  interface SourceState { turbine: boolean; solar: boolean; bess: boolean; grid: boolean; fuelCell: boolean }
  const [sourceState, setSourceState] = useState<SourceState>(
    { turbine: true, solar: true, bess: true, grid: false, fuelCell: false }
  )
  useEffect(() => {
    if (!selectedId) {
      setSourceState({ turbine: true, solar: true, bess: true, grid: false, fuelCell: false })
      return
    }
    let cancelled = false
    fetch(`/scenarios/${selectedId}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (cancelled) return
        const spec = data?.spec ?? {}
        setSourceState({
          turbine:  (spec.turbine_units?.length  ?? 1) > 0,
          solar:    (spec.solar_rated_mw          ?? 1) > 0,
          bess:     (spec.bess_units?.length      ?? 1) > 0,
          grid:     !(spec.island_mode            ?? true),
          fuelCell: spec.fuel_cell_enabled        ?? false,
        })
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [selectedId])

  const fuelCellEnabled = sourceState.fuelCell

  // ── Dynamic outline geometry ───────────────────────────────────────────────
  // Fixed y/h for each source node in SVG coordinate space.
  const SOURCE_NODE_GEOM = [
    { key: 'turbine',  y: 10,  h: 88 },
    { key: 'solar',    y: 110, h: 72 },
    { key: 'bess',     y: 210, h: 72 },
    { key: 'grid',     y: 310, h: 72 },
    { key: 'fuelCell', y: 392, h: 72 },
  ] as const

  const PAD = 6
  const enabledNodes = SOURCE_NODE_GEOM.filter(n => sourceState[n.key])
  // Fall back to full span when nothing is selected (avoids zero-height rect).
  const outlineTop    = enabledNodes.length > 0 ? enabledNodes[0].y - PAD : 4
  const outlineBottom = enabledNodes.length > 0
    ? enabledNodes[enabledNodes.length - 1].y + enabledNodes[enabledNodes.length - 1].h + PAD
    : 390
  const outlineX = -8
  const outlineY = outlineTop
  const outlineW = 171
  const outlineH = outlineBottom - outlineTop
  const tagY     = outlineY + outlineH - 1   // bar overlaps bottom border by 1 px for seamless join

  return (
    <svg
      viewBox={`0 0 ${DIAGRAM_W} ${DIAGRAM_H}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: '100%', height: '100%', display: 'block', overflow: 'visible' }}
      aria-label="Plant one-line mimic diagram"
    >
      <FlowMarkers />

      {/* ── Power supply selection outline ─────────────────────────────── */}
      {onSelectPowerSupply && (
        <>
          {/* Outline rect */}
          <rect
            x={outlineX} y={outlineY}
            width={outlineW} height={outlineH}
            rx={6} ry={6}
            fill="none"
            stroke="rgba(63,182,168,0.55)"
            strokeWidth={1.5}
          />
          {/* "Select Power" full-width footer bar — seamlessly joined to the outline rect */}
          <foreignObject x={outlineX} y={tagY} width={outlineW} height={26}>
            <div
              // @ts-expect-error — xmlns required for SVG foreignObject HTML
              xmlns="http://www.w3.org/1999/xhtml"
              style={{ width: '100%', height: '100%' }}
            >
              <button
                onClick={onSelectPowerSupply}
                style={{
                  width: '100%', height: '100%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  gap: 7,
                  fontFamily: "'JetBrains Mono',ui-monospace,monospace",
                  fontSize: 8, letterSpacing: '0.08em', fontWeight: 600,
                  color: 'rgba(63,182,168,0.85)',
                  background: '#0a0f16',
                  borderTop: '1px solid rgba(63,182,168,0.4)',
                  borderLeft: '1.5px solid rgba(63,182,168,0.55)',
                  borderRight: '1.5px solid rgba(63,182,168,0.55)',
                  borderBottom: '1.5px solid rgba(63,182,168,0.55)',
                  borderTopLeftRadius: 0, borderTopRightRadius: 0,
                  borderBottomLeftRadius: 5, borderBottomRightRadius: 5,
                  cursor: 'pointer',
                  transition: 'color 0.15s, background 0.15s',
                  boxSizing: 'border-box',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.color = '#3fb6a8'
                  e.currentTarget.style.background = 'rgba(63,182,168,0.07)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.color = 'rgba(63,182,168,0.85)'
                  e.currentTarget.style.background = '#0a0f16'
                }}
              >
                <span style={{
                  width: 7, height: 7, borderRadius: '50%',
                  border: '1.5px solid currentColor',
                  display: 'inline-block', flexShrink: 0,
                }} />
                Select Power
              </button>
            </div>
          </foreignObject>
        </>
      )}

      {/* ── Flow lines (behind nodes) ───────────────────────────────────── */}
      {FLOWS.filter(flow => {
        // Hide source-side flows whose supply tile is de-selected.
        const flowSourceMap: Record<string, keyof typeof sourceState> = {
          'gas-to-sw':   'turbine',
          'solar-to-sw': 'solar',
          'battery-to-sw': 'bess',
          'grid-to-sw':  'grid',
        }
        const sk = flowSourceMap[flow.id]
        return sk === undefined || sourceState[sk]
      }).map(flow => (
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
      {/* Fuel Cell flow — only when scenario enables it */}
      {fuelCellEnabled && (
        <FlowLine
          key={FUEL_CELL_FLOW.id}
          d={FUEL_CELL_FLOW.d}
          mwValue={0}
          maxMW={FUEL_CELL_FLOW.maxMW}
          color={FUEL_CELL_FLOW.color}
        />
      )}

      {/* ── Nodes ───────────────────────────────────────────────────────── */}
      {NODES.filter(node => {
        // Hide source tiles that the operator has de-selected in Power Supply Sources.
        // Non-source nodes (switchgear, distribution, PDU, racks, cooling) are always shown.
        const sourceKeyMap: Record<string, keyof typeof sourceState> = {
          'gas-turbine':    'turbine',
          'solar-pv':       'solar',
          'battery-bess':   'bess',
          'grid-connection': 'grid',
        }
        const sk = sourceKeyMap[node.id]
        return sk === undefined || sourceState[sk]
      }).map(node => (
        <PlantNode
          key={node.id}
          def={node}
          tick={tick}
          onClick={onNodeClick}
          solarPreview={node.id === 'solar-pv' ? solarPreview : null}
          liveSolarMW={liveSolarMW}
        />
      ))}
      {/* Fuel Cell Module Array tile — only when scenario enables it */}
      {fuelCellEnabled && (
        <PlantNode
          key="fuel-cell"
          def={FUEL_CELL_NODE}
          tick={tick}
          onClick={onNodeClick}
        />
      )}

      {/* ── Watching callout — centred between Gen & Compute ──────────── */}
      <WatchingCallout tick={tick} />

      {/* ── Lead-time callout ─────────────────────────────────────────── */}
      <LeadTimeCallout tick={tick} compact={compact} />
    </svg>
  )
}
