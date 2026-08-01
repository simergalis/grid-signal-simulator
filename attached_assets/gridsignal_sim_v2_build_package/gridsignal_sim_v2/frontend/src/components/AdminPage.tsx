/**
 * AdminPage.tsx — User management panel (role=admin only).
 *
 * Reads from and writes to /api/admin/users using the session cookie
 * (no X-Admin-Key required in the browser; the server accepts the cookie
 * for users whose role is "admin").
 */

import { useCallback, useEffect, useReducer, useRef, useState } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface User {
  id: number
  email: string
  phone: string
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
  onCreated: (u: User, tmpPw: string) => void
}

function AddUserModal({ onClose, onCreated }: AddUserModalProps) {
  const [email,    setEmail]    = useState('')
  const [phone,    setPhone]    = useState('')
  const [name,     setName]     = useState('')
  const [role,     setRole]     = useState<Role>('operator')
  const [tmpPw,    setTmpPw]    = useState('')
  const [error,    setError]    = useState<string | null>(null)
  const [loading,  setLoading]  = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const body: Record<string, string> = { email, phone, display_name: name, role }
      if (tmpPw.trim()) body.temporary_password = tmpPw.trim()

      const resp = await fetch('/api/admin/users', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(err.detail ?? 'Failed to create user')
      }
      const user: User = await resp.json()
      // Surface the password that was actually used
      const usedPw = tmpPw.trim() || '(auto-generated — check welcome email)'
      onCreated(user, usedPw)
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
        style={{ background: '#151d26', width: 440, padding: '28px 28px 24px' }}
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-sans font-semibold" style={{ fontSize: 15, color: '#e6ecf2' }}>
            Add operator account
          </h2>
          <button onClick={onClose} style={{ color: '#7d8b9c', fontSize: 18, lineHeight: 1 }}>✕</button>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-3">
          {/* Email */}
          <label className="flex flex-col gap-1">
            <span className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>Email address *</span>
            <input
              type="email" required value={email} onChange={e => setEmail(e.target.value)}
              placeholder="operator@example.com"
              className="rounded border border-border bg-canvas px-3 py-2 font-sans outline-none
                         focus:border-accent"
              style={{ fontSize: 13, color: '#e6ecf2' }}
            />
          </label>

          {/* Phone */}
          <label className="flex flex-col gap-1">
            <span className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>Mobile phone number *</span>
            <input
              type="tel" required value={phone} onChange={e => setPhone(e.target.value)}
              placeholder="+1 555 000 0000"
              className="rounded border border-border bg-canvas px-3 py-2 font-sans outline-none
                         focus:border-accent"
              style={{ fontSize: 13, color: '#e6ecf2' }}
            />
          </label>

          {/* Display name */}
          <label className="flex flex-col gap-1">
            <span className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>Display name *</span>
            <input
              type="text" required value={name} onChange={e => setName(e.target.value)}
              placeholder="Alex Smith"
              className="rounded border border-border bg-canvas px-3 py-2 font-sans outline-none
                         focus:border-accent"
              style={{ fontSize: 13, color: '#e6ecf2' }}
            />
          </label>

          {/* Role */}
          <label className="flex flex-col gap-1">
            <span className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>Role</span>
            <select
              value={role} onChange={e => setRole(e.target.value as Role)}
              className="rounded border border-border bg-canvas px-3 py-2 font-sans outline-none
                         focus:border-accent"
              style={{ fontSize: 13, color: '#e6ecf2' }}
            >
              {ROLES.map(r => (
                <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
              ))}
            </select>
          </label>

          {/* Temporary password */}
          <label className="flex flex-col gap-1">
            <span className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>
              Temporary password
              <span style={{ color: '#4b5764' }}> (leave blank to auto-generate)</span>
            </span>
            <input
              type="text" value={tmpPw} onChange={e => setTmpPw(e.target.value)}
              placeholder="auto-generate"
              className="rounded border border-border bg-canvas px-3 py-2 font-sans outline-none
                         focus:border-accent"
              style={{ fontSize: 13, color: '#e6ecf2' }}
            />
          </label>

          {error && (
            <div
              className="rounded px-3 py-2 font-sans"
              style={{ fontSize: 12, color: '#f87171', background: '#f8717115', border: '1px solid #f8717130' }}
            >
              {error}
            </div>
          )}

          <div className="flex gap-2 justify-end mt-1">
            <button
              type="button" onClick={onClose}
              className="px-4 py-2 rounded border border-border font-sans text-muted
                         hover:text-text transition-colors"
              style={{ fontSize: 12 }}
            >
              Cancel
            </button>
            <button
              type="submit" disabled={loading}
              className="px-4 py-2 rounded font-sans font-medium transition-opacity"
              style={{
                fontSize: 12, background: '#3fb6a8', color: '#0b1017',
                opacity: loading ? 0.6 : 1,
              }}
            >
              {loading ? 'Creating…' : 'Create account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Created confirmation banner ───────────────────────────────────────────────

function CreatedBanner({ user, tmpPw, onDismiss }: { user: User; tmpPw: string; onDismiss: () => void }) {
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
          &nbsp;·&nbsp;
          Temporary password: <code
            className="rounded px-1.5 py-0.5"
            style={{ fontSize: 11, background: '#1a2c1e', color: '#4ade80', fontFamily: 'monospace' }}
          >{tmpPw}</code>
        </div>
        <div className="font-sans mt-0.5" style={{ fontSize: 11, color: '#4b5764' }}>
          A welcome email has been sent if SendGrid is configured.
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
  const [created,    setCreated]    = useState<{ user: User; tmpPw: string } | null>(null)
  const [busy,       setBusy]       = useState<number | null>(null)   // id of row being patched
  const [deleteConf, setDeleteConf] = useState<number | null>(null)   // id awaiting delete confirm
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

        {/* Created banner */}
        {created && (
          <CreatedBanner
            user={created.user}
            tmpPw={created.tmpPw}
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
                  {['Name', 'Email', 'Phone', 'Role', 'Status', ''].map(h => (
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

                    {/* Phone */}
                    <td className="font-sans px-3.5 py-3" style={{ fontSize: 12, color: '#7d8b9c', whiteSpace: 'nowrap' }}>
                      {u.phone}
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
                        <button
                          disabled={busy === u.id}
                          onClick={() => setDeleteConf(u.id)}
                          className="font-sans hover:text-red-400 transition-colors"
                          style={{ fontSize: 11, color: '#4b5764' }}
                          aria-label="Delete account"
                        >
                          Delete
                        </button>
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
          onCreated={(u, pw) => {
            dispatch({ type: 'upsert', user: u })
            setCreated({ user: u, tmpPw: pw })
            setShowAdd(false)
          }}
        />
      )}
    </div>
  )
}
