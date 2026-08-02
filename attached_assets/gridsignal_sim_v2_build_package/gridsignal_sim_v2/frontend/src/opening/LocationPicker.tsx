/**
 * LocationPicker.tsx — compact data-centre location badge + editor.
 *
 * Shows the current site location (e.g. "San Diego, CA") as a small pill.
 * Clicking the pencil icon opens an inline text field; submitting it PUTs
 * the new address to /api/location, which geocodes it via Mistral and
 * stores it on the server.  The callback fires after a successful update so
 * the parent can refresh the solar-preview badge.
 *
 * Usage
 * -----
 *   <LocationPicker onLocationChanged={() => refreshSolarPreview()} />
 */

import { useState, useEffect, useRef } from 'react'

interface Location {
  name:               string
  lat:                number
  lon:                number
  utc_offset_h:       number
  climate_hint:       string
  ambient_temp_base_c: number
}

interface LocationPickerProps {
  /** Called after a successful location change so the parent can re-fetch solar-preview. */
  onLocationChanged?: (loc: Location) => void
}

export function LocationPicker({ onLocationChanged }: LocationPickerProps) {
  const [location,   setLocation]   = useState<Location | null>(null)
  const [editing,    setEditing]    = useState(false)
  const [draft,      setDraft]      = useState('')
  const [loading,    setLoading]    = useState(false)
  const [error,      setError]      = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Fetch current location on mount
  useEffect(() => {
    fetch('/api/location')
      .then(r => r.ok ? r.json() : null)
      .then((d: Location | null) => { if (d) setLocation(d) })
      .catch(() => {})
  }, [])

  // Focus the input when editing opens
  useEffect(() => {
    if (editing) {
      setDraft(location?.name ?? '')
      setError(null)
      setTimeout(() => inputRef.current?.select(), 10)
    }
  }, [editing, location?.name])

  async function handleSubmit() {
    if (!draft.trim() || loading) return
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch('/api/location', {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ address: draft.trim() }),
      })
      const data = await resp.json()
      if (!resp.ok) {
        setError(data.error ?? 'Failed to resolve location')
        setLoading(false)
        return
      }
      setLocation(data as Location)
      setEditing(false)
      onLocationChanged?.(data as Location)
    } catch {
      setError('Network error — server unreachable')
    } finally {
      setLoading(false)
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') handleSubmit()
    if (e.key === 'Escape') { setEditing(false); setError(null) }
  }

  const utcLabel = location
    ? `UTC${location.utc_offset_h >= 0 ? '+' : ''}${location.utc_offset_h}`
    : ''

  // ── Edit mode ────────────────────────────────────────────────────────────
  if (editing) {
    return (
      <div className="flex items-center gap-1" style={{ minWidth: 240 }}>
        <input
          ref={inputRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={handleKey}
          placeholder="City, Country…"
          disabled={loading}
          className="font-mono text-[10px] bg-transparent border-b outline-none"
          style={{
            color:       '#e6edf3',
            borderColor: error ? '#e05252' : '#3fb6a8',
            width:       160,
            paddingBottom: 1,
          }}
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !draft.trim()}
          className="font-mono text-[9px] px-2 py-0.5 rounded transition-colors"
          style={{
            background: loading ? '#1e2a38' : '#0d2433',
            color:      loading ? '#4b5764' : '#3fb6a8',
            border:     '1px solid #1e3a50',
            cursor:     loading ? 'wait' : 'pointer',
          }}
        >
          {loading ? '…' : 'Apply'}
        </button>
        <button
          onClick={() => { setEditing(false); setError(null) }}
          disabled={loading}
          className="font-mono text-[9px] px-1.5 py-0.5 rounded transition-colors"
          style={{
            background: '#1e2a38',
            color:      '#4b5764',
            border:     '1px solid #1e2a38',
          }}
        >
          ✕
        </button>
        {error && (
          <span className="font-mono text-[9px]" style={{ color: '#e05252' }}>
            {error}
          </span>
        )}
      </div>
    )
  }

  // ── Display mode ─────────────────────────────────────────────────────────
  return (
    <div
      className="flex items-center gap-1.5 select-none"
      title={location ? `${location.climate_hint} · lat ${location.lat.toFixed(2)}, lon ${location.lon.toFixed(2)}, ${utcLabel}` : ''}
    >
      <span className="font-mono text-[9px]" style={{ color: '#4b5764' }}>
        📍
      </span>
      <span className="font-mono text-[9px]" style={{ color: '#7d8b9c' }}>
        {location?.name ?? '…'}
      </span>
      {location && (
        <span className="font-mono text-[8px]" style={{ color: '#3a4555' }}>
          {utcLabel}
        </span>
      )}
      <button
        onClick={() => setEditing(true)}
        className="font-mono text-[8px] leading-none transition-colors hover:text-teal-400"
        style={{ color: '#3a4555', background: 'none', border: 'none', cursor: 'pointer', padding: '0 2px' }}
        title="Change data-centre location"
        aria-label="Edit data-centre location"
      >
        ✎
      </button>
    </div>
  )
}
