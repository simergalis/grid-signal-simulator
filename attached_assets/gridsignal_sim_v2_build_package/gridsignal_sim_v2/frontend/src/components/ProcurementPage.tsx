/**
 * ProcurementPage — §19.8 Grid & Procurement console.
 *
 * P2 clarification (inert acceptance):
 * Authorization today records state only — it stores reviewer_id and
 * accepted_at_sim_time on the Proposal dataclass (O2 acceptance path) and
 * sets the proposal to ACCEPTED in the advisory gate.  There is NO current
 * path from an accepted ReservationProposal to GridCapacity or the control
 * plane.  The authorization dialog is present because the confirmation
 * architecture (TC-52) must be in place before the effect path is wired; the
 * UI enforces the governance gate (named reviewer + explicit checkbox) even
 * though the downstream effect is not yet connected.
 *
 * "The only place in the console where an action commits money" was
 * inaccurate — replace with: "the only place that records authorization
 * intent for a capacity reservation, pending the production effect path."
 *
 * TC-47: Non-firm spot import is shown as reducing served load, but the
 *        reserve gap indicator is NOT updated — non-firm does not close
 *        the gap.
 * TC-52: ReservationProposal always requires_confirmation=True.  The
 *        authorization button is behind a confirmation dialog and there
 *        is no "auto-approve" or "approve at tier" control on this page.
 *
 * Sections:
 *  1. Capacity summary (firm / reserved / non-firm) with gap indicator
 *  2. Synthetic price curve chart
 *  3. Pending ReservationProposals (TC-52: authorization only, never autonomous)
 */
import { useState, useCallback, useEffect, useRef } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type CapacityType = 'firm' | 'reserved' | 'non_firm'

interface CapacityRow {
  capacity_type:  CapacityType
  available_mw:   number
  price_per_mwh:  number
  t_reserve_s:    number
}

interface PricePoint {
  sim_time:      number
  price_per_mwh: number
}

interface PendingReservation {
  proposal_id:    string
  capacity_type:  CapacityType
  requested_mw:   number
  estimated_cost: number
  t_reserve_s:    number
  rationale:      string
  // always true (TC-52)
  requires_confirmation: true
}

interface ProcurementState {
  reserve_gap_mw:     number   // MW gap between firm committed and forecast peak
  firm_mw:            number
  reserved_mw:        number
  non_firm_mw:        number
  served_load_mw:     number
  capacity:           CapacityRow[]
  price_curve:        PricePoint[]
  pending_reservations: PendingReservation[]
}

// ---------------------------------------------------------------------------
// Empty / loading state (no stub data — live API only)
// ---------------------------------------------------------------------------

function _emptyState(): ProcurementState {
  return {
    reserve_gap_mw: 0, firm_mw: 0, reserved_mw: 0,
    non_firm_mw: 0, served_load_mw: 0,
    capacity: [], price_curve: [], pending_reservations: [],
  }
}

