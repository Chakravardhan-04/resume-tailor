import { type FormEvent, useState } from 'react'
import { submitJob } from './api'

const MIN = 50
const MAX = 15000 // same length cap as the backend guardrail

const SAMPLE_RESUME = `Alex Morgan
Software Engineer | Hyderabad, India

SUMMARY
Backend-focused software engineer with 3 years of experience building Python services and REST APIs on AWS.

EXPERIENCE
Software Engineer, Acme Retail Tech (2022 - present)
- Built REST APIs in Python and Flask for the order management system, serving 40,000 requests per day.
- Designed DynamoDB tables and access patterns for the product catalogue service.
- Deployed serverless services with AWS Lambda and API Gateway using AWS SAM.
- Reduced average API latency by 30% by adding caching and query optimisation.
- Wrote unit tests with pytest and set up GitHub Actions CI for 4 repositories.

Junior Developer, BrightApps (2021 - 2022)
- Developed internal dashboards in React and JavaScript.
- Maintained PostgreSQL schemas and wrote SQL reports for the finance team.

SKILLS
Python, Flask, AWS Lambda, API Gateway, DynamoDB, S3, PostgreSQL, SQL, React, JavaScript, Git, pytest, GitHub Actions

EDUCATION
B.Tech in Computer Science, 2021`

const SAMPLE_JOB = `Backend Engineer (Python, AWS) - CloudScale Labs

About the role
We are looking for a Backend Engineer to build and run cloud-native services.

Requirements
- 3+ years of professional experience in backend development
- Strong Python skills
- Hands-on experience with AWS serverless services (Lambda, API Gateway, DynamoDB)
- Experience designing REST APIs
- Infrastructure as code with Terraform or AWS CDK
- Experience with automated testing and CI/CD pipelines

Nice to have
- Kubernetes and Docker
- Experience with event-driven architectures (SQS, EventBridge)
- AWS Certified Developer or Solutions Architect certification`

const valid = (text: string) => text.trim().length >= MIN && text.length <= MAX

/** Why a document is not ready yet, or '' when it is. */
function problem(label: string, text: string): string {
  if (!text.trim()) return `Add the ${label.toLowerCase()}.`
  if (text.trim().length < MIN) return `The ${label.toLowerCase()} is too short (at least ${MIN} characters).`
  if (text.length > MAX) return `The ${label.toLowerCase()} is too long (${text.length.toLocaleString()} of ${MAX.toLocaleString()} characters).`
  return ''
}

/** One document box: paste text or upload a .txt/.md file. */
function DocBox({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const [fileError, setFileError] = useState('')

  async function upload(file: File | undefined) {
    if (!file) return
    // Only plain text can be read here. A PDF or Word file would come in as unreadable binary data.
    if (!/\.(txt|md)$/i.test(file.name)) {
      setFileError(`${file.name} is not a .txt file. Open it, copy the text and paste it here instead.`)
      return
    }
    setFileError('')
    onChange(await file.text())
  }

  return (
    <div className="card doc">
      <div className="doc-head">
        <label htmlFor={label}>{label}</label>
        <input type="file" accept=".txt,.md" aria-label={`Upload ${label}`} onChange={(e) => upload(e.target.files?.[0])} />
      </div>
      <textarea id={label} value={value} onChange={(e) => onChange(e.target.value)} placeholder={`Paste the ${label.toLowerCase()}…`} />
      <span className={valid(value) || !value ? 'count' : 'count bad'}>
        {value.length.toLocaleString()} / {MAX.toLocaleString()} characters
      </span>
      {fileError && <p className="alert alert-error" role="alert">{fileError}</p>}
    </div>
  )
}

export default function TailorForm({ email, onSubmitted }: { email: string; onSubmitted: (jobId: string) => void }) {
  const [resume, setResume] = useState('')
  const [job, setJob] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { jobId } = await submitJob(resume, job) // starts the Step Functions pipeline
      onSubmitted(jobId)
    } catch (err) {
      setError((err as Error).message) // e.g. "The resume is too long (maximum 15000 characters)."
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="stack">
      <div className="page-head">
        <div>
          <h1>Tailor your resume</h1>
          <p className="muted">Results appear here and are emailed to <strong>{email}</strong>.</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={() => { setResume(SAMPLE_RESUME); setJob(SAMPLE_JOB) }}>
          Try a sample
        </button>
      </div>

      <div className="grid">
        <DocBox label="Resume" value={resume} onChange={setResume} />
        <DocBox label="Job description" value={job} onChange={setJob} />
      </div>

      {error && <p className="alert alert-error" role="alert">{error}</p>}
      <div className="actions">
        {/* Say why the button is disabled instead of leaving the user guessing. */}
        <span className="hint">{problem('Resume', resume) || problem('Job description', job)}</span>
        <button type="submit" className="btn btn-primary" disabled={busy || !valid(resume) || !valid(job)}>
          {busy ? 'Submitting…' : 'Tailor my resume'}
        </button>
      </div>
    </form>
  )
}
