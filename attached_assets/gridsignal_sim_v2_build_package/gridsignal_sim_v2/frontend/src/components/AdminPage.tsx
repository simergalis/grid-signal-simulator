/**
 * AdminPage.tsx — User management panel (role=admin only).
 *
 * Reads from and writes to /api/admin/users using the session cookie
 * (no X-Admin-Key required in the browser; the server accepts the cookie
 * for users whose role is "admin").
 */

import { useCallback, useEffect, useReducer, useRef, useState } from 'react'

// ── Email delivery types ──────────────────────────────────────────────────────

interface EmailCheckResult {
  ok: boolean
  api_key_set: boolean
  from_email: string
  is_default: boolean
  sendgrid_pkg: boolean
  issues: string[]
}

// ── Email delivery diagnostic panel ──────────────────────────────────────────

function EmailDeliveryPanel({ onClose }: { onClose: () => void }) {
  const [check,       setCheck]       = useState<EmailCheckResult | null>(null)
  const [checkErr,    setCheckErr]    = useState<string | null>(null)
  const [testState,   setTestState]   = useState<'idle' | 'sending' | 'ok' | 'fail'>('idle')
  const [testMsg,     setTestMsg]     = useState<string>('')

  useEffect(() => {
    fetch('/api/admin/email-check', { credentials: 'include' })
      .then(r => r.ok ? r.json() : Promise.reject(`${r.status} ${r.statusText}`))
      .then((data: EmailCheckResult) => setCheck(data))
      .catch((e: unknown) => setCheckErr(String(e)))
  }, [])

  const sendTest = async () => {
    setTestState('sending')
    setTestMsg('')
    try {
      const resp = await fetch('/api/admin/email-test', {
        method: 'POST',
        credentials: 'include',
      })
      const data = await resp.json().catch(() => ({}))
      if (resp.ok && data.sent) {
        setTestState('ok')
        setTestMsg(`Test OTP sent to ${data.to} — check your inbox.`)
      } else if (resp.ok && !data.sent) {
        setTestState('fail')
        setTestMsg(data.reason ?? 'Delivery failed — check server logs.')
      } else {
        setTestState('fail')
        setTestMsg(data.detail ?? `HTTP ${resp.status}`)
      }
    } catch (e: unknown) {
      setTestState('fail')
      setTestMsg(String(e))
    }
  }

  const Row = ({ label, value, ok }: { label: string; value: string; ok: boolean }) => (
    <div className="flex items-start gap-3 py-2" style={{ borderBottom: '1px solid #1a2330' }}>
      <span
        className="font-sans"
        style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', color: ok ? '#4ade80' : '#f87171', minWidth: 36 }}
      >
        {ok ? '✓' : '✗'}
      </span>
      <span className="font-sans" style={{ fontSize: 12, color: '#7d8b9c', minWidth: 120 }}>{label}</span>
      <span className="font-sans font-medium" style={{ fontSize: 12, color: '#e6ecf2', wordBreak: 'break-all' }}>{value}</span>
    </div>
  )

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="rounded-lg border border-border"
        style={{ background: '#151d26', width: 520, padding: '28px 28px 24px', maxHeight: '80vh', overflowY: 'auto' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-sans font-semibold" style={{ fontSize: 15, color: '#e6ecf2' }}>
            Email delivery diagnostic
          </h2>
          <button onClick={onClose} style={{ color: '#7d8b9c', fontSize: 18, lineHeight: 1 }}>✕</button>
        </div>

        {checkErr ? (
          <div className="rounded px-3 py-2 font-sans"
               style={{ fontSize: 12, color: '#f87171', background: '#f8717115', border: '1px solid #f8717130' }}>
            Could not load diagnostic: {checkErr}
          </div>
        ) : check === null ? (
          <div className="font-sans py-8 text-center" style={{ fontSize: 13, color: '#4b5764' }}>Loading…</div>
        ) : (
          <>
            {/* Status badge */}
            <div
              className="flex items-center gap-2 rounded px-3 py-2 mb-4"
              style={{
                background: check.ok ? '#0d2b1e' : '#2b1010',
                border: `1px solid ${check.ok ? '#166534' : '#7f1d1d'}`,
              }}
            >
              <span style={{ fontSize: 14 }}>{check.ok ? '✓' : '⚠'}</span>
              <span className="font-sans font-medium" style={{ fontSize: 12, color: check.ok ? '#4ade80' : '#f87171' }}>
                {check.ok ? 'Email delivery looks healthy' : 'Configuration issues detected'}
              </span>
            </div>

            {/* Rows */}
            <div className="mb-4">
              <Row label="API key set"     value={check.api_key_set  ? 'Yes' : 'No'}  ok={check.api_key_set} />
              <Row label="SendGrid pkg"    value={check.sendgrid_pkg ? 'Yes' : 'No'}  ok={check.sendgrid_pkg} />
              <Row label="From address"    value={check.from_email}                   ok={!check.is_default} />
              <Row label="Custom sender"   value={check.is_default   ? 'No — still using default' : 'Yes'} ok={!check.is_default} />
            </div>

            {/* Issues list */}
            {check.issues.length > 0 && (
              <div className="mb-4">
                <div className="font-sans mb-1.5" style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', color: '#7d8b9c' }}>
                  ISSUES
                </div>
                <ul className="flex flex-col gap-1.5">
                  {check.issues.map((iss, i) => (
                    <li
                      key={i}
                      className="font-sans rounded px-3 py-2"
                      style={{ fontSize: 12, color: '#f87171', background: '#f8717110', border: '1px solid #f8717120' }}
                    >
                      {iss}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Test send */}
            <div style={{ borderTop: '1px solid #1a2330', paddingTop: 16 }}>
              <div className="font-sans mb-2" style={{ fontSize: 11, color: '#7d8b9c' }}>
                Send a real test OTP to your own inbox to confirm end-to-end delivery.
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={sendTest}
                  disabled={testState === 'sending'}
                  className="px-4 py-2 rounded font-sans font-medium transition-opacity"
                  style={{
                    fontSize: 12,
                    background: '#3fb6a8',
                    color: '#0b1017',
                    opacity: testState === 'sending' ? 0.6 : 1,
                  }}
                >
                  {testState === 'sending' ? 'Sending…' : 'Send test OTP to me'}
                </button>

                {testState === 'ok' && (
                  <span className="font-sans" style={{ fontSize: 12, color: '#4ade80' }}>✓ {testMsg}</span>
                )}
                {testState === 'fail' && (
                  <span className="font-sans" style={{ fontSize: 12, color: '#f87171' }}>✗ {testMsg}</span>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ── Types ────────────────────────────────────────────────────────────────────

interface User {
  id: number
  email: string
  display_name: string
  role: string
  is_active: boolean
}

const ROLES = ['viewer', 'operator', 'approver', 'admin'] as const
type Role = typeof ROLES[number]

// ── Helpers ──────────────────────────────────────────────────────────────────

// ── Add-user modal ────────────────────────────────────────────────────────────

interface AddUserModalProps {
  onClose: () => void
  onCreated: (u: User) => void
}

function AddUserModal({ onClose, onCreated }: AddUserModalProps) {
  const [email,   setEmail]   = useState('')
  const [name,    setName]    = useState('')
  const [role,    setRole]    = useState<Role>('operator')
  const [error,   setError]   = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const resp = await fetch('/api/admin/users', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, display_name: name, role }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(err.detail ?? 'Failed to create user')
      }
      onCreated(await resp.json())
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="rounded-lg border border-border"
        style={{ background: '#151d26', width: 420, padding: '28px 28px 24px' }}
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-sans font-semibold" style={{ fontSize: 15, color: '#e6ecf2' }}>
            Add account
          </h2>
          <button onClick={onClose} style={{ color: '#7d8b9c', fontSize: 18, lineHeight: 1 }}>✕</button>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>Email address *</span>
            <input
              type="email" required value={email} onChange={e => setEmail(e.target.value)}
              placeholder="operator@example.com"
              className="rounded border border-border bg-canvas px-3 py-2 font-sans outline-none focus:border-accent"
              style={{ fontSize: 13, color: '#e6ecf2' }}
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>Display name *</span>
            <input
              type="text" required value={name} onChange={e => setName(e.target.value)}
              placeholder="Alex Smith"
              className="rounded border border-border bg-canvas px-3 py-2 font-sans outline-none focus:border-accent"
              style={{ fontSize: 13, color: '#e6ecf2' }}
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>Role</span>
            <select
              value={role} onChange={e => setRole(e.target.value as Role)}
              className="rounded border border-border bg-canvas px-3 py-2 font-sans outline-none focus:border-accent"
              style={{ fontSize: 13, color: '#e6ecf2' }}
            >
              {ROLES.map(r => (
                <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
              ))}
            </select>
          </label>

          <p className="font-sans" style={{ fontSize: 11, color: '#4b5764' }}>
            The user will sign in with their email and a one-time code — no password required.
          </p>

          {error && (
            <div className="rounded px-3 py-2 font-sans"
                 style={{ fontSize: 12, color: '#f87171', background: '#f8717115', border: '1px solid #f8717130' }}>
              {error}
            </div>
          )}

          <div className="flex gap-2 justify-end mt-1">
            <button type="button" onClick={onClose}
                    className="px-4 py-2 rounded border border-border font-sans text-muted hover:text-text transition-colors"
                    style={{ fontSize: 12 }}>
              Cancel
            </button>
            <button type="submit" disabled={loading}
                    className="px-4 py-2 rounded font-sans font-medium transition-opacity"
                    style={{ fontSize: 12, background: '#3fb6a8', color: '#0b1017', opacity: loading ? 0.6 : 1 }}>
              {loading ? 'Creating…' : 'Create account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Reset password modal ──────────────────────────────────────────────────────

interface ResetPasswordModalProps {
  user: User
  onClose: () => void
  onDone: () => void
}

function ResetPasswordModal({ user, onClose, onDone }: ResetPasswordModalProps) {
  const [password,  setPassword]  = useState('')
  const [confirm,   setConfirm]   = useState('')
  const [error,     setError]     = useState<string | null>(null)
  const [loading,   setLoading]   = useState(false)
  const [success,   setSuccess]   = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    setLoading(true)
    try {
      const resp = await fetch(`/api/admin/users/${user.id}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(err.detail ?? 'Failed to reset password')
      }
      setSuccess(true)
      setTimeout(onDone, 1200)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="rounded-lg border border-border"
        style={{ background: '#151d26', width: 400, padding: '28px 28px 24px' }}
      >
        <div className="flex items-center justify-between mb-1">
          <h2 className="font-sans font-semibold" style={{ fontSize: 15, color: '#e6ecf2' }}>
            Reset password
          </h2>
          <button onClick={onClose} style={{ color: '#7d8b9c', fontSize: 18, lineHeight: 1 }}>✕</button>
        </div>
        <p className="font-sans mb-4" style={{ fontSize: 12, color: '#7d8b9c' }}>
          Setting a new password for <span style={{ color: '#e6ecf2' }}>{user.display_name}</span> ({user.email})
        </p>

        {success ? (
          <div className="rounded px-3 py-2 font-sans"
               style={{ fontSize: 13, color: '#4ade80', background: '#4ade8015', border: '1px solid #4ade8030' }}>
            ✓ Password updated successfully
          </div>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1">
              <span className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>New password *</span>
              <input
                type="password" required value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Minimum 8 characters"
                autoFocus
                className="rounded border border-border bg-canvas px-3 py-2 font-sans outline-none focus:border-accent"
                style={{ fontSize: 13, color: '#e6ecf2' }}
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>Confirm password *</span>
              <input
                type="password" required value={confirm}
                onChange={e => setConfirm(e.target.value)}
                placeholder="Repeat new password"
                className="rounded border border-border bg-canvas px-3 py-2 font-sans outline-none focus:border-accent"
                style={{ fontSize: 13, color: '#e6ecf2' }}
              />
            </label>

            {error && (
              <div className="rounded px-3 py-2 font-sans"
                   style={{ fontSize: 12, color: '#f87171', background: '#f8717115', border: '1px solid #f8717130' }}>
                {error}
              </div>
            )}

            <div className="flex gap-2 justify-end mt-1">
              <button type="button" onClick={onClose}
                      className="px-4 py-2 rounded border border-border font-sans text-muted hover:text-text transition-colors"
                      style={{ fontSize: 12 }}>
                Cancel
              </button>
              <button type="submit" disabled={loading}
                      className="px-4 py-2 rounded font-sans font-medium transition-opacity"
                      style={{ fontSize: 12, background: '#3fb6a8', color: '#0b1017', opacity: loading ? 0.6 : 1 }}>
                {loading ? 'Saving…' : 'Set password'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

// ── Created confirmation banner ───────────────────────────────────────────────

function CreatedBanner({ user, onDismiss }: { user: User; onDismiss: () => void }) {
  return (
    <div
      className="rounded-lg border flex items-start gap-3 p-4 mb-4"
      style={{ background: '#0d2b1e', borderColor: '#166534' }}
    >
      <span style={{ fontSize: 18 }}>✓</span>
      <div className="flex-1 min-w-0">
        <div className="font-sans font-medium" style={{ fontSize: 13, color: '#4ade80' }}>
          Account created — {user.display_name}
        </div>
        <div className="font-sans mt-1" style={{ fontSize: 12, color: '#7d8b9c' }}>
          Email: <span style={{ color: '#e6ecf2' }}>{user.email}</span>
          &nbsp;·&nbsp;Role: <span style={{ color: '#e6ecf2' }}>{user.role}</span>
        </div>
        <div className="font-sans mt-0.5" style={{ fontSize: 11, color: '#4b5764' }}>
          They can sign in immediately using their email and a one-time code.
        </div>
      </div>
      <button onClick={onDismiss} style={{ color: '#4b5764', fontSize: 16, lineHeight: 1 }}>✕</button>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

type Action =
  | { type: 'set'; users: User[] }
  | { type: 'upsert'; user: User }
  | { type: 'remove'; id: number }

function reducer(state: User[], action: Action): User[] {
  if (action.type === 'set')    return action.users
  if (action.type === 'upsert') return state.some(u => u.id === action.user.id)
    ? state.map(u => u.id === action.user.id ? action.user : u)
    : [...state, action.user]
  if (action.type === 'remove') return state.filter(u => u.id !== action.id)
  return state
}

export function AdminPage() {
  const [users,      dispatch]      = useReducer(reducer, [])
  const [loading,    setLoading]    = useState(true)
  const [error,      setError]      = useState<string | null>(null)
  const [showAdd,    setShowAdd]    = useState(false)
  const [created,    setCreated]    = useState<User | null>(null)
  const [busy,       setBusy]       = useState<number | null>(null)   // id of row being patched
  const [deleteConf, setDeleteConf] = useState<number | null>(null)   // id awaiting delete confirm
  const [resetPwUser, setResetPwUser] = useState<User | null>(null)   // user whose password is being reset
  const [emailCheck,  setEmailCheck]  = useState<EmailCheckResult | null>(null)
  const [showEmailPanel, setShowEmailPanel] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const load = useCallback(async () => {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch('/api/admin/users', {
        credentials: 'include',
        signal: abortRef.current.signal,
      })
      if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`)
      dispatch({ type: 'set', users: await resp.json() })
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        setError(err instanceof Error ? err.message : String(err))
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  // Load email delivery status once on mount (non-blocking, best-effort)
  useEffect(() => {
    fetch('/api/admin/email-check', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then((data: EmailCheckResult | null) => { if (data) setEmailCheck(data) })
      .catch(() => { /* swallow — not critical */ })
  }, [])

  const patch = async (id: number, body: Partial<{ is_active: boolean; role: string }>) => {
    setBusy(id)
    try {
      const resp = await fetch(`/api/admin/users/${id}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!resp.ok) throw new Error(`Patch failed: ${resp.status}`)
      dispatch({ type: 'upsert', user: await resp.json() })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

  const deleteUser = async (id: number) => {
    setDeleteConf(null)
    setBusy(id)
    try {
      const resp = await fetch(`/api/admin/users/${id}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!resp.ok && resp.status !== 204) throw new Error(`Delete failed: ${resp.status}`)
      dispatch({ type: 'remove', id })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex-1 overflow-auto p-6" style={{ background: '#0b1017' }}>
      <div style={{ maxWidth: 840, margin: '0 auto' }}>

        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h1 className="font-sans font-semibold" style={{ fontSize: 16, color: '#e6ecf2' }}>
              Operator accounts
            </h1>
            <p className="font-sans mt-0.5" style={{ fontSize: 12, color: '#7d8b9c' }}>
              Manage who can sign in to GridSignal.
            </p>
          </div>
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 rounded font-sans font-medium px-4 py-2 transition-opacity
                       hover:opacity-90"
            style={{ fontSize: 12, background: '#3fb6a8', color: '#0b1017' }}
          >
            + Add account
          </button>
        </div>

        {/* Email delivery status row */}
        {emailCheck !== null && (
          <button
            onClick={() => setShowEmailPanel(true)}
            className="w-full flex items-center gap-3 rounded-lg border px-4 py-3 mb-4 text-left transition-opacity hover:opacity-80"
            style={{
              background:   emailCheck.ok ? '#0d2b1e' : '#1f1208',
              borderColor:  emailCheck.ok ? '#166534' : '#92400e',
            }}
          >
            <span style={{ fontSize: 14 }}>{emailCheck.ok ? '✓' : '⚠'}</span>
            <div className="flex-1 min-w-0">
              <span className="font-sans font-medium" style={{ fontSize: 12, color: emailCheck.ok ? '#4ade80' : '#fbbf24' }}>
                Email delivery
              </span>
              <span className="font-sans ml-2" style={{ fontSize: 12, color: '#7d8b9c' }}>
                {emailCheck.ok
                  ? `Healthy · ${emailCheck.from_email}`
                  : emailCheck.issues[0] ?? 'Configuration issue detected'}
              </span>
            </div>
            <span className="font-sans" style={{ fontSize: 11, color: '#4b5764' }}>Details →</span>
          </button>
        )}

        {/* Created banner */}
        {created && (
          <CreatedBanner
            user={created}
            onDismiss={() => setCreated(null)}
          />
        )}

        {/* Error banner */}
        {error && (
          <div
            className="rounded-lg border px-4 py-3 mb-4 font-sans flex items-center justify-between"
            style={{ fontSize: 12, color: '#f87171', background: '#f8717110', borderColor: '#f8717130' }}
          >
            {error}
            <button onClick={() => setError(null)} style={{ color: '#f87171', fontSize: 14 }}>✕</button>
          </div>
        )}

        {/* Table */}
        {loading ? (
          <div className="font-sans py-12 text-center" style={{ fontSize: 13, color: '#4b5764' }}>
            Loading…
          </div>
        ) : users.length === 0 ? (
          <div
            className="rounded-lg border border-dashed flex flex-col items-center justify-center py-16 gap-3"
            style={{ borderColor: '#2a3340', color: '#4b5764' }}
          >
            <div style={{ fontSize: 32 }}>👤</div>
            <div className="font-sans" style={{ fontSize: 13 }}>No accounts yet</div>
            <button
              onClick={() => setShowAdd(true)}
              className="font-sans text-accent underline"
              style={{ fontSize: 12 }}
            >
              Create the first account
            </button>
          </div>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#111821', borderBottom: '1px solid #1e2a36' }}>
                  {['Name', 'Email', 'Role', 'Status', ''].map(h => (
                    <th
                      key={h}
                      className="font-sans text-left"
                      style={{
                        fontSize: 10, fontWeight: 600, letterSpacing: '0.08em',
                        color: '#4b5764', padding: '10px 14px',
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((u, i) => (
                  <tr
                    key={u.id}
                    style={{
                      borderBottom: i < users.length - 1 ? '1px solid #1a2330' : undefined,
                      background: busy === u.id ? '#111821' : 'transparent',
                      opacity: busy === u.id ? 0.6 : 1,
                      transition: 'opacity 0.15s',
                    }}
                  >
                    {/* Name */}
                    <td className="font-sans px-3.5 py-3" style={{ fontSize: 13, color: '#e6ecf2' }}>
                      {u.display_name}
                    </td>

                    {/* Email */}
                    <td className="font-sans px-3.5 py-3" style={{ fontSize: 12, color: '#7d8b9c' }}>
                      {u.email}
                    </td>

                    {/* Role */}
                    <td className="px-3.5 py-3">
                      <select
                        value={u.role}
                        disabled={busy === u.id}
                        onChange={e => patch(u.id, { role: e.target.value })}
                        className="rounded border border-border bg-canvas font-sans outline-none
                                   focus:border-accent"
                        style={{ fontSize: 11, color: '#e6ecf2', padding: '2px 6px' }}
                      >
                        {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </td>

                    {/* Status */}
                    <td className="px-3.5 py-3">
                      <button
                        disabled={busy === u.id}
                        onClick={() => patch(u.id, { is_active: !u.is_active })}
                        className="font-sans rounded border transition-colors"
                        style={{
                          fontSize: 10, fontWeight: 600, letterSpacing: '0.07em',
                          padding: '2px 8px',
                          color:      u.is_active ? '#4ade80' : '#7d8b9c',
                          border:     `1px solid ${u.is_active ? '#4ade8040' : '#2a3340'}`,
                          background: u.is_active ? '#4ade8015' : 'transparent',
                        }}
                      >
                        {u.is_active ? 'ACTIVE' : 'INACTIVE'}
                      </button>
                    </td>

                    {/* Actions */}
                    <td className="px-3.5 py-3 text-right">
                      {deleteConf === u.id ? (
                        <span className="flex items-center gap-1.5 justify-end">
                          <span className="font-sans" style={{ fontSize: 11, color: '#f87171' }}>Delete?</span>
                          <button
                            onClick={() => deleteUser(u.id)}
                            className="font-sans rounded px-2 py-0.5"
                            style={{ fontSize: 11, background: '#f8717120', color: '#f87171', border: '1px solid #f8717140' }}
                          >
                            Yes
                          </button>
                          <button
                            onClick={() => setDeleteConf(null)}
                            className="font-sans"
                            style={{ fontSize: 11, color: '#7d8b9c' }}
                          >
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <span className="flex items-center gap-3 justify-end">
                          <button
                            disabled={busy === u.id}
                            onClick={() => setResetPwUser(u)}
                            className="font-sans hover:text-accent transition-colors"
                            style={{ fontSize: 11, color: '#4b5764' }}
                            aria-label="Reset password"
                          >
                            Reset pw
                          </button>
                          <button
                            disabled={busy === u.id}
                            onClick={() => setDeleteConf(u.id)}
                            className="font-sans hover:text-red-400 transition-colors"
                            style={{ fontSize: 11, color: '#4b5764' }}
                            aria-label="Delete account"
                          >
                            Delete
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add user modal */}
      {showAdd && (
        <AddUserModal
          onClose={() => setShowAdd(false)}
          onCreated={u => {
            dispatch({ type: 'upsert', user: u })
            setCreated(u)
            setShowAdd(false)
          }}
        />
      )}

      {/* Reset password modal */}
      {resetPwUser && (
        <ResetPasswordModal
          user={resetPwUser}
          onClose={() => setResetPwUser(null)}
          onDone={() => setResetPwUser(null)}
        />
      )}

      {/* Email delivery diagnostic panel */}
      {showEmailPanel && (
        <EmailDeliveryPanel onClose={() => setShowEmailPanel(false)} />
      )}
    </div>
  )
}