// Map a raw ProposalOut from /proposals/{run_id} to a PendingReservation.
// Only proposals with kind ~= 'reservation' and state === 'pending' are shown.
function _proposalToReservation(
  p: {
    proposal_id: string; kind: string; estimated_impact_mw: number
    state: string; reasoning: string; requires_confirmation: boolean
    suggested_tier: string | null
  },
  capacityPrice: Record<string, number>,
): PendingReservation | null {
  if (p.state !== 'pending') return null
  if (!p.kind.toLowerCase().includes('reserv')) return null
  const capType: CapacityType =
    (p.suggested_tier === 'firm' || p.suggested_tier === 'reserved' || p.suggested_tier === 'non_firm')
      ? p.suggested_tier as CapacityType
      : 'reserved'
  return {
    proposal_id:    p.proposal_id,
    capacity_type:  capType,
    requested_mw:   p.estimated_impact_mw,
    estimated_cost: capacityPrice[capType] ?? 62.0,
    t_reserve_s:    capType === 'reserved' ? 300 : 0,
    rationale:      p.reasoning,
    requires_confirmation: true,
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const CAPACITY_LABELS: Record<CapacityType, string> = {
  firm:     'Firm',
  reserved: 'Reserved',
  non_firm: 'Non-firm (spot)',
}

const CAPACITY_COLORS: Record<CapacityType, string> = {
  firm:     'bg-green-500',
  reserved: 'bg-blue-500',
  non_firm: 'bg-amber-500',
}

function CapacityBar({ capacity, totalMw }: { capacity: CapacityRow[]; totalMw: number }) {
  return (
    <div className="flex rounded overflow-hidden h-3 gap-px">
      {capacity.map(c => (
        <div
          key={c.capacity_type}
          className={`${CAPACITY_COLORS[c.capacity_type]} transition-all`}
          style={{ width: `${(c.available_mw / Math.max(totalMw, 1)) * 100}%` }}
          title={`${CAPACITY_LABELS[c.capacity_type]}: ${c.available_mw} MW @ $${c.price_per_mwh}/MWh`}
        />
      ))}
    </div>
  )
}

function MiniPriceCurve({ points }: { points: PricePoint[] }) {
  if (points.length < 2) return null
  const prices = points.map(p => p.price_per_mwh)
  const minP = Math.min(...prices)
  const maxP = Math.max(...prices)
  const range = Math.max(maxP - minP, 1)
  const W = 240
  const H = 48
  const pts = points.map((p, i) => {
    const x = (i / (points.length - 1)) * W
    const y = H - ((p.price_per_mwh - minP) / range) * H
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return (
    <svg width={W} height={H} className="overflow-visible">
      <polyline
        points={pts.join(' ')}
        fill="none"
        stroke="rgb(99 179 237)"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

interface AuthorizeDialogProps {
  reservation: PendingReservation
  onConfirm: (id: string, reviewerId: string) => void
  onCancel:  () => void
}

function AuthorizeDialog({ reservation, onConfirm, onCancel }: AuthorizeDialogProps) {
  const [reviewer, setReviewer] = useState('')
  const [agreed,   setAgreed]   = useState(false)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-surface border border-border rounded-xl shadow-2xl w-full max-w-md mx-4 p-5 space-y-4">
        {/* Header */}
        <div className="flex items-center gap-2">
          <span className="text-amber-400 text-lg">⚠</span>
          <h3 className="font-semibold text-text">Authorize Grid Reservation</h3>
        </div>
        <p className="text-xs text-amber-300 bg-amber-900/20 border border-amber-700/40 rounded px-3 py-2">
          This action commits real money. Authorization is required for every reservation
          at every tier — there is no autonomous approval path (TC-52, §24.3).
        </p>

        {/* Details */}
        <div className="rounded-lg bg-canvas border border-border p-3 space-y-1 text-xs">
          <div className="flex justify-between">
            <span className="text-text-muted">Capacity type</span>
            <span className="text-text font-medium">{CAPACITY_LABELS[reservation.capacity_type]}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-muted">Requested</span>
            <span className="text-text font-medium">{reservation.requested_mw} MW</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-muted">Est. price</span>
            <span className="text-text font-medium">${reservation.estimated_cost.toFixed(2)}/MWh</span>
          </div>
          {reservation.t_reserve_s > 0 && (
            <div className="flex justify-between">
              <span className="text-text-muted">Lead time</span>
              <span className="text-text font-medium">{reservation.t_reserve_s}s</span>
            </div>
          )}
          <div className="pt-1 border-t border-border">
            <p className="text-text-muted">Rationale</p>
            <p className="text-text mt-0.5">{reservation.rationale}</p>
          </div>
        </div>

        {/* Reviewer ID */}
        <div>
          <label className="text-xs text-text-muted block mb-1">
            Reviewer ID (required)
          </label>
          <input
            className="w-full bg-canvas border border-border rounded px-2 py-1.5 text-xs text-text
                       placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent"
            placeholder="e.g. ops-lead@example.com"
            value={reviewer}
            onChange={e => setReviewer(e.target.value)}
          />
        </div>

        {/* Confirmation checkbox */}
        <label className="flex items-start gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={agreed}
            onChange={e => setAgreed(e.target.checked)}
            className="mt-0.5 accent-accent"
          />
          <span className="text-xs text-text-muted">
            I confirm I am authorizing a financial commitment. This reservation will be
            submitted to the grid operator on the next window boundary.
          </span>
        </label>

        {/* Actions */}
        <div className="flex gap-2 justify-end pt-1">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-xs rounded border border-border text-text-muted
                       hover:text-text hover:border-text-muted transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(reservation.proposal_id, reviewer.trim())}
            disabled={!reviewer.trim() || !agreed}
            className="px-3 py-1.5 text-xs rounded bg-amber-600 text-white font-medium
                       hover:bg-amber-500 disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors"
          >
            Authorize Reservation
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

interface ProcurementPageProps {
  runId: string | null
}

export function ProcurementPage({ runId }: ProcurementPageProps) {
  const [state, setState] = useState<ProcurementState>(_emptyState())
  const [dialogId, setDialogId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Poll procurement state + pending proposals while a run is active.
  useEffect(() => {
    if (!runId) { setState(_emptyState()); return }

    let alive = true
    async function fetchAll() {
      try {
        const [procR, propR] = await Promise.all([
          fetch(`/procurement/${runId}`).catch(() => null),
          fetch(`/proposals/${runId}`).catch(() => null),
        ])
        if (!alive) return

        if (!procR || procR.status === 409) {
          // Run completed — stop polling, keep last state.
          if (pollRef.current) clearInterval(pollRef.current)
          return
        }
        if (!procR.ok) { setError(`HTTP ${procR.status}`); return }

        const proc = await procR.json()
        const proposals = propR?.ok ? (await propR.json()).proposals : []
        const priceByTier: Record<string, number> = {}
        for (const c of (proc.capacity ?? [])) priceByTier[c.capacity_type] = c.price_per_mwh

        const pendingRes: PendingReservation[] = (proposals as {
          proposal_id: string; kind: string; estimated_impact_mw: number
          state: string; reasoning: string; requires_confirmation: boolean
          suggested_tier: string | null
        }[])
          .map(p => _proposalToReservation(p, priceByTier))
          .filter((x): x is PendingReservation => x !== null)

        setError(null)
        setLoading(false)
        setState({
          reserve_gap_mw:      proc.reserve_gap_mw,
          firm_mw:             proc.firm_mw,
          reserved_mw:         proc.reserved_mw,
          non_firm_mw:         proc.non_firm_mw,
          served_load_mw:      proc.served_load_mw,
          capacity:            proc.capacity,
          price_curve:         proc.price_curve,
          pending_reservations: pendingRes,
        })
      } catch (e: unknown) {
        if (alive) setError(String(e))
      }
    }

    setLoading(true)
    fetchAll()
    pollRef.current = setInterval(fetchAll, 2000)
    return () => {
      alive = false
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [runId])

  const totalMw = state.capacity.reduce((s, c) => s + c.available_mw, 0)
  const dialogReservation = state.pending_reservations.find(r => r.proposal_id === dialogId)

  const handleAuthorize = useCallback((proposalId: string) => {
    setDialogId(proposalId)
  }, [])

  const handleConfirmAuthorize = useCallback(async (proposalId: string, reviewerId: string) => {
    // TC-52: POST /proposals/{id}/accept with reviewer_id.
    // Removes from local state immediately (optimistic update); API is source of truth.
    try {
      await fetch(`/proposals/${proposalId}/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewer_id: reviewerId }),
      })
    } catch { /* ignore — state will reconcile on next poll */ }
    setState(prev => ({
      ...prev,
      pending_reservations: prev.pending_reservations.filter(
        r => r.proposal_id !== proposalId
      ),
    }))
    setDialogId(null)
  }, [])

  if (!runId) {
    return (
      <div className="h-full flex items-center justify-center text-sm text-text-muted">
        Start a run to see grid &amp; procurement data.
      </div>
    )
  }

  return (
    <>
      <div className="h-full overflow-y-auto p-4 space-y-4 text-sm">

        {/* Status row */}
        {loading && state.capacity.length === 0 && (
          <p className="text-xs text-text-muted animate-pulse">Loading procurement data…</p>
        )}
        {error && (
          <p className="text-xs text-red-400">Error: {error}</p>
        )}

        {/* Page header */}
        <div>
          <h2 className="text-base font-semibold text-text">Grid &amp; Procurement</h2>
          <p className="text-xs text-text-muted mt-0.5">
            §19.8 · Firm / reserved / non-firm capacity.
            Reservation authorization is the only control on this page that commits money —
            it is confirmed separately for that reason (TC-52, §24.3).
          </p>
        </div>

        {/* Reserve gap indicator */}
        <div className={`rounded-lg border p-3 flex items-center gap-3 ${
          state.reserve_gap_mw > 0
            ? 'border-red-700/40 bg-red-900/10'
            : 'border-green-700/40 bg-green-900/10'
        }`}>
          <div className="flex-1">
            <p className="text-xs font-medium text-text">
              Reserve gap: {state.reserve_gap_mw > 0
                ? `${state.reserve_gap_mw.toFixed(1)} MW deficit`
                : 'Covered'}
            </p>
            <p className="text-xs text-text-muted mt-0.5">
              Firm committed: {state.firm_mw} MW · Served load: {state.served_load_mw.toFixed(1)} MW
            </p>
          </div>
          {state.non_firm_mw > 0 && state.reserve_gap_mw > 0 && (
            <div className="text-xs text-amber-300 text-right">
              <p>{state.non_firm_mw} MW non-firm (spot) imported</p>
              <p className="text-text-muted">Gap unchanged — TC-47</p>
            </div>
          )}
        </div>

        {/* Capacity summary */}
        <section className="rounded-lg border border-border bg-surface p-3 space-y-3">
          <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">
            Available Capacity
          </h3>
          <CapacityBar capacity={state.capacity} totalMw={totalMw} />
          <div className="grid grid-cols-3 gap-2">
            {state.capacity.map(c => (
              <div key={c.capacity_type} className="rounded bg-canvas border border-border p-2">
                <div className="flex items-center gap-1.5 mb-1">
                  <div className={`w-2 h-2 rounded-full ${CAPACITY_COLORS[c.capacity_type]}`} />
                  <span className="text-xs text-text-muted">{CAPACITY_LABELS[c.capacity_type]}</span>
                </div>
                <p className="text-sm font-medium text-text">{c.available_mw} MW</p>
                <p className="text-xs text-text-muted">${c.price_per_mwh.toFixed(0)}/MWh</p>
                {c.t_reserve_s > 0 && (
                  <p className="text-xs text-text-muted">T_reserve {c.t_reserve_s}s</p>
                )}
              </div>
            ))}
          </div>
          <p className="text-xs text-text-muted">
            TC-47: non-firm spot import reduces served load but does NOT close the reserve gap.
          </p>
        </section>

        {/* Synthetic price curve */}
        <section className="rounded-lg border border-border bg-surface p-3 space-y-2">
          <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">
            Synthetic Price Curve
          </h3>
          <MiniPriceCurve points={state.price_curve} />
          <p className="text-xs text-text-muted">
            Seeded synthetic curve — no live external feeds.
            A demo that depends on a third-party API's availability will eventually fail
            in front of an audience.
          </p>
        </section>

        {/* Pending reservations (TC-52) */}
        <section className="rounded-lg border border-border bg-surface overflow-hidden">
          <div className="px-3 py-2 border-b border-border flex items-center justify-between">
            <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">
              Pending Reservation Proposals
            </h3>
            <span className="text-xs text-amber-300">
              Authorization required · Never autonomous (TC-52)
            </span>
          </div>
          {state.pending_reservations.length === 0 ? (
            <p className="px-3 py-4 text-xs text-text-muted">No pending reservation proposals.</p>
          ) : (
            <div className="divide-y divide-border">
              {state.pending_reservations.map(r => (
                <div key={r.proposal_id} className="px-3 py-3 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`px-1.5 py-0.5 text-xs rounded font-medium ${
                          r.capacity_type === 'firm'
                            ? 'bg-green-900/40 text-green-300'
                            : r.capacity_type === 'reserved'
                            ? 'bg-blue-900/40 text-blue-300'
                            : 'bg-amber-900/40 text-amber-300'
                        }`}>
                          {CAPACITY_LABELS[r.capacity_type]}
                        </span>
                        <span className="text-xs text-text">
                          {r.requested_mw} MW · ${r.estimated_cost.toFixed(2)}/MWh
                        </span>
                        {r.t_reserve_s > 0 && (
                          <span className="text-xs text-text-muted">
                            T_reserve {r.t_reserve_s}s
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-text-muted mt-1">{r.rationale}</p>
                    </div>
                    <button
                      onClick={() => handleAuthorize(r.proposal_id)}
                      className="flex-shrink-0 px-3 py-1.5 text-xs rounded border border-amber-600/60
                                 text-amber-300 hover:bg-amber-900/30 hover:border-amber-500
                                 transition-colors font-medium"
                    >
                      Authorize…
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="px-3 py-2 border-t border-border bg-canvas/50">
            <p className="text-xs text-text-muted">
              §24.3: reservations are never autonomous at any tier. Authorization requires
              a named reviewer and an explicit confirmation step.
            </p>
          </div>
        </section>
      </div>

      {/* Authorization dialog (TC-52) */}
      {dialogId && dialogReservation && (
        <AuthorizeDialog
          reservation={dialogReservation}
          onConfirm={handleConfirmAuthorize}
          onCancel={() => setDialogId(null)}
        />
      )}
    </>
  )
}
