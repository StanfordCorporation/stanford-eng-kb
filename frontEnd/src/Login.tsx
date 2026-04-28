import { useState } from 'react'

import { login } from './lib'

export default function Login({ onSuccess }: { onSuccess: () => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!password.trim() || submitting) return

    setSubmitting(true)
    setError(null)
    const result = await login(password)
    setSubmitting(false)

    if (result.ok) {
      onSuccess()
      return
    }
    setError(result.message)
    setPassword('')
  }

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={onSubmit}>
        <div className="login-brand">Stanford KB</div>
        <div className="login-hint">Enter the access password to continue.</div>

        <input
          className="login-input"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          disabled={submitting}
        />

        <button
          type="submit"
          className="login-submit"
          disabled={submitting || !password.trim()}
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>

        {error && <div className="login-error">{error}</div>}
      </form>
    </div>
  )
}
