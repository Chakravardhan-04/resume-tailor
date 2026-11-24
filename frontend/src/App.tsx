import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/context'
import { AuthForm } from './components/AuthForm'
import { DemoBanner } from './components/DemoBanner'
import Tailor from './Tailor'

function Shell() {
  const { status, email, signOut } = useAuth()
  return (
    <main className="container">
      <header className="top">
        <div>
          <h1>Resume Tailor</h1>
          <p className="muted">
            Paste your resume and a job description. You get a tailored summary and bullets, an honest list of what
            your resume is missing, a PDF, and an email with the same.
          </p>
        </div>
        {status === 'signedIn' && (
          <div className="account">
            <span className="muted small">{email}</span>
            <button type="button" className="btn" onClick={() => void signOut()}>
              Sign out
            </button>
          </div>
        )}
      </header>
      <DemoBanner />
      {status === 'loading' && <p className="muted">Loading…</p>}
      {status === 'signedOut' && <AuthForm />}
      {status === 'signedIn' && <Tailor />}
    </main>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  )
}
