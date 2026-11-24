import { type FormEvent, useState } from 'react'
import { ApiError, submitJob } from './api'
import { DocInput } from './components/DocInput'
import { JobView } from './components/JobView'
import { MAX_DOC_CHARS, MIN_DOC_CHARS } from './limits'

export default function Tailor() {
  const [resume, setResume] = useState('')
  const [jobDescription, setJobDescription] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const valid = [resume, jobDescription].every((t) => {
    const n = t.trim().length
    return n >= MIN_DOC_CHARS && n <= MAX_DOC_CHARS
  })

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!valid || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      setJobId(await submitJob(resume, jobDescription))
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
    <>
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
    </>
  )
}
