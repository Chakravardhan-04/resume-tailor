import { type FormEvent, useState } from 'react'
import { ApiError, submitJob } from './api'
import { DemoBanner } from './components/DemoBanner'
import { DocInput } from './components/DocInput'
import { JobView } from './components/JobView'
import { EMAIL_PATTERN, MAX_DOC_CHARS, MIN_DOC_CHARS } from './limits'

export default function App() {
  const [resume, setResume] = useState('')
  const [jobDescription, setJobDescription] = useState('')
  const [email, setEmail] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const docsValid = [resume, jobDescription].every((t) => {
    const n = t.trim().length
    return n >= MIN_DOC_CHARS && n <= MAX_DOC_CHARS
  })
  const valid = docsValid && EMAIL_PATTERN.test(email.trim())

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!valid || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      setJobId(await submitJob(resume, jobDescription, email.trim()))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const reset = () => {
    setJobId(null)
    setError(null)
  }

  return (
    <main className="container">
      <header>
        <h1>Resume Tailor</h1>
        <p className="muted">
          Paste your resume and a job description. You get a tailored summary and bullets, plus an honest list of what
          your resume is missing.
        </p>
      </header>
      <DemoBanner />

      {jobId ? (
        <JobView key={jobId} jobId={jobId} onReset={reset} />
      ) : (
        <form onSubmit={onSubmit} noValidate>
          <DocInput label="Resume" value={resume} onChange={setResume} disabled={submitting} placeholder="Paste your resume text…" />
          <DocInput
            label="Job description"
            value={jobDescription}
            onChange={setJobDescription}
            disabled={submitting}
            placeholder="Paste the job posting…"
          />
          <div className="field">
            <label htmlFor="email">Email (we send the draft and PDF here)</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={submitting}
              placeholder="you@example.com"
            />
          </div>
          {error && (
            <div role="alert" className="error">
              {error}
            </div>
          )}
          <button type="submit" className="btn primary" disabled={!valid || submitting}>
            {submitting ? 'Submitting…' : 'Tailor my resume'}
          </button>
        </form>
      )}
    </main>
  )
}
