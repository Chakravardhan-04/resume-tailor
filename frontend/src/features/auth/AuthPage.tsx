import { AuthForm } from './AuthForm'

const POINTS = [
  { title: 'Tailored to the role', text: 'A rewritten summary and bullets that match the job description.' },
  { title: 'Never invents experience', text: 'Every bullet is checked against your original resume.' },
  { title: 'An honest gap list', text: 'Requirements you do not meet yet, ranked by importance.' },
  { title: 'PDF and email', text: 'Download the draft, and get a copy in your inbox.' },
]

export function AuthPage() {
  return (
    <div className="auth-layout">
      <section className="auth-intro" aria-label="About Resume Tailor">
        <h2 className="hero-title">Tailor your resume to any job, honestly.</h2>
        <p className="hero-lead">
          Three AI specialists read the job, score your resume against it, and rewrite it using only what you have
          actually done.
        </p>
        <ul className="feature-list">
          {POINTS.map((p) => (
            <li key={p.title}>
              <span className="feature-check" aria-hidden="true">
                ✓
              </span>
              <div>
                <strong>{p.title}</strong>
                <span className="muted">{p.text}</span>
              </div>
            </li>
          ))}
        </ul>
      </section>
      <AuthForm />
    </div>
  )
}
