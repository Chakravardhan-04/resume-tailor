import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthError, configureAuth, confirmSignUp, emailFromToken, getIdToken, signIn, signOut, signUp } from './cognito'

const reply = (status: number, body: unknown) => new Response(JSON.stringify(body), { status })

const jwt = (payload: object) => `h.${btoa(JSON.stringify(payload)).replace(/\+/g, '-').replace(/\//g, '_')}.s`

beforeEach(() => {
  sessionStorage.clear()
  configureAuth({ region: 'us-east-1', userPoolId: 'us-east-1_abc', clientId: 'client1' })
})
afterEach(() => vi.restoreAllMocks())

const lastCall = (spy: ReturnType<typeof vi.spyOn>) => {
  const [url, init] = spy.mock.calls.at(-1) as [string, RequestInit]
  return {
    url,
    target: (init.headers as Record<string, string>)['X-Amz-Target'],
    body: JSON.parse(String(init.body)),
  }
}

describe('cognito client', () => {
  it('signs up with the email as username and attribute', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply(200, {}))
    await signUp('me@example.com', 'Passw0rdPassw0rd')
    const call = lastCall(spy)
    expect(call.url).toBe('https://cognito-idp.us-east-1.amazonaws.com/')
    expect(call.target).toBe('AWSCognitoIdentityProviderService.SignUp')
    expect(call.body).toMatchObject({
      ClientId: 'client1',
      Username: 'me@example.com',
      UserAttributes: [{ Name: 'email', Value: 'me@example.com' }],
    })
  })

  it('confirms with a trimmed code', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply(200, {}))
    await confirmSignUp('me@example.com', ' 123456 ')
    expect(lastCall(spy).body.ConfirmationCode).toBe('123456')
  })

  it('stores the session on sign-in and returns the token without refreshing', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(reply(200, { AuthenticationResult: { IdToken: 'id1', RefreshToken: 'r1', ExpiresIn: 3600 } }))
    await signIn('me@example.com', 'pw')
    expect(lastCall(spy).body.AuthFlow).toBe('USER_PASSWORD_AUTH')
    expect(await getIdToken()).toBe('id1')
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('refreshes an expiring token once, even for concurrent callers', async () => {
    sessionStorage.setItem(
      'resume-tailor.session',
      JSON.stringify({ idToken: 'old', refreshToken: 'r1', expiresAt: Date.now() + 1000 }),
    )
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(reply(200, { AuthenticationResult: { IdToken: 'new', ExpiresIn: 3600 } }))
    const [a, b] = await Promise.all([getIdToken(), getIdToken()])
    expect([a, b]).toEqual(['new', 'new'])
    expect(spy).toHaveBeenCalledTimes(1)
    expect(lastCall(spy).body.AuthFlow).toBe('REFRESH_TOKEN_AUTH')
    expect(JSON.parse(sessionStorage.getItem('resume-tailor.session')!).refreshToken).toBe('r1') // kept
  })

  it('clears the session when refresh fails', async () => {
    sessionStorage.setItem(
      'resume-tailor.session',
      JSON.stringify({ idToken: 'old', refreshToken: 'r1', expiresAt: Date.now() - 1 }),
    )
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply(400, { __type: 'NotAuthorizedException' }))
    expect(await getIdToken()).toBeNull()
    expect(sessionStorage.getItem('resume-tailor.session')).toBeNull()
  })

  it('maps Cognito errors to friendly messages with a code', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      reply(400, { __type: 'com.amazonaws#UserNotConfirmedException', message: 'raw' }),
    )
    const err = await signIn('me@example.com', 'pw').catch((e) => e)
    expect(err).toBeInstanceOf(AuthError)
    expect(err.code).toBe('UserNotConfirmedException')
    expect(err.message).toBe('Please confirm your email address first.')
  })

  it('signs out locally even if revocation fails', async () => {
    sessionStorage.setItem(
      'resume-tailor.session',
      JSON.stringify({ idToken: 'x', refreshToken: 'r1', expiresAt: Date.now() + 3600_000 }),
    )
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('offline'))
    await signOut()
    expect(sessionStorage.getItem('resume-tailor.session')).toBeNull()
  })

  it('reads the email from an ID token for display', () => {
    expect(emailFromToken(jwt({ email: 'me@example.com' }))).toBe('me@example.com')
    expect(emailFromToken('garbage')).toBe('')
  })
})
