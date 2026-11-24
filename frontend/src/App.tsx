import { useState } from 'react'
import { currentEmail, getToken, signOut } from './auth'
import AuthForm from './AuthForm'
import JobView from './JobView'
import TailorForm from './TailorForm'

/** Screens: sign in -> form -> job progress/result. */
export default function App() {
  const [signedIn, setSignedIn] = useState(() => getToken() !== null)
  const [jobId, setJobId] = useState<string | null>(null)

  return (
    <div className="app">
      <header className="header">
        <span className="logo">Resume Tailor</span>
        {signedIn && (
          <span className="account">
            <span className="muted">{currentEmail()}</span>
            <button className="btn btn-ghost" onClick={() => { signOut(); setSignedIn(false); setJobId(null) }}>
              Sign out
            </button>
          </span>
        )}
      </header>

      <main className="main">
        {!signedIn ? (
          <AuthForm onSignedIn={() => setSignedIn(true)} />
        ) : jobId ? (
          <JobView jobId={jobId} onReset={() => setJobId(null)} />
        ) : (
          <TailorForm email={currentEmail()} onSubmitted={setJobId} />
        )}
      </main>

      <footer className="footer" role="note">
        <span><strong>Demo.</strong> Resumes are personal data. Files are deleted after one day.</span>
      </footer>
    </div>
  )
}
