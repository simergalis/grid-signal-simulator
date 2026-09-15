/**
 * AlertDock.tsx — Capacity Alert tile and alert banner (§7.1 / §19.2).
 *
 * Shows two independent latched alerts:
 *   1. Insufficient reserve  — insufficient_reserve_alert flag from the backend.
 *   2. Power balance         — balance_alert flag (|generation − demand| > 0.5 MW).
 *
 * F4 — reads `latchedAlert` / `latchedBalanceAlert` from the store (NOT the
 * raw tick flags, which are true on only one tick and would flash for one frame).
 * The store latches on rising edge and clears after a successful disposition.
 */

import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useTickStore } from '../store/tickStore'
import {
  deriveRollingShortfall,
  formatPlanningTime,
  type PlanningUrgency,
  type ReferenceForecastShape,
  type RollingShortfall,
} from '../alerts/rollingShortfall'

type RemediationRecommendation = {
  recommendation_id: string
  action: 'start' | 'trip'
  unit_id: string
  title: string
  rationale: string
  expected_impact_mw: number
  risk: string
  confidence: number
  valid: boolean
  validation_message: string
}

type RecommendationStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error'

type AlertEntry = {
  key: string
  type: 'reserve' | 'balance'
  title: string
  tickIndex: number
  simTimeSeconds: number
  summary: string
  handled: boolean
  telemetryFresh: boolean
}

type AlertReview = {
  key: string
  repeat_alert: boolean
  already_handled: boolean
  confidence: number
  rationale: string
}

type AlertCluster = {
  cluster_id: string
  alert_type: 'reserve' | 'balance'
  keys: string[]
  confidence: number
  reason: string
}

type ReferenceForecastRow = {
  day_of_year: number
  hour_of_day: number
  kubernetes_node_count: number
  slurm_node_count: number
  ray_rack_count: number
}

type ReferenceForecastDataset = {
  dataset_id: string
  display_name: string
  span_days: number
  source_filename: string
  created_at: string
}

type ReferenceForecastResponse = {
  dataset: ReferenceForecastDataset
  rows: ReferenceForecastRow[]
  row_count: number
  truncated: boolean
}

type ReferenceForecastDerivedRow = ReferenceForecastRow & {
  kubernetes_mw: number
  slurm_mw: number
  ray_mw: number
  total_mw: number
}

type ReferenceForecastRowsResponse = {
  rows: ReferenceForecastDerivedRow[]
  row_count: number
}

type ReferenceShapeStatus = 'idle' | 'loading' | 'ready' | 'unavailable'

const REFERENCE_FORECAST_ID = 'equinix-sj-2-52wk-v1'

function calendarDayOfYear(date: Date): number {
  return Math.floor(
    (Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) -
      Date.UTC(date.getFullYear(), 0, 1)) /
      86_400_000,
  ) + 1
}

async function fetchReferenceDay(
  dayOfYear: number,
): Promise<ReferenceForecastDerivedRow[]> {
  const params = new URLSearchParams({
    start_day: String(dayOfYear),
    start_hour: '0',
    end_day: String(dayOfYear),
    end_hour: '23',
  })
  const response = await fetch(
    `/api/reference-forecast/${REFERENCE_FORECAST_ID}/rows?${params.toString()}`,
    { credentials: 'include', cache: 'no-store' },
  )
  if (!response.ok) throw new Error(`Reference forecast range failed (${response.status})`)
  const body = await response.json() as ReferenceForecastRowsResponse
  if (!Array.isArray(body.rows) || body.rows.length === 0) {
    throw new Error('Reference forecast range returned no rows')
  }
  return body.rows
}

/**
 * Load the next four hours of the persisted Kubernetes workload shape.
 *
 * The reference API performs the canonical node → MW conversion. This helper
 * only maps the same "today" convention as the baseline viewer and linearly
 * resamples the hourly values into the rolling chart's 15-minute slots.
 */
async function loadReferenceForecastShape(): Promise<ReferenceForecastShape> {
  const metadataResponse = await fetch(
    `/api/reference-forecast/${REFERENCE_FORECAST_ID}`,
    { credentials: 'include', cache: 'no-store' },
  )
  if (!metadataResponse.ok) {
    throw new Error(`Reference forecast metadata failed (${metadataResponse.status})`)
  }
  const metadata = await metadataResponse.json() as ReferenceForecastResponse
  const spanDays = metadata.dataset?.span_days
  if (!Number.isInteger(spanDays) || spanDays < 1) {
    throw new Error('Reference forecast has an invalid span')
  }

  const now = new Date()
  const mappedToday = ((calendarDayOfYear(now) - 1) % spanDays) + 1
  const nextDay = mappedToday === spanDays ? 1 : mappedToday + 1
  const [todayRows, nextDayRows] = await Promise.all([
    fetchReferenceDay(mappedToday),
    nextDay === mappedToday ? Promise.resolve([]) : fetchReferenceDay(nextDay),
  ])
  const rowsByKey = new Map<string, ReferenceForecastDerivedRow>(
    [...todayRows, ...nextDayRows].map(row => [
      `${row.day_of_year}:${row.hour_of_day}`,
      row,
    ]),
  )

  const startHour = now.getHours()
  const hourlyWorkload: number[] = []
  for (let offset = 0; offset <= 4; offset += 1) {
    const absoluteHour = startHour + offset
    const dayOffset = Math.floor(absoluteHour / 24)
    const hour = absoluteHour % 24
    const day = ((mappedToday - 1 + dayOffset) % spanDays) + 1
    const row = rowsByKey.get(`${day}:${hour}`)
    if (!row || !Number.isFinite(row.kubernetes_mw)) {
      throw new Error(`Reference forecast is missing day ${day}, hour ${hour}`)
    }
    hourlyWorkload.push(row.kubernetes_mw)
  }

  const points = Array.from({ length: 16 }, (_, index) => {
    const minutesFromNow = (index + 1) * 15
    const position = minutesFromNow / 60
    const left = Math.min(4, Math.floor(position))
    const right = Math.min(4, left + 1)
    const fraction = position - left
    const workloadMw = hourlyWorkload[left] +
      (hourlyWorkload[right] - hourlyWorkload[left]) * fraction
    return { minutesFromNow, workloadMw }
  })

  return {
    currentWorkloadMw: hourlyWorkload[0],
    points,
    sourceDetail: `${metadata.dataset.display_name} · Kubernetes workload · mapped day ${mappedToday}, ${String(startHour).padStart(2, '0')}:00 local`,
  }
}

