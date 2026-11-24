/**
 * Sign-up and sign-in with Amazon Cognito, called directly from the browser (no SDK, no secret).
 * The ID token is kept in sessionStorage and sent to the API as "Authorization: Bearer <token>".
 */

let region = ''
let clientId = ''
const TOKEN_KEY = 'resume-tailor.idToken'

/** Read the public Cognito ids that CDK wrote to /config.json at deploy time. */
export async function loadConfig(): Promise<void> {
  const config = await (await fetch('/config.json')).json()
  region = config.region
  clientId = config.clientId
}

/** Call one Cognito user-pool API action, e.g. SignUp, ConfirmSignUp, InitiateAuth. */
async function cognito(action: string, body: object) {
  const res = await fetch(`https://cognito-idp.${region}.amazonaws.com/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-amz-json-1.1',
      'X-Amz-Target': `AWSCognitoIdentityProviderService.${action}`,
    },
    body: JSON.stringify({ ClientId: clientId, ...body }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.message ?? 'Something went wrong. Please try again.')
  return data
}

export const signUp = (email: string, password: string) =>
  cognito('SignUp', { Username: email, Password: password, UserAttributes: [{ Name: 'email', Value: email }] })

export const confirmSignUp = (email: string, code: string) =>
  cognito('ConfirmSignUp', { Username: email, ConfirmationCode: code.trim() })

export async function signIn(email: string, password: string): Promise<void> {
  const data = await cognito('InitiateAuth', {
    AuthFlow: 'USER_PASSWORD_AUTH',
    AuthParameters: { USERNAME: email, PASSWORD: password },
  })
  sessionStorage.setItem(TOKEN_KEY, data.AuthenticationResult.IdToken)
}

export const signOut = () => sessionStorage.removeItem(TOKEN_KEY)

/** The ID token, or null if missing or expired (tokens last one hour). */
export function getToken(): string | null {
  const token = sessionStorage.getItem(TOKEN_KEY)
  if (!token) return null
  const { exp } = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
  return exp * 1000 > Date.now() ? token : null
}

/** The signed-in user's email, read from the token (for display only; the server checks the token itself). */
export function currentEmail(): string {
  const token = getToken()
  return token ? JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).email : ''
}
