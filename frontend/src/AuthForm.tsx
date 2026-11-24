import { type FormEvent, useState } from 'react'
import { confirmSignUp, signIn, signUp } from './auth'

type Mode = 'signIn' | 'signUp' | 'confirm'

/** Sign in, create an account, or enter the 6-digit code Cognito emails after sign-up. */
export default function AuthForm({ onSignedIn }: { onSignedIn: () => void }) {
  const [mode, setMode] = useState<Mode>('signIn')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (mode === 'signUp') {
        await signUp(email, password)
        setMode('confirm')
        setMessage(`We emailed a verification code to ${email}.`)
      } else if (mode === 'confirm') {
        await confirmSignUp(email, code)
        setMode('signIn')
        setMessage('Email confirmed. Sign in to continue.')
      } else {
        await signIn(email, password)
        onSignedIn()
      }
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const title = { signIn: 'Sign in', signUp: 'Create an account', confirm: 'Confirm your email' }[mode]

  return (
    <form className="card auth" onSubmit={submit} aria-label={title}>
      <h1>{title}</h1>
      <p className="muted">Results are shown here, and you can email them to your account address.</p>

      <label>
        Email
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled={mode === 'confirm'} required />
      </label>
      {mode === 'confirm' ? (
        <label>
          Verification code
          <input inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} required />
        </label>
      ) : (
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={10} required />
        </label>
      )}
      {mode === 'signUp' && <p className="hint">At least 10 characters, with upper case, lower case and a number.</p>}

      {message && <p className="alert alert-success">{message}</p>}
      {error && <p className="alert alert-error" role="alert">{error}</p>}

      <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Please wait…' : title}</button>

      <p className="switch">
        {mode === 'signIn' ? (
          <button type="button" className="link" onClick={() => setMode('signUp')}>Create an account</button>
        ) : (
          <button type="button" className="link" onClick={() => setMode('signIn')}>Back to sign in</button>
        )}
      </p>
    </form>
  )
}
