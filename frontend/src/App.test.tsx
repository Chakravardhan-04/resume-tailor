import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import * as cognito from './auth/cognito'

beforeEach(() => {
  sessionStorage.clear()
  cognito.configureAuth({ region: 'us-east-1', userPoolId: 'p', clientId: 'c' })
})
afterEach(() => vi.restoreAllMocks())

const reply = (status: number, body: unknown) => new Response(JSON.stringify(body), { status })
const jwt = (payload: object) => `h.${btoa(JSON.stringify(payload))}.s`

describe('App auth gate', () => {
  it('shows the demo warning and the sign-in form when signed out, and no resume form', async () => {
    render(<App />)
    expect(await screen.findByRole('form', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent(/demo/i)
    expect(screen.queryByLabelText('Resume')).not.toBeInTheDocument()
  })

  it('shows the app and the account email when a session exists', async () => {
    sessionStorage.setItem(
      'resume-tailor.session',
      JSON.stringify({
        idToken: jwt({ email: 'me@example.com' }),
        refreshToken: 'r',
        expiresAt: Date.now() + 3600_000,
      }),
    )
    render(<App />)
    expect(await screen.findByLabelText('Resume')).toBeInTheDocument()
    expect(screen.getByRole('banner')).toHaveTextContent('me@example.com')
  })

  it('signs in with email and password', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      reply(200, {
        AuthenticationResult: { IdToken: jwt({ email: 'me@example.com' }), RefreshToken: 'r', ExpiresIn: 3600 },
      }),
    )
    render(<App />)
    await user.type(await screen.findByLabelText('Email'), 'me@example.com')
    await user.type(screen.getByLabelText('Password'), 'Passw0rdPassw0rd')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))
    expect(await screen.findByLabelText('Resume')).toBeInTheDocument()
  })

  it('shows a clear error for wrong credentials', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply(400, { __type: 'NotAuthorizedException' }))
    render(<App />)
    await user.type(await screen.findByLabelText('Email'), 'me@example.com')
    await user.type(screen.getByLabelText('Password'), 'wrongpassword1')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.')
  })

  it('walks through sign-up, code confirmation, then back to sign-in', async () => {
    const user = userEvent.setup()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply(200, {}))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Create an account' }))
    await user.type(screen.getByLabelText('Email'), 'new@example.com')
    await user.type(screen.getByLabelText('Password'), 'Passw0rdPassw0rd')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByLabelText('Verification code')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Verification code'), '123456')
    await user.click(screen.getByRole('button', { name: 'Confirm email' }))

    await waitFor(() => expect(screen.getByRole('form', { name: 'Sign in' })).toBeInTheDocument())
    expect(screen.getByText(/email confirmed/i)).toBeInTheDocument()
    const targets = fetchSpy.mock.calls.map((c) => ((c[1] as RequestInit).headers as Record<string, string>)['X-Amz-Target'])
    expect(targets).toEqual([
      'AWSCognitoIdentityProviderService.SignUp',
      'AWSCognitoIdentityProviderService.ConfirmSignUp',
    ])
  })

  it('sends an unconfirmed user to the code screen with a fresh code', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(reply(400, { __type: 'UserNotConfirmedException' }))
      .mockResolvedValue(reply(200, {}))
    render(<App />)
    await user.type(await screen.findByLabelText('Email'), 'me@example.com')
    await user.type(screen.getByLabelText('Password'), 'Passw0rdPassw0rd')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))
    expect(await screen.findByLabelText('Verification code')).toBeInTheDocument()
  })

  it('signs out', async () => {
    const user = userEvent.setup()
    sessionStorage.setItem(
      'resume-tailor.session',
      JSON.stringify({ idToken: jwt({ email: 'me@example.com' }), refreshToken: 'r', expiresAt: Date.now() + 3600_000 }),
    )
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply(200, {}))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('form', { name: 'Sign in' })).toBeInTheDocument()
    expect(sessionStorage.getItem('resume-tailor.session')).toBeNull()
  })
})