export function AlertDock({ onOpenSubsystem }: { onOpenSubsystem?: (nodeId: string) => void }) {
  const tick                   = useTickStore(s => s.latestTick)
  const latchedAlert           = useTickStore(s => s.latchedAlert)
  const latchedBalanceAlert    = useTickStore(s => s.latchedBalanceAlert)
  const acknowledge            = useTickStore(s => s.acknowledgeAlert)
  const acknowledgeBalance     = useTickStore(s => s.acknowledgeBalanceAlert)
  const markOperatorAction     = useTickStore(s => s.markOperatorAction)
  const [reviewBusy, setReviewBusy] = useState(false)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [recommendations, setRecommendations] = useState<RemediationRecommendation[]>([])
  const [recommendBusy, setRecommendBusy] = useState(false)
  const [recommendationStatus, setRecommendationStatus] = useState<RecommendationStatus>('idle')
  const [executeBusy, setExecuteBusy] = useState<string | null>(null)
  const [actionResult, setActionResult] = useState<string | null>(null)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [alertEntries, setAlertEntries] = useState<AlertEntry[]>([])
  const [alertReviews, setAlertReviews] = useState<AlertReview[]>([])
  const [alertClusters, setAlertClusters] = useState<AlertCluster[]>([])
  const [bulkDispositionAllowList, setBulkDispositionAllowList] = useState<string[]>([])
  const [reviewAlertsBusy, setReviewAlertsBusy] = useState(false)
  const [reviewAlertsError, setReviewAlertsError] = useState<string | null>(null)
  const [bulkDispositionBusy, setBulkDispositionBusy] = useState<string | null>(null)
  const [referenceShape, setReferenceShape] = useState<ReferenceForecastShape | null>(null)
  const [referenceShapeStatus, setReferenceShapeStatus] = useState<ReferenceShapeStatus>('idle')
  const rollingShortfall = deriveRollingShortfall(tick, referenceShape)

  const showReserve = latchedAlert !== null
  const showBalance = latchedBalanceAlert !== null
  const showAny     = showReserve || showBalance
  const reserveEventKey = latchedAlert
    ? `reserve-${latchedAlert.tick_index}`
    : null
  const balanceEventKey = latchedBalanceAlert
    ? `balance-${latchedBalanceAlert.tick_index}`
    : null

  useEffect(() => {
    setAlertEntries([])
    setAlertReviews([])
    setAlertClusters([])
    setBulkDispositionAllowList([])
    setReviewAlertsError(null)
  }, [tick?.run_id])

  useEffect(() => {
    const runId = tick?.run_id
    let cancelled = false
    setReferenceShape(null)
    if (!runId) {
      setReferenceShapeStatus('idle')
      return
    }

    const load = async () => {
      setReferenceShapeStatus('loading')
      try {
        const shape = await loadReferenceForecastShape()
        if (!cancelled) {
          setReferenceShape(shape)
          setReferenceShapeStatus('ready')
        }
      } catch {
        if (!cancelled) {
          setReferenceShape(null)
          setReferenceShapeStatus('unavailable')
        }
      }
    }
    void load()
    const refreshTimer = window.setInterval(() => void load(), 15 * 60 * 1000)
    return () => {
      cancelled = true
      window.clearInterval(refreshTimer)
    }
  }, [tick?.run_id])

  useEffect(() => {
    if (!latchedAlert) return
    const entry: AlertEntry = {
      key: `reserve-${latchedAlert.tick_index}`,
      type: 'reserve',
      title: 'Insufficient reserve',
      tickIndex: latchedAlert.tick_index,
      simTimeSeconds: latchedAlert.sim_time_seconds,
      summary: 'BESS fleet cannot sustain the current shortfall for the full ramp-gap duration.',
      handled: false,
      telemetryFresh: true,
    }
    setAlertEntries(current => current.some(item => item.key === entry.key)
      ? current
      : [...current, entry])
  }, [latchedAlert?.tick_index])

  useEffect(() => {
    if (!latchedBalanceAlert) return
    const entry: AlertEntry = {
      key: `balance-${latchedBalanceAlert.tick_index}`,
      type: 'balance',
      title: 'Power balance mismatch',
      tickIndex: latchedBalanceAlert.tick_index,
      simTimeSeconds: latchedBalanceAlert.sim_time_seconds,
      summary: 'Generation and demand are outside the permitted operating balance.',
      handled: false,
      telemetryFresh: true,
    }
    setAlertEntries(current => current.some(item => item.key === entry.key)
      ? current
      : [...current, entry])
  }, [latchedBalanceAlert?.tick_index])

  // A latch is deliberately persistent, but the modal should open only when
  // a new alert event arrives—not on every render after the operator closes it.
  useEffect(() => {
    if (reserveEventKey || balanceEventKey) setIsModalOpen(true)
    setRecommendations([])
    setRecommendationStatus('idle')
  }, [reserveEventKey, balanceEventKey])

  useEffect(() => {
    const onUnitCommand = (event: Event) => {
      const detail = (event as CustomEvent<{ runId?: string; unitId?: string; action?: string }>).detail
      if (detail?.action !== 'trip' || !detail.runId || !tick || detail.runId !== tick.run_id) return
      const unitLabel = detail.unitId || 'the turbine'
      const unit = tick.turbine_units?.find(candidate => candidate.asset_id === detail.unitId)
      const isStandbyRelease = unit?.state === 'offline' && unit.hot_standby
      setActionResult(isStandbyRelease
        ? `Operator action accepted: ${unitLabel} was released from hot standby and synchronization is queued. The next tick will confirm the new operating state.`
        : `Operator action accepted: ${unitLabel} trip is queued. The next tick will confirm the new operating state.`)
      setRecommendations([])
      markOperatorAction({
        runId: detail.runId,
        action: detail.action,
        unitId: unitLabel,
        tickIndex: tick?.tick_index ?? 0,
      })
      if (latchedBalanceAlert) acknowledgeBalance(latchedBalanceAlert.tick_index)
      if (latchedAlert) acknowledge(latchedAlert.tick_index)
      setIsModalOpen(false)
    }
    window.addEventListener('gridsignal:unit-command', onUnitCommand)
    return () => window.removeEventListener('gridsignal:unit-command', onUnitCommand)
  }, [acknowledge, acknowledgeBalance, latchedAlert, latchedBalanceAlert, markOperatorAction, tick?.run_id, tick?.tick_index])

  const reviewReserve = async (decision: 'accept' | 'reject') => {
    const alert = latchedAlert
    const proposalId = alert?.insufficient_reserve_proposal_id
    if (!alert || !proposalId) {
      setReviewError('No advisory proposal is associated with this alert.')
      return
    }
    setReviewBusy(true)
    setReviewError(null)
    try {
      const userResponse = await fetch('/api/auth/me', { credentials: 'include' })
      if (!userResponse.ok) throw new Error(`Unable to identify reviewer (${userResponse.status})`)
      const user = await userResponse.json() as { email?: string; display_name?: string }
      const reviewerId = user.email || user.display_name
      if (!reviewerId) throw new Error('Authenticated reviewer identity is unavailable')
      const response = await fetch(`/proposals/${proposalId}/${decision}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(
          decision === 'accept'
            ? { reviewer_id: reviewerId }
            : {
                reason: 'Operator rejected insufficient reserve recommendation',
                reviewer_id: reviewerId,
              },
        ),
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || `Proposal review failed (${response.status})`)
      acknowledge(alert.tick_index)
      setIsModalOpen(false)
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : 'Proposal review failed')
    } finally {
      setReviewBusy(false)
    }
  }

  const getReviewer = async () => {
    const response = await fetch('/api/auth/me', { credentials: 'include' })
    if (!response.ok) throw new Error(`Unable to identify reviewer (${response.status})`)
    const user = await response.json() as { email?: string; display_name?: string }
    const reviewer = user.email || user.display_name
    if (!reviewer) throw new Error('Authenticated reviewer identity is unavailable')
    return reviewer
  }

  const requestRecommendations = async () => {
    const alert = showBalance ? latchedBalanceAlert : latchedAlert
    const runId = alert?.run_id
    if (!alert || !runId) {
      setReviewError('No live alert telemetry is available.')
      setRecommendationStatus('error')
      return
    }
    setRecommendBusy(true)
    setRecommendationStatus('loading')
    setReviewError(null)
    setActionResult(null)
    try {
      const response = await fetch('/api/ai/remediation/recommend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: runId,
          tick_index: alert.tick_index,
          alert_type: showReserve ? 'reserve' : 'balance',
          telemetry: alert,
        }),
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || `Recommendation request failed (${response.status})`)
      const nextRecommendations = body.recommendations || []
      setRecommendations(nextRecommendations)
      const hasValidRecommendation = nextRecommendations.some(
        (recommendation: RemediationRecommendation) => recommendation.valid !== false,
      )
      setRecommendationStatus(hasValidRecommendation ? 'ready' : 'empty')
      if (!nextRecommendations.length) {
        setReviewError('No valid turbine action is feasible at this tick; the simulator blocked the model alternatives.')
      }
    } catch (error) {
      setRecommendationStatus('error')
      setReviewError(error instanceof Error ? error.message : 'Recommendation request failed')
    } finally {
      setRecommendBusy(false)
    }
  }

  const implementRecommendation = async (recommendation: RemediationRecommendation) => {
    setExecuteBusy(recommendation.recommendation_id)
    setReviewError(null)
    try {
      const reviewer = await getReviewer()
      const response = await fetch('/api/ai/remediation/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recommendation_id: recommendation.recommendation_id,
          reviewer_id: reviewer,
        }),
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || `Implementation blocked (${response.status})`)
      const currentAlert = showBalance ? latchedBalanceAlert : latchedAlert
      const beforeImbalanceValue = currentAlert?.p_imbalance_mw
      const beforeImbalance = typeof beforeImbalanceValue === 'number'
        ? Math.abs(beforeImbalanceValue)
        : 0
      setActionResult(`${body.message} Audit ${body.audit_id}.`)
      setRecommendations([])
      if (showBalance) acknowledgeBalance(latchedBalanceAlert!.tick_index)
      if (showReserve) acknowledge(latchedAlert!.tick_index)
      setIsModalOpen(false)
      window.setTimeout(async () => {
        try {
          const tickResponse = await fetch(`/runs/${encodeURIComponent(body.run_id)}/latest-tick`)
          const nextTick = await tickResponse.json() as { p_imbalance_mw?: number }
          const afterImbalanceValue = nextTick.p_imbalance_mw
          if (typeof afterImbalanceValue === 'number') {
            const afterImbalance = Math.abs(afterImbalanceValue)
            const change = beforeImbalance - afterImbalance
            setActionResult(
              `Command result: imbalance is ${afterImbalanceValue >= 0 ? '+' : ''}${afterImbalanceValue.toFixed(2)} MW ` +
              `(absolute mismatch ${change >= 0 ? 'improved' : 'increased'} by ${Math.abs(change).toFixed(2)} MW). ` +
              `Audit ${body.audit_id}.`,
            )
          }
        } catch {
          // Keep the queued result visible if the run has already ended.
        }
      }, 4000)
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : 'Implementation failed')
    } finally {
      setExecuteBusy(null)
    }
  }

  const setAlertHandled = (entry: AlertEntry, handled: boolean) => {
    const telemetryFresh = Boolean(
      tick && tick.run_id === (showBalance ? latchedBalanceAlert?.run_id : latchedAlert?.run_id)
      && tick.tick_index === entry.tickIndex,
    )
    const nextHandled = handled
    setAlertEntries(current => current.map(item =>
      item.key === entry.key ? { ...item, handled: nextHandled, telemetryFresh } : item,
    ))
    void (async () => {
      try {
        const response = await fetch('/api/ai/alert-dispositions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            run_id: tick?.run_id,
            alert_key: entry.key,
            alert_type: entry.type,
            tick_index: entry.tickIndex,
            telemetry_fresh: telemetryFresh,
            disposition: handled ? 'handled' : 'not_handled',
          }),
        })
        const body = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(body.detail || `Disposition failed (${response.status})`)
        if (handled) {
          if (entry.type === 'reserve') acknowledge(entry.tickIndex)
          if (entry.type === 'balance') acknowledgeBalance(entry.tickIndex)
        }
      } catch (error) {
        setReviewError(error instanceof Error ? error.message : 'Disposition failed')
        setAlertEntries(current => current.map(item =>
          item.key === entry.key ? { ...item, handled: entry.handled } : item,
        ))
      }
    })()
  }

  useEffect(() => {
    setAlertEntries(current => current.map(entry => ({
      ...entry,
      telemetryFresh: Boolean(tick && tick.tick_index === entry.tickIndex),
    })))
  }, [tick?.tick_index])

  const reviewAlertHistory = async () => {
    if (!tick || alertEntries.length === 0) {
      setReviewAlertsError('No alert history is available to review.')
      return
    }
    setReviewAlertsBusy(true)
    setReviewAlertsError(null)
    try {
      const response = await fetch('/api/ai/review-alerts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: tick.run_id, entries: alertEntries }),
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || `Alert review failed (${response.status})`)
      setAlertReviews(body.reviews || [])
      setAlertClusters(body.clusters || [])
      setBulkDispositionAllowList(body.bulk_disposition_allow_list || [])
    } catch (error) {
      setReviewAlertsError(error instanceof Error ? error.message : 'Alert review failed')
    } finally {
      setReviewAlertsBusy(false)
    }
  }

  const bulkDisposition = async (cluster: AlertCluster) => {
    const instances = cluster.keys
      .map(key => alertEntries.find(entry => entry.key === key))
      .filter((entry): entry is AlertEntry => Boolean(entry))
    if (instances.some(entry => !entry.telemetryFresh)) {
      setReviewAlertsError('Bulk disposition blocked: at least one cluster instance has stale telemetry.')
      return
    }
    setBulkDispositionBusy(cluster.cluster_id)
    setReviewAlertsError(null)
    try {
      const response = await fetch('/api/ai/alert-dispositions/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: tick?.run_id,
          cluster_id: cluster.cluster_id,
          alert_type: cluster.alert_type,
          proposal_reason: cluster.reason,
          instances: instances.map(entry => ({
            alert_key: entry.key,
            alert_type: entry.type,
            tick_index: entry.tickIndex,
            telemetry_fresh: entry.telemetryFresh,
          })),
        }),
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || `Bulk disposition failed (${response.status})`)
      setAlertEntries(current => current.map(entry =>
        cluster.keys.includes(entry.key) ? { ...entry, handled: true } : entry,
      ))
      setActionResult(`Bulk disposition recorded for ${body.count} alert instances. Batch ${body.batch_reference}.`)
      setBulkDispositionBusy(null)
    } catch (error) {
      setReviewAlertsError(error instanceof Error ? error.message : 'Bulk disposition failed')
    } finally {
      setBulkDispositionBusy(null)
    }
  }

  if (!showAny) {
    return (
      <section
        className="min-w-0 flex h-full min-h-0 flex-col gap-1 overflow-hidden p-3 cursor-pointer"
        onClick={event => {
          if (!(event.target as HTMLElement).closest('button')) setDetailsOpen(true)
        }}
      >
          <div className="min-w-0 truncate font-mono text-[10px] uppercase tracking-wider text-muted" title="Capacity Alerts">
          Capacity Alerts
        </div>
        <div className="min-h-0 flex flex-1 flex-col items-center justify-center rounded border border-border/80
                        bg-canvas/40 px-2 py-1.5 text-center">
          {actionResult && (
            <div className="mb-3 w-full rounded border border-teal-500/40 bg-teal-500/5 p-3 text-left">
              <div className="font-mono text-[10px] uppercase tracking-wider text-teal-300">Remediation result</div>
              <div className="mt-1 font-mono text-xs leading-relaxed text-surface-fg">{actionResult}</div>
            </div>
          )}
          <div className="font-mono text-xl leading-none text-muted/50">—</div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-wider text-muted">
            {tick ? 'No active alerts' : 'No active run'}
          </div>
          <div className="mt-1 font-mono text-[9px] leading-tight text-muted/70">
            Start a scenario to monitor capacity
          </div>
        </div>
        {detailsOpen && (
          <AlertDetailsModal
            entries={alertEntries}
            actionResult={actionResult}
            rollingShortfall={rollingShortfall}
            referenceShapeStatus={referenceShapeStatus}
            reviews={alertReviews}
            clusters={alertClusters}
            reviewBusy={reviewAlertsBusy}
            reviewError={reviewAlertsError}
            onReview={reviewAlertHistory}
            onBulkDisposition={bulkDisposition}
            bulkDispositionBusy={bulkDispositionBusy}
            bulkDispositionAllowList={bulkDispositionAllowList}
            onToggle={setAlertHandled}
            activeAlert={showAny}
            recommendations={recommendations}
            recommendationStatus={recommendationStatus}
            recommendationBusy={recommendBusy}
            onRequestRecommendations={() => void requestRecommendations()}
            onResolveRecommendation={() => {
              setDetailsOpen(false)
              onOpenSubsystem?.('gas-turbine')
            }}
            onClose={() => setDetailsOpen(false)}
          />
        )}
      </section>
    )
  }

  return (
    <section
      className="min-w-0 flex h-full flex-col gap-3 overflow-x-hidden overflow-y-auto p-4 cursor-pointer"
      onClick={event => {
        if (!(event.target as HTMLElement).closest('button')) setDetailsOpen(true)
      }}
    >
      <div className="min-w-0 truncate font-mono text-xs uppercase tracking-wider text-muted" title="Capacity Alerts">
        Capacity Alerts
      </div>

      {/* ── Insufficient reserve ─────────────────────────────────────────── */}
      {showReserve && (
        <div className="rounded border border-warn/60 bg-warn/10 p-3 space-y-2">
          <div className="flex items-start gap-2">
            <span className="text-warn text-lg leading-none mt-0.5">⚠</span>
            <div className="space-y-0.5">
              <div className="font-mono text-sm font-semibold text-warn">
                Insufficient reserve
              </div>
              <div className="font-mono text-xs text-warn/70">
                Alert fired at tick #{latchedAlert!.tick_index}
                {' · '}
                sim time{' '}
                {latchedAlert!.sim_time_seconds.toFixed(0)} s
              </div>
            </div>
          </div>
          <div className="font-mono text-xs text-muted leading-relaxed">
            BESS fleet cannot sustain the current shortfall for the full ramp-gap
            duration. Stage additional turbine capacity or shed non-critical load.
          </div>
          {!isModalOpen && (
            <div className="flex gap-2 pt-1">
              <button
                onClick={() => void reviewReserve('accept')}
                disabled={reviewBusy}
                className="flex-1 rounded bg-green-700 px-3 py-2 font-mono text-sm font-semibold
                           text-white transition-colors hover:bg-green-600 active:scale-95 disabled:opacity-50"
              >
                Approve
              </button>
              <button
                onClick={() => void reviewReserve('reject')}
                disabled={reviewBusy}
                className="flex-1 rounded bg-red-700 px-3 py-2 font-mono text-sm font-semibold
                           text-white transition-colors hover:bg-red-600 active:scale-95 disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          )}
          {reviewError && <p className="font-mono text-[10px] text-red-300">{reviewError}</p>}
        </div>
      )}

      {/* ── Power balance ────────────────────────────────────────────────── */}
      {showBalance && (() => {
        const t = latchedBalanceAlert!
        const imbalance = typeof t.p_imbalance_mw === 'number'
          ? t.p_imbalance_mw
          : null
        const isDeficit = imbalance !== null && imbalance < 0
        return (
          <div className="rounded border border-warn/60 bg-warn/10 p-3 space-y-2">
            <div className="flex items-start gap-2">
              <span className="text-warn text-lg leading-none mt-0.5">⚡</span>
              <div className="space-y-0.5">
                <div className="font-mono text-sm font-semibold text-warn">
                  Power balance mismatch
                </div>
                <div className="font-mono text-xs text-warn/70">
                  Alert fired at tick #{t.tick_index}
                  {' · '}
                  sim time {t.sim_time_seconds.toFixed(0)} s
                </div>
              </div>
            </div>
            <div className="font-mono text-xs text-muted leading-relaxed space-y-1">
              <div>
                <span className="text-surface-fg">Produced:</span>{' '}
                <span className="text-teal-400">{t.p_generation_mw.toFixed(2)} MW</span>
                {'  '}
                <span className="text-surface-fg">Consumed:</span>{' '}
                <span className="text-warn">{t.p_demand_mw.toFixed(2)} MW</span>
              </div>
              <div>
                Imbalance:{' '}
                <span className={isDeficit ? 'text-warn font-semibold' : 'text-teal-400 font-semibold'}>
                  {imbalance === null
                    ? 'unavailable'
                    : `${imbalance >= 0 ? '+' : ''}${imbalance.toFixed(2)} MW`}
                </span>
                {' '}({isDeficit ? 'deficit — generation below demand' : 'surplus — generation above demand'})
              </div>
            </div>
            <div className="space-y-1 pt-1">
              <button
                onClick={() => void requestRecommendations()}
                disabled={recommendBusy}
                className="w-full rounded border border-teal-500/70 px-4 py-2 font-mono text-sm font-semibold
                           text-teal-300 transition-colors hover:bg-teal-500/10 disabled:opacity-50"
              >
                {recommendBusy ? 'Evaluating safe actions…' : 'Ask Gridley for safe actions'}
              </button>
              <button
                onClick={() => {
                  acknowledgeBalance(t.tick_index)
                  setIsModalOpen(false)
                }}
                className="w-full rounded bg-warn px-4 py-2 font-mono text-sm font-semibold
                           text-canvas transition-colors hover:bg-warn/80 active:scale-95"
              >
                Acknowledge
              </button>
              <p className="font-mono text-[10px] text-muted text-center">
                Local dismissal only — persistent ack deferred to Step 8.
              </p>
            </div>
          </div>
        )
      })()}
      {isModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Capacity alert requires operator action"
          className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/75 px-4"
          onClick={event => {
            if (event.target === event.currentTarget) setIsModalOpen(false)
          }}
        >
          <div className="w-full max-w-xl overflow-hidden rounded-lg border-2 border-warn
                          bg-[#111821] shadow-[0_0_40px_rgba(240,136,62,0.25)]">
            <div className="flex items-start gap-3 border-b border-warn/30 bg-warn/10 px-5 py-4">
              <span className="mt-0.5 text-2xl leading-none text-warn" aria-hidden="true">⚠</span>
              <div className="min-w-0 flex-1">
                <div className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-warn">
                  Immediate operator action required
                </div>
                <h2 className="mt-1 font-mono text-xl font-semibold text-surface-fg">
                  Operator action required
                </h2>
              </div>
              <button
                type="button"
                aria-label="Close capacity alert"
                onClick={() => setIsModalOpen(false)}
                className="rounded px-2 py-1 font-mono text-xl leading-none text-muted
                           transition-colors hover:bg-warn/20 hover:text-surface-fg"
              >
                ×
              </button>
            </div>

            <div className="space-y-4 px-5 py-5">
              {(() => {
                const summaryTick = showBalance ? latchedBalanceAlert : latchedAlert
                const formatMw = (value: number | null | undefined) =>
                  typeof value === 'number' ? `${value.toFixed(2)} MW` : '—'
                return (
              <div className="grid grid-cols-2 gap-2 rounded border border-border/80 bg-canvas/40 p-3 font-mono text-xs">
                <div><span className="text-muted">Generation</span><div className="text-teal-300">{formatMw(summaryTick?.p_generation_mw)}</div></div>
                <div><span className="text-muted">Demand</span><div className="text-warn">{formatMw(summaryTick?.p_demand_mw)}</div></div>
                <div><span className="text-muted">Imbalance</span><div className="text-surface-fg">{formatMw(summaryTick?.p_imbalance_mw)}</div></div>
                <div><span className="text-muted">BESS SoC</span><div className="text-surface-fg">{(((showBalance ? latchedBalanceAlert : latchedAlert)?.bess_soc_fraction ?? 0) * 100).toFixed(1)}%</div></div>
              </div>
                )
              })()}
              {showReserve && (
                <div className="space-y-2">
                  <div className="font-mono text-base font-semibold text-warn">
                    Reserve capacity cannot cover the predicted shortfall
                  </div>
                  <p className="font-mono text-sm leading-relaxed text-muted">
                    The BESS fleet cannot sustain the current shortfall for the full
                    ramp-gap duration. Stage additional turbine capacity or shed
                    non-critical load now.
                  </p>
                  <div className="font-mono text-xs text-warn/70">
                    Fired at tick #{latchedAlert!.tick_index}
                    {' · '}
                    simulated time {latchedAlert!.sim_time_seconds.toFixed(0)}s
                  </div>
                </div>
              )}

              {!showReserve && showBalance && (
                <div className="space-y-2">
                  <div className="font-mono text-base font-semibold text-warn">
                    Power balance mismatch detected
                  </div>
                  <p className="font-mono text-sm leading-relaxed text-muted">
                    Generation and demand are outside the permitted operating
                    balance. Review the live dispatch state immediately.
                  </p>
                  <div className="font-mono text-xs text-warn/70">
                    Fired at tick #{latchedBalanceAlert!.tick_index}
                    {' · '}
                    simulated time {latchedBalanceAlert!.sim_time_seconds.toFixed(0)}s
                  </div>
                </div>
              )}

              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded border border-border px-4 py-2 font-mono text-sm text-muted
                             transition-colors hover:border-warn/60 hover:text-surface-fg"
                >
                  Review in dashboard
                </button>
                {showReserve && (
                  <>
                    <button
                      type="button"
                      onClick={() => void reviewReserve('reject')}
                      disabled={reviewBusy}
                      className="rounded bg-red-700 px-4 py-2 font-mono text-sm font-semibold
                                 text-white transition-colors hover:bg-red-600 disabled:opacity-50"
                    >
                      Reject recommendation
                    </button>
                    <button
                      type="button"
                      onClick={() => void reviewReserve('accept')}
                      disabled={reviewBusy}
                      className="rounded bg-green-700 px-4 py-2 font-mono text-sm font-semibold
                                 text-white transition-colors hover:bg-green-600 disabled:opacity-50"
                    >
                      Approve recommendation
                    </button>
                  </>
                )}
                {showBalance && !showReserve && (
                  <button
                    type="button"
                    onClick={() => {
                      acknowledgeBalance(latchedBalanceAlert!.tick_index)
                      setIsModalOpen(false)
                    }}
                    className="rounded bg-warn px-4 py-2 font-mono text-sm font-semibold
                               text-canvas transition-colors hover:bg-warn/80"
                  >
                    Acknowledge alert
                  </button>
                )}
              </div>
              <div className="space-y-2 border-t border-border/70 pt-3">
                <button
                  type="button"
                  onClick={() => void requestRecommendations()}
                  disabled={recommendBusy}
                  className="w-full rounded border border-teal-500/70 px-4 py-2 font-mono text-sm font-semibold
                             text-teal-300 transition-colors hover:bg-teal-500/10 disabled:opacity-50"
                >
                  {recommendBusy ? 'Evaluating safe actions…' : 'Evaluate safe alternatives'}
                </button>
                {recommendations.map(recommendation => (
                  <div key={recommendation.recommendation_id} className="rounded border border-teal-500/40 bg-teal-500/5 p-3">
                    <div className="font-mono text-sm font-semibold text-surface-fg">{recommendation.title}</div>
                    <div className="mt-1 font-mono text-xs text-muted">{recommendation.rationale}</div>
                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] text-muted">
                      <span>Expected {recommendation.expected_impact_mw.toFixed(2)} MW</span>
                      <span>Confidence {(recommendation.confidence * 100).toFixed(0)}%</span>
                    </div>
                    <div className="mt-1 font-mono text-[10px] text-warn/80">Risk: {recommendation.risk}</div>
                    {recommendation.valid ? (
                      <button
                        type="button"
                        onClick={() => void implementRecommendation(recommendation)}
                        disabled={executeBusy !== null}
                        className="mt-3 w-full rounded bg-teal-600 px-3 py-2 font-mono text-xs font-semibold text-canvas
                                   hover:bg-teal-500 disabled:opacity-50"
                      >
                        {executeBusy === recommendation.recommendation_id ? 'Validating and queuing…' : `Implement ${recommendation.action} command`}
                      </button>
                    ) : (
                      <div className="mt-2 font-mono text-[10px] text-red-300">Blocked: {recommendation.validation_message}</div>
                    )}
                  </div>
                ))}
              </div>
              {reviewError && (
                <p className="font-mono text-xs text-red-300">{reviewError}</p>
              )}
              {actionResult && (
                <p className="font-mono text-xs text-teal-300">{actionResult}</p>
              )}
            </div>
          </div>
        </div>
      )}
      {detailsOpen && (
        <AlertDetailsModal
          entries={alertEntries}
          actionResult={actionResult}
          rollingShortfall={rollingShortfall}
           referenceShapeStatus={referenceShapeStatus}
          reviews={alertReviews}
          clusters={alertClusters}
          reviewBusy={reviewAlertsBusy}
          reviewError={reviewAlertsError}
          onReview={reviewAlertHistory}
          onBulkDisposition={bulkDisposition}
          bulkDispositionBusy={bulkDispositionBusy}
          bulkDispositionAllowList={bulkDispositionAllowList}
          onToggle={setAlertHandled}
          activeAlert={showAny}
          recommendations={recommendations}
          recommendationStatus={recommendationStatus}
          recommendationBusy={recommendBusy}
          onRequestRecommendations={() => void requestRecommendations()}
          onResolveRecommendation={() => {
            setDetailsOpen(false)
            onOpenSubsystem?.('gas-turbine')
          }}
          onClose={() => setDetailsOpen(false)}
        />
      )}
    </section>
  )
}

function AlertDetailsModal({
  entries,
  actionResult,
  rollingShortfall,
  referenceShapeStatus,
  reviews,
  clusters,
  reviewBusy,
  reviewError,
  onReview,
  onBulkDisposition,
  bulkDispositionBusy,
  bulkDispositionAllowList,
  onToggle,
  activeAlert,
  recommendations,
  recommendationStatus,
  recommendationBusy,
  onRequestRecommendations,
  onResolveRecommendation,
  onClose,
}: {
  entries: AlertEntry[]
  actionResult: string | null
  rollingShortfall: RollingShortfall | null
  referenceShapeStatus: ReferenceShapeStatus
  reviews: AlertReview[]
  clusters: AlertCluster[]
  reviewBusy: boolean
  reviewError: string | null
  onReview: () => void
  onBulkDisposition: (cluster: AlertCluster) => void
  bulkDispositionBusy: string | null
  bulkDispositionAllowList: string[]
  onToggle: (entry: AlertEntry, handled: boolean) => void
  activeAlert: boolean
  recommendations: RemediationRecommendation[]
  recommendationStatus: RecommendationStatus
  recommendationBusy: boolean
  onRequestRecommendations: () => void
  onResolveRecommendation: () => void
  onClose: () => void
}) {
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set())
  const [baselineViewerOpen, setBaselineViewerOpen] = useState(false)
  const entriesByKey = new Map(entries.map(entry => [entry.key, entry]))
  const clusteredKeys = new Set(clusters.flatMap(cluster => cluster.keys))
  const renderEntry = (entry: AlertEntry) => (
    <label
      key={entry.key}
      className={`flex cursor-pointer items-start gap-4 rounded border p-4 transition-colors ${
        entry.handled
          ? 'border-teal-500/40 bg-teal-500/5'
          : 'border-warn/50 bg-warn/5'
      }`}
    >
      <input
        type="checkbox"
        checked={entry.handled}
        onChange={event => onToggle(entry, event.target.checked)}
        className="mt-1 h-5 w-5 accent-teal-500"
      />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline justify-between gap-2">
          <span className="font-mono text-base font-semibold text-text">{entry.title}</span>
          <span className={`font-mono text-xs uppercase tracking-wider ${entry.handled ? 'text-teal-300' : 'text-warn'}`}>
            {entry.handled ? 'Handled' : 'Not handled'}
          </span>
        </span>
        <span className="mt-1 block font-mono text-sm leading-relaxed text-muted">{entry.summary}</span>
        <span className="mt-2 block font-mono text-xs text-muted">
          Tick #{entry.tickIndex} · simulated time {entry.simTimeSeconds.toFixed(0)}s
        </span>
        {!entry.telemetryFresh && (
          <span className="mt-2 block font-mono text-xs font-semibold uppercase tracking-wider text-red-300">
            Stale telemetry — refresh live tick before disposition
          </span>
        )}
      </span>
    </label>
  )
  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/70 px-4"
      role="presentation"
      onClick={event => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Capacity alerts"
        className="relative flex max-h-[90vh] w-full max-w-[1120px] flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-2xl"
        onClick={event => event.stopPropagation()}
      >
        <div className="absolute inset-x-0 top-0 h-1 bg-[#f0883e]" />
        <div className="flex items-start justify-between px-7 pb-4 pt-7">
          <div>
            <h2 className="font-mono text-3xl font-bold tracking-wide text-text">CAPACITY ALERTS</h2>
            <p className="mt-1 font-mono text-sm text-muted">
              Operator review log · check alerts when the required action has been handled
            </p>
          </div>
          <div className="ml-4 flex items-start gap-3">
            <button
              type="button"
              onClick={() => setBaselineViewerOpen(true)}
              className="rounded border border-teal-500/60 px-3 py-2 font-mono text-xs font-semibold text-teal-300 hover:bg-teal-500/10"
            >
              View 52-week baseline
            </button>
            <button
              type="button"
              aria-label="Close"
              onClick={onClose}
              className="px-1 text-3xl leading-none text-muted hover:text-text"
            >
              ✕
            </button>
          </div>
        </div>
        <div className="mx-7 h-px bg-border" />
        <div className="flex-1 overflow-y-auto space-y-3 px-7 py-5">
          {actionResult && (
            <div className="rounded border border-teal-500/40 bg-teal-500/5 p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-teal-300">Latest operator action</div>
              <div className="mt-1 font-mono text-sm text-text">{actionResult}</div>
            </div>
          )}
          {activeAlert && (
            <section
              className="rounded border border-teal-500/40 bg-teal-500/5 p-3"
              data-testid="capacity-alert-recommendations"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-mono text-xs font-semibold uppercase tracking-wider text-teal-300">
                    Recommendations
                  </div>
                  <div className="mt-1 font-mono text-[10px] leading-relaxed text-muted">
                    Simulator-validated turbine actions for the currently latched alert.
                    Review the live fleet state before resolving.
                  </div>
                </div>
                <button
                  type="button"
                  onClick={onRequestRecommendations}
                  disabled={recommendationBusy}
                  className="rounded border border-teal-500/70 px-3 py-2 font-mono text-xs font-semibold text-teal-300 hover:bg-teal-500/10 disabled:opacity-40"
                >
                  {recommendationBusy ? 'Evaluating…' : 'Find safe actions'}
                </button>
              </div>
              {recommendationStatus === 'loading' && (
                <p className="mt-3 font-mono text-xs text-muted">Checking the latest simulator telemetry…</p>
              )}
              {recommendationStatus === 'ready' && (
                <div className="mt-3 space-y-2 border-t border-teal-500/20 pt-3">
                  {recommendations
                    .filter(recommendation => recommendation.valid !== false)
                    .map(recommendation => (
                      <div
                        key={recommendation.recommendation_id}
                        className="rounded border border-border/80 bg-canvas/40 p-3"
                      >
                        <div className="font-mono text-sm font-semibold text-text">{recommendation.title}</div>
                        <div className="mt-1 font-mono text-xs leading-relaxed text-muted">{recommendation.rationale}</div>
                        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] text-muted">
                          <span>Unit {recommendation.unit_id}</span>
                          <span>Expected {recommendation.expected_impact_mw.toFixed(2)} MW</span>
                          <span>Confidence {(recommendation.confidence * 100).toFixed(0)}%</span>
                        </div>
                        <div className="mt-1 font-mono text-[10px] text-warn/80">Risk: {recommendation.risk}</div>
                        <button
                          type="button"
                          onClick={onResolveRecommendation}
                          className="mt-3 w-full rounded bg-teal-600 px-3 py-2 font-mono text-xs font-semibold text-canvas hover:bg-teal-500"
                        >
                          Resolve in Gas Turbine Fleet
                        </button>
                      </div>
                    ))}
                </div>
              )}
              {recommendationStatus === 'empty' && (
                <p className="mt-3 border-t border-teal-500/20 pt-3 font-mono text-xs leading-relaxed text-muted">
                  No simulator-validated turbine action is feasible at this tick. Use human judgment and the live
                  plant controls to decide the next safe step.
                </p>
              )}
              {recommendationStatus === 'error' && (
                <p className="mt-3 border-t border-red-500/20 pt-3 font-mono text-xs leading-relaxed text-red-300">
                  {reviewError || 'Recommendations could not be evaluated. Use human judgment and review the live plant controls.'}
                </p>
              )}
            </section>
          )}
          <RollingPlanningSection
            projection={rollingShortfall}
            referenceShapeStatus={referenceShapeStatus}
          />
          <div className="rounded border border-border bg-canvas/40 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="font-mono text-xs font-semibold text-text">AI alert review</div>
                <div className="mt-1 font-mono text-[10px] text-muted">
                  Claude checks for repeats using this run’s alert history.
                </div>
              </div>
              <button
                type="button"
                onClick={onReview}
                disabled={reviewBusy || entries.length === 0}
                className="rounded border border-teal-500/70 px-3 py-2 font-mono text-xs font-semibold text-teal-300 hover:bg-teal-500/10 disabled:opacity-40"
              >
                {reviewBusy ? 'Reviewing…' : 'Review repeats'}
              </button>
            </div>
            {reviewError && <p className="mt-2 font-mono text-xs text-red-300">{reviewError}</p>}
            {reviews.length > 0 && (
              <div className="mt-3 space-y-2 border-t border-border pt-3">
                {reviews.map(review => (
                  <div key={review.key} className="rounded border border-border/70 px-3 py-2 font-mono text-[10px]">
                    <div className="flex flex-wrap justify-between gap-2 text-text">
                      <span>{review.key}</span>
                      <span className={review.already_handled ? 'text-teal-300' : review.repeat_alert ? 'text-amber-300' : 'text-muted'}>
                        {review.already_handled ? 'Already handled' : review.repeat_alert ? 'Likely repeat' : 'New alert'}
                      </span>
                    </div>
                    <div className="mt-1 text-muted">{review.rationale}</div>
                  </div>
                ))}
                <p className="font-mono text-[10px] text-muted">
                  AI review is advisory. Checkboxes remain under operator control.
                </p>
              </div>
            )}
          </div>
          {entries.length === 0 ? (
            <div className="rounded border border-border bg-canvas/40 px-4 py-10 text-center font-mono text-sm text-muted">
              No alerts recorded for this run.
            </div>
          ) : (
            <>
              {clusters.map(cluster => {
                const clusterEntries = cluster.keys
                  .map(key => entriesByKey.get(key))
                  .filter((entry): entry is AlertEntry => Boolean(entry))
                const expanded = expandedClusters.has(cluster.cluster_id)
                const bulkAllowed = bulkDispositionAllowList.includes(cluster.alert_type)
                return (
                  <section key={cluster.cluster_id} className="rounded border border-teal-500/40 bg-teal-500/5 p-3">
                    <div className="w-full text-left">
                    <button
                      type="button"
                      className="w-full text-left"
                      onClick={() => setExpandedClusters(current => {
                        const next = new Set(current)
                        if (next.has(cluster.cluster_id)) next.delete(cluster.cluster_id)
                        else next.add(cluster.cluster_id)
                        return next
                      })}
                      aria-expanded={expanded}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono text-sm font-semibold text-text">
                          {expanded ? '▾' : '▸'} {cluster.alert_type} cluster · {clusterEntries.length} alerts
                        </span>
                        <span className="font-mono text-xs text-teal-300">
                          {Math.round(cluster.confidence * 100)}% confidence
                        </span>
                      </div>
                      <div className="mt-1 font-mono text-xs text-muted">{cluster.reason}</div>
                    </button>
                    <div className="mt-2 font-mono text-[10px] text-muted">
                      {bulkAllowed
                        ? 'Bulk disposition is available for this catalogue-approved alert class.'
                        : 'Bulk disposition disabled: this alert class is not on the catalogue allow-list.'}
                    </div>
                    <button
                      type="button"
                      disabled={!bulkAllowed || bulkDispositionBusy === cluster.cluster_id || clusterEntries.some(entry => !entry.telemetryFresh)}
                      onClick={event => {
                        event.stopPropagation()
                        onBulkDisposition(cluster)
                      }}
                      className="mt-2 rounded border border-amber-500/60 px-2 py-1 font-mono text-[10px] font-semibold text-amber-300 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {bulkDispositionBusy === cluster.cluster_id ? 'Recording…' : 'Mark cluster handled'}
                    </button>
                    {clusterEntries.some(entry => !entry.telemetryFresh) && (
                      <div className="mt-1 font-mono text-[10px] text-red-300">
                        Disabled: every instance must have fresh telemetry.
                      </div>
                    )}
                    {expanded && <div className="mt-3 space-y-2 border-t border-border/60 pt-3">{clusterEntries.map(renderEntry)}</div>}
                    </div>
                  </section>
                )
              })}
              {entries.filter(entry => !clusteredKeys.has(entry.key)).map(renderEntry)}
            </>
          )}
        </div>
        <div className="flex justify-end border-t border-border px-7 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded bg-warn px-5 py-2 font-mono text-sm font-semibold text-canvas hover:bg-warn/80"
          >
            Close
          </button>
        </div>
      </div>
      {baselineViewerOpen && (
        <ReferenceForecastViewer onClose={() => setBaselineViewerOpen(false)} />
      )}
    </div>
  )
}

function ReferenceForecastViewer({ onClose }: { onClose: () => void }) {
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [dataset, setDataset] = useState<ReferenceForecastDataset | null>(null)
  const [rows, setRows] = useState<ReferenceForecastRow[]>([])
  const [domain, setDomain] = useState<'kubernetes_node_count' | 'slurm_node_count' | 'ray_rack_count'>('kubernetes_node_count')
  const [view, setView] = useState<'average' | 'day'>('day')
  const [daySelection, setDaySelection] = useState<'today' | number>('today')

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const response = await fetch('/api/reference-forecast/equinix-sj-2-52wk-v1', {
          credentials: 'include',
        })
        if (!response.ok) {
          throw new Error(`Baseline request failed (${response.status})`)
        }
        const body = await response.json() as ReferenceForecastResponse
        if (!cancelled) {
          setDataset(body.dataset)
          setRows(body.rows)
          setState('ready')
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Baseline request failed')
          setState('error')
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const domainLabel: Record<typeof domain, string> = {
    kubernetes_node_count: 'Kubernetes nodes',
    slurm_node_count: 'Slurm nodes',
    ray_rack_count: 'Ray racks',
  }
  const now = new Date()
  const calendarDayOfYear = Math.floor(
    (Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) -
      Date.UTC(now.getFullYear(), 0, 1)) /
      86_400_000,
  ) + 1
  const todayMappedDay = dataset
    ? ((calendarDayOfYear - 1) % dataset.span_days) + 1
    : 1
  const selectedDayOfYear = daySelection === 'today' ? todayMappedDay : daySelection
  const chartData = (() => {
    const source = view === 'day' ? rows.filter(row => row.day_of_year === selectedDayOfYear) : rows
    return Array.from({ length: 24 }, (_, hour) => {
      const points = source.filter(row => row.hour_of_day === hour)
      const total = points.reduce((sum, row) => sum + row[domain], 0)
      return {
        hour,
        label: `${String(hour).padStart(2, '0')}:00`,
        count: points.length ? total / points.length : 0,
      }
    })
  })()

  return (
    <div
      className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/80 px-4"
      role="presentation"
      onClick={event => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="52-week reference forecast baseline"
        className="relative flex max-h-[90vh] w-full max-w-[980px] flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-2xl"
        onClick={event => event.stopPropagation()}
      >
        <div className="absolute inset-x-0 top-0 h-1 bg-teal-500" />
        <div className="flex items-start justify-between gap-4 px-6 pb-4 pt-6">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-teal-300">
              Reference forecast baseline
            </div>
            <h2 className="mt-1 font-mono text-2xl font-bold tracking-wide text-text">
              52-WEEK WORKLOAD HISTORY
            </h2>
            <p className="mt-1 font-mono text-xs text-muted">
              Read-only view of the persisted hourly dataset · not used to change live forecasting
            </p>
          </div>
          <button
            type="button"
            aria-label="Close baseline viewer"
            onClick={onClose}
            className="px-1 text-3xl leading-none text-muted hover:text-text"
          >
            ✕
          </button>
        </div>
        <div className="mx-6 h-px bg-border" />
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {state === 'loading' && (
            <div className="flex min-h-[300px] items-center justify-center font-mono text-sm text-muted">
              Loading stored baseline…
            </div>
          )}
          {state === 'error' && (
            <div className="flex min-h-[300px] flex-col items-center justify-center gap-2 text-center">
              <p className="font-mono text-sm text-red-300">Unable to load the stored baseline</p>
              <p className="font-mono text-xs text-muted">{error}</p>
            </div>
          )}
          {state === 'ready' && dataset && rows.length === 0 && (
            <div className="flex min-h-[300px] items-center justify-center font-mono text-sm text-muted">
              The stored baseline contains no hourly rows.
            </div>
          )}
          {state === 'ready' && dataset && rows.length > 0 && (
            <>
              <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
                <div className="font-mono text-[10px] text-muted">
                  <div className="text-text">{dataset.display_name}</div>
                  <div className="mt-1">{dataset.span_days} days · {rows.length.toLocaleString()} hourly rows · {dataset.source_filename}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <label className="font-mono text-[10px] text-muted">
                    Domain
                    <select
                      value={domain}
                      onChange={event => setDomain(event.target.value as typeof domain)}
                      className="ml-2 rounded border border-border bg-canvas px-2 py-1 text-xs text-text"
                    >
                      <option value="kubernetes_node_count">Kubernetes nodes</option>
                      <option value="slurm_node_count">Slurm nodes</option>
                      <option value="ray_rack_count">Ray racks</option>
                    </select>
                  </label>
                  <label className="font-mono text-[10px] text-muted">
                    View
                    <select
                      value={view}
                      onChange={event => setView(event.target.value as typeof view)}
                      className="ml-2 rounded border border-border bg-canvas px-2 py-1 text-xs text-text"
                    >
                      <option value="average">Average by hour</option>
                      <option value="day">One day</option>
                    </select>
                  </label>
                  {view === 'day' && (
                    <label className="font-mono text-[10px] text-muted">
                      Day
                      <select
                        value={daySelection === 'today' ? 'today' : String(daySelection)}
                        onChange={event => {
                          setDaySelection(event.target.value === 'today' ? 'today' : Number(event.target.value))
                        }}
                        className="ml-2 rounded border border-border bg-canvas px-2 py-1 text-xs text-text"
                      >
                        <option value="today">
                          Today (mapped to Day {String(todayMappedDay).padStart(3, '0')})
                        </option>
                        {Array.from({ length: dataset.span_days }, (_, index) => (
                          <option key={index + 1} value={index + 1}>
                            Day {String(index + 1).padStart(3, '0')}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                </div>
              </div>
              <div className="h-[360px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#30363d" vertical={false} />
                    <XAxis
                      dataKey="label"
                      tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'monospace' }}
                      stroke="#30363d"
                    />
                    <YAxis
                      allowDecimals={false}
                      tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'monospace' }}
                      label={{ value: domainLabel[domain], angle: -90, position: 'insideLeft', fill: '#8b949e', fontSize: 10 }}
                      stroke="#30363d"
                      width={42}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#161b22',
                        border: '1px solid #30363d',
                        fontFamily: 'monospace',
                        fontSize: 11,
                      }}
                      formatter={(value: number) => [`${value.toFixed(2)}`, domainLabel[domain]]}
                      labelFormatter={label => `${view === 'average' ? 'Average' : `Day ${String(selectedDayOfYear).padStart(3, '0')}`} · ${label}`}
                    />
                    <Bar dataKey="count" name={domainLabel[domain]} fill="#2dd4bf" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-3 text-center font-mono text-[10px] text-muted">
                {view === 'average'
                  ? `Each bar is the average ${domainLabel[domain].toLowerCase()} count for that hour across ${dataset.span_days} stored days.`
                  : `Hourly ${domainLabel[domain].toLowerCase()} count for day ${String(selectedDayOfYear).padStart(3, '0')} of the stored baseline.`}
              </p>
            </>
          )}
        </div>
        <div className="flex justify-end border-t border-border px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-border px-4 py-2 font-mono text-xs text-muted hover:border-teal-500/60 hover:text-text"
          >
            Back to Capacity Alerts
          </button>
        </div>
      </div>
    </div>
  )
}

function RollingPlanningSection({
  projection,
  referenceShapeStatus,
}: {
  projection: RollingShortfall | null
  referenceShapeStatus: ReferenceShapeStatus
}) {
  if (!projection) {
    return (
      <div className="rounded border border-border bg-canvas/40 p-4 font-mono text-sm text-muted">
        Rolling planning forecast is unavailable until a live simulation tick arrives.
      </div>
    )
  }

  const earliest = projection.earliest
  const urgencyLabel: Record<PlanningUrgency, string> = {
    clear: 'No projected shortfall',
    immediate: 'Immediate attention',
    prepare: 'Prepare within the hour',
    plan: 'Plan ahead',
  }
  const urgencyClass: Record<PlanningUrgency, string> = {
    clear: 'border-teal-500/40 bg-teal-500/5 text-teal-300',
    immediate: 'border-red-500/60 bg-red-500/10 text-red-300',
    prepare: 'border-warn/60 bg-warn/10 text-warn',
    plan: 'border-amber-500/40 bg-amber-500/5 text-amber-300',
  }
  const urgencyColour: Record<PlanningUrgency, string> = {
    clear: '#2dd4bf',
    immediate: '#f87171',
    prepare: '#f59e0b',
    plan: '#fbbf24',
  }
  const urgency = earliest?.urgency ?? 'clear'
  const chartData = projection.points.map(point => ({
    ...point,
    leadTimeLabel: point.urgency === 'clear'
      ? ''
      : formatPlanningTime(point.minutesFromNow),
  }))

  return (
    <section className={`rounded border p-4 ${urgencyClass[urgency]}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] opacity-80">
            Rolling planning alert · 15 min–4 hr
          </div>
          <div className="mt-1 font-mono text-lg font-semibold">
            {earliest ? urgencyLabel[urgency] : urgencyLabel.clear}
          </div>
        </div>
        <div className="font-mono text-[10px] uppercase tracking-wider opacity-70">
          {projection.source}
        </div>
      </div>
      {projection.sourceDetail && (
        <p className="mt-2 font-mono text-[10px] leading-relaxed opacity-70">
          Shape source: {projection.sourceDetail}
        </p>
      )}
      {referenceShapeStatus === 'loading' && projection.source === 'simulator forecast' && (
        <p className="mt-2 font-mono text-[10px] leading-relaxed opacity-70">
          Loading the persisted workload shape; live simulator projection remains active.
        </p>
      )}
      {referenceShapeStatus === 'unavailable' && projection.source === 'simulator forecast' && (
        <p className="mt-2 font-mono text-[10px] leading-relaxed opacity-70">
          Reference baseline unavailable; showing the live simulator projection.
        </p>
      )}
      {earliest ? (
        <div className="mt-3 space-y-2 font-mono text-xs">
          <p className="leading-relaxed">
            Projected shortfall {formatPlanningTime(earliest.minutesFromNow)}.
            {' '}Recommended response: {urgency === 'immediate'
              ? 'act now'
              : urgency === 'prepare'
                ? 'prepare dispatch or load relief'
                : 'review capacity before the projected window'}.
          </p>
          <div className="grid grid-cols-3 gap-2 border-t border-current/20 pt-2">
            <div><span className="block opacity-70">At</span>{formatPlanningTime(earliest.minutesFromNow)}</div>
            <div><span className="block opacity-70">Demand</span>{earliest.projectedDemandMw.toFixed(2)} MW</div>
            <div><span className="block opacity-70">Gap</span>{earliest.shortfallMw.toFixed(2)} MW</div>
          </div>
        </div>
      ) : (
        <p className="mt-2 font-mono text-xs leading-relaxed opacity-80">
          No shortfall is projected in the next 4 hours at the current simulator forecast.
        </p>
      )}
      <div className="mt-3 border-t border-current/20 pt-3">
        <div className="h-44 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              margin={{ top: 22, right: 8, bottom: 4, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" vertical={false} />
              <XAxis
                type="number"
                dataKey="minutesFromNow"
                domain={[0, 240]}
                ticks={[0, 60, 120, 180, 240]}
                tickFormatter={(value: number) => value === 0 ? 'now' : `${value}m`}
                tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'monospace' }}
                stroke="#30363d"
              />
              <YAxis
                tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'monospace' }}
                tickFormatter={(value: number) => `${value.toFixed(0)}`}
                label={{ value: 'MW', angle: -90, position: 'insideLeft', fill: '#8b949e', fontSize: 10 }}
                stroke="#30363d"
                width={34}
              />
              <Tooltip
                contentStyle={{
                  background: '#161b22',
                  border: '1px solid #30363d',
                  fontFamily: 'monospace',
                  fontSize: 11,
                }}
                labelFormatter={(value: number) => value === 0 ? 'now' : formatPlanningTime(value)}
                formatter={(value: number, _name: string, item: { payload?: typeof chartData[number] }) => {
                  const point = item.payload
                  const driverLabel = point
                    ? point.driver === 'scheduled'
                      ? 'scripted event'
                      : point.driver === 'reference'
                        ? 'reference shape'
                        : 'live ramp'
                    : 'projected demand'
                  return [
                    `${value.toFixed(2)} MW`,
                    point
                      ? `${point.shortfallMw > 0 ? `-${point.shortfallMw.toFixed(2)} MW gap` : 'OK'} · ${point.urgency} · driven by ${driverLabel}`
                      : 'projected demand',
                  ]
                }}
              />
              <ReferenceLine
                x={0}
                stroke="#8b949e"
                strokeDasharray="3 3"
                label={{ value: 'now', position: 'insideTopLeft', fill: '#8b949e', fontSize: 10, fontFamily: 'monospace' }}
              />
              <Bar
                dataKey="projectedDemandMw"
                name="Projected demand"
                radius={[2, 2, 0, 0]}
                isAnimationActive={false}
                maxBarSize={22}
              >
                <LabelList
                  dataKey="leadTimeLabel"
                  position="top"
                  fill="#c9d1d9"
                  fontSize={9}
                  fontFamily="monospace"
                />
                {chartData.map(point => (
                  <Cell key={point.minutesFromNow} fill={urgencyColour[point.urgency]} fillOpacity={point.urgency === 'clear' ? 0.55 : 0.9} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-1 text-center font-mono text-[10px] opacity-60">
          Each bar = 15 minutes · 16 bars = the full 4-hour window
        </p>
      </div>
      <p className="mt-2 font-mono text-[10px] opacity-60">
        Advisory projection from live simulator telemetry; immediate balance and reserve alerts remain authoritative for current conditions.
      </p>
    </section>
  )
}
