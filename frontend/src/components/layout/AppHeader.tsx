import { useAuth } from '../../auth/context'
import { Logo } from '../ui/Logo'

export function AppHeader() {
  const { status, email, signOut } = useAuth()
  return (
    <header className="app-header">
      <div className="container header-inner">
        <Logo />
        {status === 'signedIn' && (
          <div className="account">
            <span className="avatar" aria-hidden="true">
              {email.charAt(0).toUpperCase()}
            </span>
            <span className="account-email">{email}</span>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void signOut()}>
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
