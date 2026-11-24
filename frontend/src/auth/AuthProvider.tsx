import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { setAuthHandlers } from '../api'
import * as cognito from './cognito'
import { AuthContext, type AuthState, type AuthStatus } from './context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [email, setEmail] = useState('')

  const applyToken = useCallback((token: string | null) => {
    setEmail(token ? cognito.emailFromToken(token) : '')
    setStatus(token ? 'signedIn' : 'signedOut')
  }, [])

  const signOut = useCallback(async () => {
    await cognito.signOut()
    applyToken(null)
  }, [applyToken])

  useEffect(() => {
    setAuthHandlers({ getToken: cognito.getIdToken, onUnauthorized: () => void signOut() })
    void cognito.getIdToken().then(applyToken)
  }, [applyToken, signOut])

  const value = useMemo<AuthState>(
    () => ({
      status,
      email,
      signIn: async (e, p) => {
        await cognito.signIn(e, p)
        applyToken(await cognito.getIdToken())
      },
      signOut,
    }),
    [status, email, applyToken, signOut],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
