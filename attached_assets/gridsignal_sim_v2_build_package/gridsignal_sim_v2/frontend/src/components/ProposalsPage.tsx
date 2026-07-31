/**
 * ProposalsPage.tsx — §19.10 Proposals & Learning (Step 13).
 *
 * Shows all advisory proposals from the current or most recent run:
 *   • Originating agent, kind, estimated impact, confidence, state, expiry.
 *   • Reasoning text.
 *   • Approve / Reject buttons for PENDING proposals.
 *   • For proposals with requires_confirmation=true: Approve opens a
 *     Confirm-consequence modal (type "CONFIRM" to proceed).
 *   • Sort by estimated impact (descending).
 *   • Agents ON/OFF toggle in the header.
 *   • generated_by badge: "MODEL" (normal) vs "FALLBACK" (distinct, amber).
 *
 * Data: polled from GET /proposals/{runId} at 2 Hz when a run is active.
 * Actions: POST /proposals/{proposalId}/accept or /reject.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTickStore } from '../store/tickStore'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ProposalState = 'pending' | 'accepted' | 'rejected' | 'expired' | 'superseded'

interface Proposal {
  proposal_id: string
  kind: string
  estimated_impact_mw: number
  confidence: number
  reasoning: string
  state: ProposalState
  expires_at_sim_time: number
  created_at_sim_time: number
  suggested_tier: string | null
  originating_agent: string
  prompt_digest: string
  evidence_digest: string
  generated_by: string        // "model" | "fallback"
  requires_confirmation: boolean
  rejection_reason: string | null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const KIND_LABELS: Record<string, string> = {
  curtailment:        'Curtailment',
  pre_staging:        'Pre-staging',
  bess_reserve_adjust: 'BESS Reserve',
  turbine_ramp_rate:  'Turbine Ramp',
  load_defer:         'Load Defer',
  calibration:        'Calibration',
}

const STATE_CLASSES: Record<ProposalState, string> = {
  pending:    'text-yellow-400 bg-yellow-400/10',
  accepted:   'text-green-400 bg-green-400/10',
  rejected:   'text-red-400 bg-red-400/10',
  expired:    'text-text-muted bg-surface-2',
  superseded: 'text-text-muted bg-surface-2',
}

const AGENT_LABELS: Record<string, string> = {
  compute:     'Compute & Workload',
  storage:     'Storage',
  generation:  'Generation',
  renewable:   'Renewable Supply',
  thermal:     'Thermal',
  calibration: 'Calibration',
}

function Badge({ text, className }: { text: string; className: string }) {
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono uppercase ${className}`}>
      {text}
    </span>
  )
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const colour = pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-1.5 text-xs text-text-muted">
      <div className="h-1.5 w-20 bg-border rounded-full overflow-hidden">
        <div className={`h-full ${colour} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span>{pct}%</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ConfirmModal — type-to-confirm for requires_confirmation proposals
// ---------------------------------------------------------------------------

function ConfirmModal({
  proposal,
  onConfirm,
  onCancel,
}: {
  proposal: Proposal
  onConfirm: () => void
  onCancel: () => void
}) {
  const latestTick     = useTickStore(s => s.latestTick)
  const [typed, setTyped] = useState('')

  // Count jobs currently in a running state (informational; not guaranteed accurate)
  const runningJobs = latestTick
    ? Object.entries(latestTick.checkpoint_states)
        .filter(([, state]) => state === 'running')
        .map(([jobId]) => jobId)
    : []

  const dtLead = latestTick?.dt_lead_next_s ?? 0

  const confirmed = typed === 'CONFIRM'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-[480px] rounded-lg border border-border bg-surface shadow-2xl overflow-hidden">

        {/* Header */}
        <div className="px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <span className="text-warn text-lg">⚠</span>
            <h3 className="text-sm font-semibold text-text">Review before applying</h3>
          </div>
          <p className="mt-1 text-xs text-text-muted">
            This proposal requires confirmation before it is applied to the dispatch layer.
          </p>
        </div>

        {/* Proposal summary */}
        <div className="px-5 py-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-[10px] text-text-muted uppercase tracking-wide">Kind</p>
              <p className="text-xs text-text font-mono">{KIND_LABELS[proposal.kind] ?? proposal.kind}</p>
            </div>
            {proposal.suggested_tier && (
              <div>
                <p className="text-[10px] text-text-muted uppercase tracking-wide">Tier</p>
                <p className="text-xs text-text font-mono">{proposal.suggested_tier}</p>
              </div>
            )}
            <div>
              <p className="text-[10px] text-text-muted uppercase tracking-wide">Estimated impact</p>
              <p className="text-xs text-text font-semibold">{proposal.estimated_impact_mw.toFixed(2)} MW</p>
            </div>
            <div>
              <p className="text-[10px] text-text-muted uppercase tracking-wide">Confidence</p>
              <ConfidenceBar value={proposal.confidence} />
            </div>
          </div>

          {/* Affected jobs */}
          <div className="rounded border border-border bg-canvas p-3 space-y-1.5">
            <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wide">
              Restoration cost
            </p>
            <p className="text-xs text-text">
              {runningJobs.length > 0
                ? `${runningJobs.length} job${runningJobs.length > 1 ? 's' : ''} currently running.`
                : 'No jobs in running state (cost applies to next staged job).'}
            </p>
            <p className="text-xs text-text-muted leading-relaxed">
              Each affected job must complete the GPU ramp-up sequence
              {dtLead > 0 ? ` (approximately ${dtLead.toFixed(0)} s remaining at current rate)` : ''}
              , plus checkpoint reload overhead, before resuming full throughput.
              This figure is based on ramp-lead time and checkpoint mechanics —
              not forfeited compute.
            </p>
            {runningJobs.length > 0 && (
              <div className="text-[10px] font-mono text-text-muted">
                {runningJobs.slice(0, 4).join(', ')}
                {runningJobs.length > 4 ? `, +${runningJobs.length - 4} more` : ''}
              </div>
            )}
          </div>

          {/* Type-to-confirm */}
          <div className="space-y-1.5">
            <label className="text-[10px] text-text-muted">
              Type <span className="font-mono text-text">CONFIRM</span> to proceed
            </label>
            <input
              type="text"
              className="w-full rounded border border-border bg-canvas px-2 py-1.5 text-xs text-text
                         font-mono focus:outline-none focus:ring-1 focus:ring-warn"
              placeholder="CONFIRM"
              value={typed}
              onChange={e => setTyped(e.target.value)}
              autoFocus
              onKeyDown={e => { if (e.key === 'Enter' && confirmed) onConfirm() }}
            />
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-border flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded border border-border px-4 py-1.5 text-xs text-text-muted hover:text-text"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!confirmed}
            className="rounded bg-red-700 px-4 py-1.5 text-xs font-semibold text-white
                       hover:bg-red-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Confirm and apply
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ProposalCard
// ---------------------------------------------------------------------------

