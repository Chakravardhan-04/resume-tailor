import { useEffect, useState } from 'react'
import { emailJob, type Gap, getJob, type Job, type Result } from './api'

const STAGES = [
  { key: 'analyzer', label: 'Reading the job requirements' },
  { key: 'scorer', label: 'Scoring your resume against them' },
  { key: 'rewriter', label: 'Rewriting honestly from your resume' },
]

/** Poll GET /api/jobs/{id} every 3 seconds until the pipeline finishes. */
function usePollJob(jobId: string): { job: Job | null; error: string } {
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let stopped = false
    async function poll() {
      try {
        const latest = await getJob(jobId)
        if (stopped) return
        setJob(latest)
        if (latest.status === 'RUNNING') setTimeout(poll, 3000) // keep polling until DONE or FAILED
      } catch (err) {
        if (!stopped) setError((err as Error).message)
      }
    }
    poll()
    return () => { stopped = true } // stop polling when the user leaves the page
  }, [jobId])

  return { job, error }
}

export default function JobView({ jobId, onReset }: { jobId: string; onReset: () => void }) {
  const { job, error } = usePollJob(jobId)

  if (error || job?.status === 'FAILED') {
    return (
      <div className="card stack">
        <h1>We could not finish this one</h1>
        <p className="alert alert-error" role="alert">{error || job?.error}</p>
        <button className="btn btn-primary" onClick={onReset}>Try again</button>
      </div>
    )
  }

  if (job?.status === 'DONE' && job.result) {
    return <ResultView jobId={jobId} job={job} result={job.result} onReset={onReset} />
  }

  // Still running: show which of the three Step Functions stages is active.
  const current = Math.max(0, STAGES.findIndex((s) => s.key === job?.stage))
  return (
    <div className="card progress">
      <h1>Tailoring your resume…</h1>
      <p className="muted">This usually takes under a minute.</p>
      <ol aria-label="Pipeline progress">
        {STAGES.map((s, i) => (
          <li key={s.key} className={i < current ? 'done' : i === current ? 'active' : ''}>{s.label}</li>
        ))}
      </ol>
    </div>
  )
}

/** "Email me this draft": the user decides when to send it. */
function EmailButton({ jobId, alreadySent }: { jobId: string; alreadySent: boolean }) {
  const [state, setState] = useState<'idle' | 'sending' | 'sent'>(alreadySent ? 'sent' : 'idle')
  const [error, setError] = useState('')

  async function send() {
    setState('sending')
    setError('')
    try {
      await emailJob(jobId)
      setState('sent')
    } catch (err) {
      setError((err as Error).message) // e.g. the address is not verified in SES sandbox mode
      setState('idle')
    }
  }

  if (state === 'sent') return <p className="alert alert-success">Sent. Check your inbox (and the Spam folder) for the PDF.</p>
  return (
    <>
      <button className="btn" onClick={send} disabled={state === 'sending'}>
        {state === 'sending' ? 'Sending…' : 'Email me this draft'}
      </button>
      {error && <p className="alert alert-error" role="alert">{error}</p>}
    </>
  )
}

function ResultView({ jobId, job, result, onReset }: { jobId: string; job: Job; result: Result; onReset: () => void }) {
  const mustHave = result.gaps.filter((g) => g.category === 'must_have')
  const niceToHave = result.gaps.filter((g) => g.category !== 'must_have')

  return (
    <div className="stack">
      <section className="card hero">
        <div className="score" aria-label={`Match score ${result.score} out of 100`}>
          {result.score}<small>/100</small>
        </div>
        <div>
          <h1>{result.score >= 75 ? 'Strong match' : result.score >= 50 ? 'Partial match' : 'Low match'}</h1>
          <p className="muted">
            Evidence for {result.matched.length} of {result.matched.length + result.gaps.length} requirements.
          </p>
          <div className="actions-left">
            <a className="btn btn-primary" href={job.downloadUrl}>Download PDF</a>
            <EmailButton jobId={jobId} alreadySent={job.emailStatus === 'SENT'} />
            <button className="btn btn-ghost" onClick={onReset}>Tailor another</button>
          </div>
        </div>
      </section>

      <div className="grid">
        {result.lowMatch ? (
          // Nothing in the resume fits this job, so no draft was written (honesty: we never invent a fit).
          <section className="card">
            <h2>This job does not match your resume</h2>
            <p>Your resume shows none of the job's key requirements, so we did not write a tailored draft.</p>
            <p className="hint">The gap list shows what this role needs that your resume does not show yet.</p>
          </section>
        ) : (
          <div className="stack">
            <section className="card">
              <h2>Summary</h2>
              <p>{result.summary}</p>
            </section>
            <section className="card">
              <h2>Tailored bullets</h2>
              <ul>{result.bullets.map((b) => <li key={b}>{b}</li>)}</ul>
              <p className="hint">Every bullet is based on a line in your resume and was fact-checked against it.</p>
            </section>
          </div>
        )}

        <div className="stack">
          <section className="card">
            <h2>Gap list</h2>
            <p className="hint">Requirements your resume does not show yet. These are never invented into bullets.</p>
            <GapGroup title="Must have" tone="must" gaps={mustHave} />
            <GapGroup title="Nice to have" tone="nice" gaps={niceToHave} />
          </section>
          <section className="card">
            <h2>Matched requirements</h2>
            <ul className="boxes">
              {result.matched.map((m) => (
                <li key={m.requirement}><strong>{m.requirement}</strong><blockquote>{m.evidence}</blockquote></li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  )
}

function GapGroup({ title, tone, gaps }: { title: string; tone: string; gaps: Gap[] }) {
  if (gaps.length === 0) return null
  return (
    <>
      <h3 className={`gap-${tone}`}>{title}</h3>
      <ul className="boxes">
        {gaps.map((g) => (
          <li key={g.requirement}><strong>{g.requirement}</strong><span className="muted">{g.reason}</span></li>
        ))}
      </ul>
    </>
  )
}
