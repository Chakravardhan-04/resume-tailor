import { type FormEvent, useState } from 'react'
import { AuthError, confirmSignUp, resendCode, signUp } from '../auth/cognito'
import { useAuth } from '../auth/context'
import { EMAIL_PATTERN } from '../limits'

type Mode = 'signIn' | 'signUp' | 'confirm'

const TITLES: Record<Mode, string> = {
  signIn: 'Sign in',
  signUp: 'Create your account',
  confirm: 'Confirm your email',
}

export function AuthForm() {
  const { signIn } = useAuth()
  const [mode, setMode] = useState<Mode>('signIn')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  const emailOk = EMAIL_PATTERN.test(email.trim())
  const canSubmit = emailOk && (mode === 'confirm' ? code.trim().length >= 6 : password.length >= 10) && !busy

  const switchMode = (next: Mode) => {
    setMode(next)
    setError(null)
    setInfo(null)
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    const address = email.trim()
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      if (mode === 'signUp') {
        await signUp(address, password)
        setPassword('')
        setInfo(`We sent a verification code to ${address}.`)
        setMode('confirm')
      } else if (mode === 'confirm') {
        await confirmSignUp(address, code)
        setCode('')
        setInfo('Email confirmed. You can sign in now.')
        setMode('signIn')
      } else {
        await signIn(address, password)
      }
    } catch (err) {
      if (err instanceof AuthError && err.code === 'UserNotConfirmedException') {
        await resendCode(address).catch(() => undefined)
        setInfo('Please confirm your email. We sent a new code.')
        setMode('confirm')
      } else {
        setError(err instanceof AuthError ? err.message : 'Something went wrong. Please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  const onResend = async () => {
    setError(null)
    try {
      await resendCode(email.trim())
      setInfo('A new code is on its way.')
    } catch (err) {
      setError(err instanceof AuthError ? err.message : 'Could not send a new code.')
    }
  }

  return (
    <form className="panel auth" onSubmit={onSubmit} noValidate aria-label={TITLES[mode]}>
      <h2>{TITLES[mode]}</h2>
      <div className="field">
        <label htmlFor="auth-email">Email</label>
        <input
          id="auth-email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={busy}
        />
      </div>
      {mode === 'confirm' ? (
        <div className="field">
          <label htmlFor="auth-code">Verification code</label>
          <input
            id="auth-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            disabled={busy}
          />
        </div>
      ) : (
        <div className="field">
          <label htmlFor="auth-password">Password</label>
          <input
            id="auth-password"
            type="password"
            autoComplete={mode === 'signUp' ? 'new-password' : 'current-password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
          />
          {mode === 'signUp' && (
            <div className="count">At least 10 characters, with upper case, lower case and a number.</div>
          )}
        </div>
      )}
      {info && (
        <p className="notice" role="status">
          {info}
        </p>
      )}
      {error && (
        <div role="alert" className="error">
          {error}
        </div>
      )}
      <button type="submit" className="btn primary" disabled={!canSubmit}>
        {busy ? 'Please wait…' : TITLES[mode]}
      </button>
      <p className="muted small links">
        {mode === 'signIn' && (
          <button type="button" className="link" onClick={() => switchMode('signUp')}>
            Create an account
          </button>
        )}
        {mode === 'signUp' && (
          <button type="button" className="link" onClick={() => switchMode('signIn')}>
            I already have an account
          </button>
        )}
        {mode === 'confirm' && (
          <>
            <button type="button" className="link" onClick={onResend} disabled={!emailOk}>
              Send a new code
            </button>{' '}
            <button type="button" className="link" onClick={() => switchMode('signIn')}>
              Back to sign in
            </button>
          </>
        )}
      </p>
    </form>
  )
}