function ProposalCard({
  proposal,
  onAccept,
  onReject,
  onRequestConfirm,
}: {
  proposal: Proposal
  onAccept: (id: string) => void
  onReject: (id: string) => void
  onRequestConfirm: (p: Proposal) => void
}) {
  const isPending = proposal.state === 'pending'
  const stateClass = STATE_CLASSES[proposal.state] ?? 'text-text-muted'

  return (
    <div className="rounded-lg border border-border bg-surface p-4 space-y-2">
      {/* Header row */}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-text">
              {AGENT_LABELS[proposal.originating_agent] ?? proposal.originating_agent}
            </span>
            <Badge
              text={KIND_LABELS[proposal.kind] ?? proposal.kind}
              className="text-accent bg-accent/10"
            />
            {proposal.suggested_tier && (
              <Badge
                text={proposal.suggested_tier}
                className="text-text-muted bg-border"
              />
            )}
            <Badge
              text={proposal.generated_by === 'fallback' ? 'FALLBACK' : 'MODEL'}
              className={
                proposal.generated_by === 'fallback'
                  ? 'text-amber-400 bg-amber-400/10'
                  : 'text-blue-400 bg-blue-400/10'
              }
            />
            {proposal.requires_confirmation && (
              <Badge
                text="NEEDS REVIEW"
                className="text-orange-400 bg-orange-400/10"
              />
            )}
          </div>
          <div className="text-xs text-text-muted font-mono">
            id:{proposal.proposal_id.slice(0, 8)}
            {' · '}
            digest:{proposal.evidence_digest}
          </div>
        </div>

        <Badge
          text={proposal.state.toUpperCase()}
          className={stateClass}
        />
      </div>

      {/* Impact + confidence */}
      <div className="flex items-center gap-6 text-sm">
        <div>
          <span className="text-text-muted text-xs uppercase tracking-wide">Impact</span>
          <div className="text-text font-semibold">
            {proposal.estimated_impact_mw.toFixed(2)} MW
          </div>
        </div>
        <div>
          <span className="text-text-muted text-xs uppercase tracking-wide">Confidence</span>
          <ConfidenceBar value={proposal.confidence} />
        </div>
        <div>
          <span className="text-text-muted text-xs uppercase tracking-wide">Expires at</span>
          <div className="text-text text-xs font-mono">
            t={proposal.expires_at_sim_time.toFixed(0)}s
          </div>
        </div>
      </div>

      {/* Reasoning */}
      <p className="text-xs text-text-muted leading-relaxed">
        {proposal.reasoning || '—'}
      </p>
      {proposal.rejection_reason && (
        <p className="text-xs text-red-400">
          Rejection: {proposal.rejection_reason}
        </p>
      )}

      {/* Actions (PENDING only) */}
      {isPending && (
        <div className="flex gap-2 pt-1">
          {proposal.requires_confirmation ? (
            /* Tier C/D or other high-consequence: gate behind confirm modal */
            <button
              onClick={() => onRequestConfirm(proposal)}
              className="px-3 py-1 text-xs rounded bg-amber-700 hover:bg-amber-600 text-white transition-colors"
            >
              Review &amp; Approve
            </button>
          ) : (
            /* Tier A/B: direct Approve */
            <button
              onClick={() => onAccept(proposal.proposal_id)}
              className="px-3 py-1 text-xs rounded bg-green-600 hover:bg-green-500 text-white transition-colors"
            >
              Approve
            </button>
          )}
          <button
            onClick={() => onReject(proposal.proposal_id)}
            className="px-3 py-1 text-xs rounded bg-red-700 hover:bg-red-600 text-white transition-colors"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ProposalsPage
// ---------------------------------------------------------------------------

export function ProposalsPage({
  runId,
  agentsEnabled,
  onToggleAgents,
}: {
  runId: string | null
  agentsEnabled: boolean
  onToggleAgents: () => void
}) {
  const [proposals,     setProposals]     = useState<Proposal[]>([])
  const [loading,       setLoading]       = useState(false)
  const [error,         setError]         = useState<string | null>(null)
  const [confirmTarget, setConfirmTarget] = useState<Proposal | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Fetch proposals ───────────────────────────────────────────────────────

  const fetchProposals = useCallback(async () => {
    if (!runId) return
    try {
      const resp = await fetch(`/proposals/${runId}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      const sorted = (data.proposals as Proposal[]).sort(
        (a, b) => b.estimated_impact_mw - a.estimated_impact_mw,
      )
      setProposals(sorted)
      setError(null)
    } catch (e) {
      setError(String(e))
    }
  }, [runId])

  useEffect(() => {
    setLoading(true)
    fetchProposals().finally(() => setLoading(false))
    intervalRef.current = setInterval(fetchProposals, 500)   // 2 Hz
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchProposals])

  // ── Actions ───────────────────────────────────────────────────────────────

  const handleAccept = useCallback(async (proposalId: string) => {
    await fetch(`/proposals/${proposalId}/accept`, { method: 'POST' })
    fetchProposals()
  }, [fetchProposals])

  const handleReject = useCallback(async (proposalId: string) => {
    await fetch(`/proposals/${proposalId}/reject`, { method: 'POST' })
    fetchProposals()
  }, [fetchProposals])

  const handleRequestConfirm = useCallback((p: Proposal) => {
    setConfirmTarget(p)
  }, [])

  const handleModalConfirm = useCallback(async () => {
    if (!confirmTarget) return
    setConfirmTarget(null)
    await handleAccept(confirmTarget.proposal_id)
  }, [confirmTarget, handleAccept])

  const handleModalCancel = useCallback(() => {
    setConfirmTarget(null)
  }, [])

  // ── Render ────────────────────────────────────────────────────────────────

  const pending   = proposals.filter(p => p.state === 'pending')
  const terminal  = proposals.filter(p => p.state !== 'pending')

  return (
    <div className="flex flex-col h-full bg-canvas text-text overflow-hidden">

      {/* Confirm-consequence modal */}
      {confirmTarget && (
        <ConfirmModal
          proposal={confirmTarget}
          onConfirm={handleModalConfirm}
          onCancel={handleModalCancel}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface flex-shrink-0">
        <div>
          <h2 className="text-sm font-semibold text-text">Proposals &amp; Learning</h2>
          <p className="text-xs text-text-muted">§19.10 — advisory recommendations from the agent layer</p>
        </div>
        <div className="flex items-center gap-3">
          {proposals.length > 0 && (
            <span className="text-xs text-text-muted">
              {pending.length} pending / {proposals.length} total
            </span>
          )}
          {/* Agents ON/OFF toggle */}
          <button
            onClick={onToggleAgents}
            className={`
              flex items-center gap-2 px-3 py-1.5 rounded text-xs font-semibold
              transition-colors border
              ${agentsEnabled
                ? 'bg-green-600/20 border-green-600 text-green-400 hover:bg-green-600/30'
                : 'bg-surface-2 border-border text-text-muted hover:border-border'}
            `}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${agentsEnabled ? 'bg-green-400' : 'bg-text-muted'}`} />
            Agents {agentsEnabled ? 'ON' : 'OFF'}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-6">
        {!runId && (
          <div className="text-center text-text-muted text-sm py-16">
            Start a scenario run to see advisory proposals.
          </div>
        )}

        {runId && loading && proposals.length === 0 && (
          <div className="text-center text-text-muted text-sm py-16">Loading…</div>
        )}

        {error && (
          <div className="rounded border border-red-700/50 bg-red-900/20 text-red-400 text-xs px-3 py-2">
            {error}
          </div>
        )}

        {!agentsEnabled && (
          <div className="rounded border border-amber-700/50 bg-amber-900/10 text-amber-400 text-xs px-3 py-2">
            Agents are OFF — proposal generation is suspended. Dispatch is unaffected (TC-48).
          </div>
        )}

        {/* Pending proposals */}
        {pending.length > 0 && (
          <section className="space-y-3">
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide">
              Pending ({pending.length})
            </h3>
            {pending.map(p => (
              <ProposalCard
                key={p.proposal_id}
                proposal={p}
                onAccept={handleAccept}
                onReject={handleReject}
                onRequestConfirm={handleRequestConfirm}
              />
            ))}
          </section>
        )}

        {/* Terminal proposals */}
        {terminal.length > 0 && (
          <section className="space-y-3">
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide">
              History ({terminal.length})
            </h3>
            {terminal.map(p => (
              <ProposalCard
                key={p.proposal_id}
                proposal={p}
                onAccept={handleAccept}
                onReject={handleReject}
                onRequestConfirm={handleRequestConfirm}
              />
            ))}
          </section>
        )}

        {runId && !loading && proposals.length === 0 && !error && (
          <div className="text-center text-text-muted text-sm py-16">
            No proposals yet. Agents produce proposals every 30 s – 60 min depending on agent type.
          </div>
        )}
      </div>
    </div>
  )
}
