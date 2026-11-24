import type { AppConfig } from '../config'

/**
 * Minimal Amazon Cognito client using the public user-pool API (no secret, no SDK).
 * Tokens live in sessionStorage: they are cleared when the tab closes.
 */

export class AuthError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'AuthError'
    this.code = code
  }
}

interface Session {
  idToken: string
  refreshToken: string
  expiresAt: number // epoch ms
}

const STORAGE_KEY = 'resume-tailor.session'
const REFRESH_MARGIN_MS = 60_000

const MESSAGES: Record<string, string> = {
  NotAuthorizedException: 'Incorrect email or password.',
  UserNotFoundException: 'Incorrect email or password.',
  UsernameExistsException: 'An account with this email already exists. Try signing in.',
  InvalidPasswordException: 'Password must be at least 10 characters with upper case, lower case and a number.',
  InvalidParameterException: 'Please check the values you entered.',
  CodeMismatchException: 'That code is not correct.',
  ExpiredCodeException: 'That code has expired. Request a new one.',
  LimitExceededException: 'Too many attempts. Please wait a few minutes and try again.',
  TooManyRequestsException: 'Too many attempts. Please wait a few minutes and try again.',
  UserNotConfirmedException: 'Please confirm your email address first.',
}

let config: AppConfig | null = null
let refreshing: Promise<string | null> | null = null

export function configureAuth(cfg: AppConfig): void {
  config = cfg
}

function cfg(): AppConfig {
  if (!config) throw new Error('Auth is not configured')
  return config
}

async function call<T>(target: string, body: Record<string, unknown>): Promise<T> {
  let res: Response
  try {
    res = await fetch(`https://cognito-idp.${cfg().region}.amazonaws.com/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': `AWSCognitoIdentityProviderService.${target}`,
      },
      body: JSON.stringify({ ClientId: cfg().clientId, ...body }),
    })
  } catch {
    throw new AuthError('NetworkError', 'Network error. Check your connection and try again.')
  }
  const data = (await res.json().catch(() => ({}))) as { __type?: string; message?: string }
  if (!res.ok) {
    const code = (data.__type ?? 'Unknown').split('#').pop() ?? 'Unknown'
    throw new AuthError(code, MESSAGES[code] ?? data.message ?? 'Something went wrong. Please try again.')
  }
  return data as T
}

interface AuthResult {
  AuthenticationResult?: { IdToken: string; RefreshToken?: string; ExpiresIn: number }
}

function store(result: AuthResult, fallbackRefresh?: string): Session {
  const auth = result.AuthenticationResult
  const refreshToken = auth?.RefreshToken ?? fallbackRefresh
  if (!auth || !refreshToken) throw new AuthError('Unknown', 'Sign-in failed. Please try again.')
  const session = { idToken: auth.IdToken, refreshToken, expiresAt: Date.now() + auth.ExpiresIn * 1000 }
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  return session
}

function load(): Session | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch {
    return null
  }
}

export async function signUp(email: string, password: string): Promise<void> {
  await call('SignUp', {
    Username: email,
    Password: password,
    UserAttributes: [{ Name: 'email', Value: email }],
  })
}

export async function confirmSignUp(email: string, code: string): Promise<void> {
  await call('ConfirmSignUp', { Username: email, ConfirmationCode: code.trim() })
}

export async function resendCode(email: string): Promise<void> {
  await call('ResendConfirmationCode', { Username: email })
}

export async function signIn(email: string, password: string): Promise<void> {
  const result = await call<AuthResult>('InitiateAuth', {
    AuthFlow: 'USER_PASSWORD_AUTH',
    AuthParameters: { USERNAME: email, PASSWORD: password },
  })
  store(result)
}

/** A valid ID token (refreshing it when close to expiry), or null when signed out. */
export async function getIdToken(): Promise<string | null> {
  const session = load()
  if (!session) return null
  if (session.expiresAt - Date.now() > REFRESH_MARGIN_MS) return session.idToken
  refreshing ??= call<AuthResult>('InitiateAuth', {
    AuthFlow: 'REFRESH_TOKEN_AUTH',
    AuthParameters: { REFRESH_TOKEN: session.refreshToken },
  })
    .then((result) => store(result, session.refreshToken).idToken)
    .catch(() => {
      sessionStorage.removeItem(STORAGE_KEY)
      return null
    })
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

export async function signOut(): Promise<void> {
  const session = load()
  sessionStorage.removeItem(STORAGE_KEY)
  if (session) {
    // Best effort: revoke the refresh token server-side.
    await call('RevokeToken', { Token: session.refreshToken }).catch(() => undefined)
  }
}

/** Display only. The server never trusts this; it validates the token itself. */
export function emailFromToken(idToken: string): string {
  try {
    const payload = idToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return (JSON.parse(atob(payload)) as { email?: string }).email ?? ''
  } catch {
    return ''
  }
}
