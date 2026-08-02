/**
 * ChangePasswordModal.tsx — In-session password change form.
 *
 * If the account has no password set yet (first use after OTP-only creation)
 * the "current password" field is hidden — the user just sets a new one.
 * The backend handles the same distinction server-side.
 */

import { FormEvent, useEffect, useState } from 'react'

interface Props {
  onClose: () => void
}

export function ChangePasswordModal({ onClose }: Props) {
  const [hasPassword, setHasPassword] = useState<boolean | null>(null)
  const [current,     setCurrent]     = useState('')
  const [next,        setNext]        = useState('')
  const [confirm,     setConfirm]     = useState('')
  const [error,       setError]       = useState<string | null>(null)
  const [success,     setSuccess]     = useState(false)
  const [loading,     setLoading]     = useState(false)

  // Ask the backend whether this account already has a password set.
  useEffect(() => {
    fetch('/api/auth/password-status', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then((d: { has_password: boolean } | null) => setHasPassword(d?.has_password ?? false))
      .catch(() => setHasPassword(false))
  }, [])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    if (next.length < 8) {
      setError('New password must be at least 8 characters.')
      return
    }
    if (next !== confirm) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      const resp = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          current_password: hasPassword ? current : null,
          new_password: next,
        }),
      })
      if (resp.ok) {
        setSuccess(true)
      } else {
        const body = await resp.json().catch(() => ({})) as { detail?: string }
        setError(body.detail ?? 'Could not update password — please try again.')
      }
    } catch {
      setError('Network error — please try again.')
    } finally {
      setLoading(false)
    }
  }

  const inputCls = `rounded border border-border px-3 py-2 font-sans outline-none
                    focus:border-[#3fb6a8] transition-colors w-full`
  const inputStyle = { background: '#0b1017', color: '#e6ecf2', fontSize: 13 } as const

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.6)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="flex flex-col gap-5 w-full max-w-sm rounded-lg border border-border p-8"
        style={{ background: '#111821' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="font-sans font-semibold" style={{ fontSize: 15, color: '#e6ecf2' }}>
            {hasPassword ? 'Change password' : 'Set a password'}
          </h2>
          <button
            onClick={onClose}
            className="font-sans text-muted hover:text-text transition-colors"
            style={{ fontSize: 18, background: 'none', border: 'none', cursor: 'pointer', lineHeight: 1 }}
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {success ? (
          <div className="flex flex-col gap-5">
            <div
              className="rounded px-3 py-3 font-sans text-center"
              style={{ background: '#0e2a1e', color: '#3fb6a8', fontSize: 13, border: '1px solid #1d5a40' }}
            >
              Password updated successfully.
            </div>
            <button
              onClick={onClose}
              className="rounded px-4 py-2.5 font-sans font-semibold transition-opacity"
              style={{ background: '#3fb6a8', color: '#0b1017', fontSize: 13 }}
            >
              Done
            </button>
          </div>
        ) : hasPassword === null ? (
          <p className="font-sans text-center" style={{ fontSize: 12, color: '#7d8b9c' }}>Loading…</p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {hasPassword && (
              <div className="flex flex-col gap-1.5">
                <label className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>
                  Current password
                </label>
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  value={current}
                  onChange={e => setCurrent(e.target.value)}
                  className={inputCls}
                  style={inputStyle}
                />
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>
                New password
              </label>
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={next}
                onChange={e => setNext(e.target.value)}
                placeholder="At least 8 characters"
                className={inputCls}
                style={inputStyle}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>
                Confirm new password
              </label>
              <input
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={e => setConfirm(e.target.value)}
                className={inputCls}
                style={inputStyle}
              />
            </div>

            {error && (
              <div
                className="rounded px-3 py-2 font-sans text-center"
                style={{ background: '#2a1a1a', color: '#e05a5a', fontSize: 12, border: '1px solid #5a2020' }}
              >
                {error}
              </div>
            )}

            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 rounded px-4 py-2.5 font-sans transition-colors border border-border
                           text-muted hover:text-text hover:border-muted/50"
                style={{ fontSize: 13, background: 'none' }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex-1 rounded px-4 py-2.5 font-sans font-semibold tracking-wide
                           transition-opacity disabled:opacity-50"
                style={{ background: '#3fb6a8', color: '#0b1017', fontSize: 13 }}
              >
                {loading ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
