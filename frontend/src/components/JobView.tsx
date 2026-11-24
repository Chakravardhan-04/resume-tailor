import { usePollJob } from '../hooks/usePollJob'
import { Progress } from './Progress'
import { ResultView } from './ResultView'

export function JobView({ jobId, onReset }: { jobId: string; onReset: () => void }) {
  const { job, error } = usePollJob(jobId)

  if (error || job?.status === 'FAILED') {
    return (
      <div className="panel" role="alert">
        <h2>Something went wrong</h2>
        <p>{error ?? job?.error?.message ?? 'The job failed. Please try again.'}</p>
        <button type="button" className="btn" onClick={onReset}>
          Try again
        </button>
      </div>
    )
  }
  if (job?.status === 'DONE' && job.result) {
    return <ResultView result={job.result} downloadUrl={job.downloadUrl} email={job.email} onReset={onReset} />
  }
  return (
    <div className="panel">
      <h2>Working on it…</h2>
      <p className="muted">This usually takes under a minute. You can keep this tab open.</p>
      <Progress stage={job?.stage ?? null} />
    </div>
  )
}
