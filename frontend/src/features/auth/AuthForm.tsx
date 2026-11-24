import { type FormEvent, useState } from 'react'
import { useAuth } from '../../auth/context'
import { AuthError, confirmSignUp, resendCode, signUp } from '../../auth/cognito'
import { Alert } from '../../components/ui/Alert'
import { Button } from '../../components/ui/Button'
import { EMAIL_PATTERN } from '../../limits'
import { PasswordInput } from './PasswordInput'

type Mode = 'signIn' | 'signUp' | 'confirm'

const COPY: Record<Mode, { title: string; subtitle: string; action: string }> = {
  signIn: { title: 'Sign in', subtitle: 'Welcome back. Sign in to tailor your resume.', action: 'Sign in' },
  signUp: {
    title: 'Create your account',
    subtitle: 'Results are emailed to this address, so use one you can open.',
    action: 'Create account',
  },
  confirm: { title: 'Confirm your email', subtitle: 'Enter the 6-digit code we emailed you.', action: 'Confirm email' },
}

const MIN_PASSWORD = 10

export function AuthForm() {
  const { signIn } = useAuth()
  const [mode, setMode] = useState<Mode>('signIn')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  const address = email.trim()
  const emailOk = EMAIL_PATTERN.test(address)
  const canSubmit =
    emailOk && (mode === 'confirm' ? /^\d{6}$/.test(code.trim()) : password.length >= MIN_PASSWORD) && !busy

  const switchMode = (next: Mode) => {
    setMode(next)
    setError(null)
    setInfo(null)
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
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
        setInfo('Email confirmed. Sign in to continue.')
        setMode('signIn')
      } else {
        await signIn(address, password)
      }
    } catch (err) {
      if (err instanceof AuthError && err.code === 'UserNotConfirmedException') {
        await resendCode(address).catch(() => undefined)
        setInfo('Please confirm your email first. We sent you a new code.')
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
      await resendCode(address)
      setInfo('A new code is on its way.')
    } catch (err) {
      setError(err instanceof AuthError ? err.message : 'Could not send a new code.')
    }
  }

  const { title, subtitle, action } = COPY[mode]
  return (
    <form className="card auth-card" onSubmit={onSubmit} noValidate aria-labelledby="auth-title">
      <h1 id="auth-title" className="card-title">
        {title}
      </h1>
      <p className="muted">{subtitle}</p>

      <div className="field">
        <label htmlFor="auth-email">Email</label>
        <input
          id="auth-email"
          className="input"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={busy || mode === 'confirm'}
        />
      </div>

      {mode === 'confirm' ? (
        <div className="field">
          <label htmlFor="auth-code">Verification code</label>
          <input
            id="auth-code"
            className="input input-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            disabled={busy}
          />
        </div>
      ) : (
        <div className="field">
          <label htmlFor="auth-password">Password</label>
          <PasswordInput
            id="auth-password"
            value={password}
            onChange={setPassword}
            autoComplete={mode === 'signUp' ? 'new-password' : 'current-password'}
            disabled={busy}
            describedBy={mode === 'signUp' ? 'password-hint' : undefined}
          />
          {mode === 'signUp' && (
            <p id="password-hint" className="hint">
              At least {MIN_PASSWORD} characters, with upper case, lower case and a number.
            </p>
          )}
        </div>
      )}

      {info && <Alert tone="success">{info}</Alert>}
      {error && <Alert tone="error">{error}</Alert>}

      <Button type="submit" variant="primary" className="btn-block" loading={busy} disabled={!canSubmit}>
        {action}
      </Button>

      <div className="auth-switch">
        {mode === 'signIn' && (
          <>
            New here?{' '}
            <button type="button" className="link" onClick={() => switchMode('signUp')}>
              Create an account
            </button>
          </>
        )}
        {mode === 'signUp' && (
          <>
            Already have an account?{' '}
            <button type="button" className="link" onClick={() => switchMode('signIn')}>
              Sign in
            </button>
          </>
        )}
        {mode === 'confirm' && (
          <>
            <button type="button" className="link" onClick={() => void onResend()} disabled={!emailOk}>
              Send a new code
            </button>
            <span aria-hidden="true"> · </span>
            <button type="button" className="link" onClick={() => switchMode('signIn')}>
              Back to sign in
            </button>
          </>
        )}
      </div>
    </form>
  )
}
