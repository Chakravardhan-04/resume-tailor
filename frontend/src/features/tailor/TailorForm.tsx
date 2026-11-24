import { type FormEvent, useState } from 'react'
import { ApiError, submitJob } from '../../api'
import { Alert } from '../../components/ui/Alert'
import { Button } from '../../components/ui/Button'
import { MAX_DOC_CHARS, MIN_DOC_CHARS } from '../../limits'
import { DocInput } from './DocInput'
import { SAMPLE_JOB, SAMPLE_RESUME } from './sample'

const isValid = (text: string) => {
  const n = text.trim().length
  return n >= MIN_DOC_CHARS && text.length <= MAX_DOC_CHARS
}

export function TailorForm({ email, onSubmitted }: { email: string; onSubmitted: (jobId: string) => void }) {
  const [resume, setResume] = useState('')
  const [jobDescription, setJobDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const valid = isValid(resume) && isValid(jobDescription)

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!valid || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      onSubmitted(await submitJob(resume, jobDescription))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
      setSubmitting(false)
    }
  }

  const loadSample = () => {
    setResume(SAMPLE_RESUME)
    setJobDescription(SAMPLE_JOB)
  }

  return (
    <form onSubmit={onSubmit} noValidate className="stack">
      <div className="page-head">
        <div>
          <h1 className="page-title">Tailor your resume</h1>
          <p className="muted">
            Add your resume and the job you want. Results appear here and are emailed to <strong>{email}</strong>.
          </p>
        </div>
        <Button variant="ghost" onClick={loadSample} disabled={submitting}>
          Try a sample
        </Button>
      </div>

      <div className="doc-grid">
        <DocInput
          label="Resume"
          hint="Your current resume as plain text."
          value={resume}
          onChange={setResume}
          disabled={submitting}
          placeholder="Paste your resume…"
        />
        <DocInput
          label="Job description"
          hint="The full posting, including requirements."
          value={jobDescription}
          onChange={setJobDescription}
          disabled={submitting}
          placeholder="Paste the job posting…"
        />
      </div>

      {error && <Alert tone="error">{error}</Alert>}

      <div className="submit-bar">
        <p className="hint">Takes about a minute. You can submit up to 5 jobs a day.</p>
        <Button type="submit" variant="primary" loading={submitting} disabled={!valid}>
          Tailor my resume
        </Button>
      </div>
    </form>
  )
}
