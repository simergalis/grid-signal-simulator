/**
 * ScenarioManagerPage.tsx — Scenario library with upload / download / delete.
 *
 * Capabilities:
 *   Upload   — drag JSON file or click "Upload JSON"; validates required fields
 *              before POSTing to POST /scenarios.
 *   Download — fetches GET /scenarios/{id} and saves the spec as a .json file.
 *   Edit     — opens the existing ScenarioBuilder drawer via onEditScenario.
 *   Delete   — inline two-step confirm; seeded scenarios are protected.
 *   New      — opens the ScenarioBuilder drawer via onNewScenario.
 *
 * Seeded scenarios (IDs matching demo-* or S\d+_*) cannot be deleted; they
 * are shown with a "built-in" badge and their delete button is disabled.
 */

import { useEffect, useRef, useState } from 'react'
import { useScenarioStore } from '../store/scenarioStore'
import type { ScenarioSpec } from '../types'

// ── Helpers ───────────────────────────────────────────────────────────────────

/** True for seeded/built-in scenarios that must not be deleted. */
function isSeeded(id: string): boolean {
  return id.startsWith('demo-') || /^S\d+_/.test(id) || id === 'demo_solar_peak'
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

/** Minimal structural check on an uploaded JSON object. */
function validateSpec(obj: unknown): string | null {
  if (typeof obj !== 'object' || obj === null) return 'File is not a JSON object.'
  const s = obj as Record<string, unknown>
  if (!s.name || typeof s.name !== 'string' || !s.name.trim()) return 'Missing required field: name.'
  if (!Array.isArray(s.bess_units) || s.bess_units.length === 0) return 'Missing required field: bess_units (array, ≥1 entry).'
  if (!Array.isArray(s.turbine_units) || s.turbine_units.length === 0) return 'Missing required field: turbine_units (array, ≥1 entry).'
  return null
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Badge({ label, variant }: { label: string; variant: 'muted' | 'accent' | 'success' | 'danger' }) {
  const cls: Record<string, string> = {
    muted:   'bg-canvas text-muted border-border',
    accent:  'bg-accent/10 text-accent border-accent/30',
    success: 'bg-success/10 text-success border-success/30',
    danger:  'bg-danger/10 text-danger border-danger/30',
  }
  return (
    <span className={`inline-block rounded border px-1.5 py-0.5 font-mono text-[9px] leading-none ${cls[variant]}`}>
      {label}
    </span>
  )
}

function Toast({ msg, kind, onDismiss }: { msg: string; kind: 'ok' | 'err'; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 5000)
    return () => clearTimeout(t)
  }, [onDismiss])

  return (
    <div
      className={`fixed bottom-4 right-4 z-50 flex items-start gap-2 rounded border px-4 py-3 text-xs shadow-lg max-w-sm
        ${kind === 'ok' ? 'bg-surface border-success/40 text-success' : 'bg-surface border-danger/40 text-danger'}`}
    >
      <span className="flex-1 leading-snug">{msg}</span>
      <button onClick={onDismiss} className="opacity-60 hover:opacity-100 text-sm leading-none">×</button>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  onNewScenario:  () => void
  onEditScenario: (id: string) => void
  /** Called after a run is successfully started from the Execute button. */
  onExecute?:     (runId: string, speed: number, socFloor?: number, socCeil?: number) => void
}

export function ScenarioManagerPage({ onNewScenario, onEditScenario, onExecute }: Props) {
  const scenarios     = useScenarioStore(s => s.scenarios)
  const isLoading     = useScenarioStore(s => s.isLoading)
  const fetchScenarios = useScenarioStore(s => s.fetchScenarios)
  const deleteScenario = useScenarioStore(s => s.deleteScenario)
  const createScenario = useScenarioStore(s => s.createScenario)

  const fileRef = useRef<HTMLInputElement>(null)

  const [toast,         setToast]         = useState<{ msg: string; kind: 'ok' | 'err' } | null>(null)
  const [confirmId,     setConfirmId]     = useState<string | null>(null)
  const [deleteBusy,    setDeleteBusy]    = useState(false)
  const [uploadBusy,    setUploadBusy]    = useState(false)
  const [downloadBusy,  setDownloadBusy]  = useState<string | null>(null)  // scenario_id in-flight
  const [executeBusy,   setExecuteBusy]   = useState<string | null>(null)  // scenario_id in-flight
  const [dragOver,      setDragOver]      = useState(false)
  const [search,        setSearch]        = useState('')

  // ── Execute (start a run directly from the scenario list) ─────────────────
  const handleExecute = async (scenarioId: string) => {
    setExecuteBusy(scenarioId)
    setToast(null)
    try {
      const resp = await fetch('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_id: scenarioId, playback_speed: 1, end_sim_time: 1800 }),
      })
      if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`)
      const data = await resp.json() as { run_id: string; soc_floor_pct?: number; soc_ceil_pct?: number }
      onExecute?.(data.run_id, 1, data.soc_floor_pct, data.soc_ceil_pct)
      setToast({ msg: `Run started for "${scenarioId}".`, kind: 'ok' })
    } catch (e) {
      setToast({ msg: `Failed to start run: ${String(e)}`, kind: 'err' })
    } finally {
      setExecuteBusy(null)
    }
  }

  useEffect(() => { fetchScenarios() }, [fetchScenarios])

  // ── Filtered list ──────────────────────────────────────────────────────────
  const q = search.trim().toLowerCase()
  const filtered = q
    ? scenarios.filter(s =>
        s.name.toLowerCase().includes(q) ||
        s.scenario_id.toLowerCase().includes(q) ||
        (s.description ?? '').toLowerCase().includes(q)
      )
    : scenarios

  // ── Upload ─────────────────────────────────────────────────────────────────
  const handleFile = async (file: File) => {
    if (!file.name.endsWith('.json')) {
      setToast({ msg: 'Only .json files are supported.', kind: 'err' })
      return
    }
    setUploadBusy(true)
    try {
      const text = await file.text()
      let obj: unknown
      try { obj = JSON.parse(text) } catch {
        setToast({ msg: 'File is not valid JSON.', kind: 'err' })
        return
      }
      const err = validateSpec(obj)
      if (err) { setToast({ msg: err, kind: 'err' }); return }
      const result = await createScenario(obj as ScenarioSpec)
      const warn = result.c_rate_warnings?.length
        ? `  ⚠ C-rate warnings: ${result.c_rate_warnings.join('; ')}`
        : ''
      setToast({ msg: `Uploaded "${result.name}" (${result.scenario_id}).${warn}`, kind: 'ok' })
    } catch (e) {
      setToast({ msg: String(e), kind: 'err' })
    } finally {
      setUploadBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) handleFile(f)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

  // ── Download ───────────────────────────────────────────────────────────────
  const handleDownload = async (id: string, name: string) => {
    setDownloadBusy(id)
    try {
      const resp = await fetch(`/scenarios/${id}`)
      if (!resp.ok) throw new Error(`GET /scenarios/${id} → ${resp.status}`)
      const data = await resp.json() as { spec: ScenarioSpec }
      const json = JSON.stringify(data.spec, null, 2)
      const url  = 'data:application/json;charset=utf-8,' + encodeURIComponent(json)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `${name.replace(/[^a-z0-9_-]/gi, '_')}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    } catch (e) {
      setToast({ msg: String(e), kind: 'err' })
    } finally {
      setDownloadBusy(null)
    }
  }

  // ── Delete ─────────────────────────────────────────────────────────────────
  const handleDeleteConfirm = async (id: string) => {
    setDeleteBusy(true)
    try {
      await deleteScenario(id)
      setConfirmId(null)
      setToast({ msg: `Scenario deleted.`, kind: 'ok' })
    } catch (e) {
      setToast({ msg: String(e), kind: 'err' })
    } finally {
      setDeleteBusy(false)
    }
  }

  // ── Counts ─────────────────────────────────────────────────────────────────
  const customCount = scenarios.filter(s => !isSeeded(s.scenario_id)).length

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div
      className="flex h-full flex-col bg-canvas text-text"
      onDragOver={e => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {dragOver && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-canvas/80 pointer-events-none">
          <div className="rounded-lg border-2 border-dashed border-accent px-12 py-8 text-center">
            <p className="text-sm text-accent font-semibold">Drop JSON file to upload</p>
            <p className="text-xs text-muted mt-1">Must include name, bess_units, turbine_units</p>
          </div>
        </div>
      )}

      {/* ── Toolbar ──────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 border-b border-border bg-surface px-6 py-3 flex-shrink-0">
        <div>
          <h2 className="text-sm font-semibold text-text">Scenario Library</h2>
          <p className="text-[10px] text-muted">
            {scenarios.length} total · {customCount} custom
          </p>
        </div>

        <div className="flex-1" />

        {/* Search */}
        <input
          type="search"
          placeholder="Search…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-48 rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                     placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-accent"
        />

        {/* Upload */}
        <input
          ref={fileRef}
          type="file"
          accept=".json"
          className="hidden"
          onChange={handleFileInput}
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploadBusy}
          title="Upload a ScenarioSpec JSON file"
          className="flex items-center gap-1.5 rounded border border-border px-3 py-1 text-xs
                     text-muted hover:border-accent hover:text-accent disabled:opacity-40
                     transition-colors"
        >
          {uploadBusy ? (
            <span className="inline-block h-3 w-3 animate-spin rounded-full border border-accent border-t-transparent" />
          ) : (
            <span>↑</span>
          )}
          Upload JSON
        </button>

        {/* New */}
        <button
          onClick={onNewScenario}
          className="rounded bg-accent px-3 py-1 text-xs font-semibold text-white
                     hover:bg-accent/80 transition-colors"
        >
          + New Scenario
        </button>
      </div>

      {/* ── Table ────────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-auto px-6 py-4">
        {isLoading && scenarios.length === 0 ? (
          <p className="mt-12 text-center text-xs text-muted">Loading…</p>
        ) : filtered.length === 0 ? (
          <div className="mt-12 text-center space-y-2">
            <p className="text-xs text-muted">
              {search ? 'No scenarios match your search.' : 'No scenarios found.'}
            </p>
            {!search && (
              <button
                onClick={onNewScenario}
                className="text-xs text-accent hover:underline"
              >
                Create your first custom scenario →
              </button>
            )}
          </div>
        ) : (
          <table className="w-full text-xs border-separate border-spacing-0">
            <thead>
              <tr className="text-muted">
                <th className="text-left pb-2 pr-4 font-medium uppercase tracking-wide text-[10px]">Name</th>
                <th className="text-left pb-2 pr-4 font-medium uppercase tracking-wide text-[10px]">ID</th>
                <th className="text-left pb-2 pr-4 font-medium uppercase tracking-wide text-[10px]">Type</th>
                <th className="text-left pb-2 pr-4 font-medium uppercase tracking-wide text-[10px] hidden lg:table-cell">Description</th>
                <th className="text-left pb-2 pr-4 font-medium uppercase tracking-wide text-[10px] hidden xl:table-cell">Created</th>
                <th className="text-right pb-2 font-medium uppercase tracking-wide text-[10px]">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(s => {
                const seeded  = isSeeded(s.scenario_id)
                const isConfirming = confirmId === s.scenario_id
                const isDown  = downloadBusy === s.scenario_id
                const isExec  = executeBusy === s.scenario_id

                return (
                  <tr
                    key={s.scenario_id}
                    className="group border-t border-border hover:bg-surface/60 transition-colors"
                  >
                    {/* Name */}
                    <td className="py-2.5 pr-4 font-medium text-text max-w-[160px]">
                      <span className="truncate block" title={s.name}>{s.name}</span>
                    </td>

                    {/* ID */}
                    <td className="py-2.5 pr-4">
                      <span
                        className="font-mono text-[10px] text-muted truncate block max-w-[140px]"
                        title={s.scenario_id}
                      >
                        {s.scenario_id}
                      </span>
                    </td>

                    {/* Type */}
                    <td className="py-2.5 pr-4 whitespace-nowrap">
                      {seeded
                        ? <Badge label="built-in" variant="muted" />
                        : <Badge label="custom"   variant="accent" />
                      }
                    </td>

                    {/* Description */}
                    <td className="py-2.5 pr-4 hidden lg:table-cell text-muted max-w-[240px]">
                      <span className="truncate block" title={s.description}>{s.description || '—'}</span>
                    </td>

                    {/* Created */}
                    <td className="py-2.5 pr-4 hidden xl:table-cell text-muted whitespace-nowrap font-mono text-[10px]">
                      {seeded ? '—' : formatDate(s.created_at)}
                    </td>

                    {/* Actions */}
                    <td className="py-2.5 text-right">
                      {isConfirming ? (
                        /* Delete confirmation inline */
                        <span className="inline-flex items-center gap-1.5">
                          <span className="text-danger text-[10px]">Delete "{s.name}"?</span>
                          <button
                            disabled={deleteBusy}
                            onClick={() => handleDeleteConfirm(s.scenario_id)}
                            className="rounded border border-danger px-2 py-0.5 text-[10px] text-danger
                                       hover:bg-danger/10 disabled:opacity-40 transition-colors"
                          >
                            {deleteBusy ? '…' : 'Confirm'}
                          </button>
                          <button
                            disabled={deleteBusy}
                            onClick={() => setConfirmId(null)}
                            className="rounded border border-border px-2 py-0.5 text-[10px] text-muted
                                       hover:text-text disabled:opacity-40 transition-colors"
                          >
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5">
                          {/* Execute — start run immediately */}
                          <button
                            onClick={() => handleExecute(s.scenario_id)}
                            disabled={!!executeBusy}
                            title="Start a run with this scenario"
                            className="inline-flex items-center gap-1 rounded border px-2 py-0.5
                                       text-[10px] font-semibold transition-colors disabled:opacity-40"
                            style={{
                              borderColor: isExec ? '#3fb6a8' : '#3fb6a8aa',
                              color:        '#3fb6a8',
                              background:   isExec ? 'rgba(63,182,168,0.12)' : 'rgba(63,182,168,0.06)',
                            }}
                          >
                            {isExec
                              ? <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border border-accent border-t-transparent" />
                              : <span>▶</span>
                            }
                            {isExec ? 'Starting…' : 'Run'}
                          </button>
                          {/* Edit */}
                          <button
                            onClick={() => onEditScenario(s.scenario_id)}
                            title="Edit scenario"
                            className="rounded border border-border px-2 py-0.5 text-[10px] text-muted
                                       hover:border-accent hover:text-accent transition-colors"
                          >
                            Edit
                          </button>

                          {/* Download */}
                          <button
                            onClick={() => handleDownload(s.scenario_id, s.name)}
                            disabled={isDown}
                            title="Download spec as JSON"
                            className="rounded border border-border px-2 py-0.5 text-[10px] text-muted
                                       hover:border-accent hover:text-accent disabled:opacity-40 transition-colors"
                          >
                            {isDown ? '…' : '↓ JSON'}
                          </button>

                          {/* Delete */}
                          <button
                            onClick={() => setConfirmId(s.scenario_id)}
                            disabled={seeded}
                            title={seeded ? 'Built-in scenarios cannot be deleted' : 'Delete scenario'}
                            className="rounded border border-border px-2 py-0.5 text-[10px] text-muted
                                       hover:border-danger hover:text-danger disabled:opacity-30
                                       disabled:cursor-not-allowed transition-colors"
                          >
                            Delete
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Upload hint */}
      <div className="border-t border-border bg-surface px-6 py-2 flex-shrink-0">
        <p className="text-[10px] text-muted">
          Drag a <span className="font-mono">.json</span> file anywhere onto this page to upload, or use the Upload JSON button.
          Required fields: <span className="font-mono">name</span>, <span className="font-mono">bess_units</span>, <span className="font-mono">turbine_units</span>.
          Download <a href="/scenario_spec_schema.json" target="_blank" className="text-accent hover:underline">schema ↗</a>
        </p>
      </div>

      {/* Toast */}
      {toast && (
        <Toast msg={toast.msg} kind={toast.kind} onDismiss={() => setToast(null)} />
      )}
    </div>
  )
}
