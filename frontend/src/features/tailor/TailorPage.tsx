import { useState } from 'react'
import { useAuth } from '../../auth/context'
import { Alert } from '../../components/ui/Alert'
import { Button } from '../../components/ui/Button'
import { usePollJob } from '../../hooks/usePollJob'
import { Processing } from './Processing'
import { ResultView } from './ResultView'
import { TailorForm } from './TailorForm'

function JobView({ jobId, onReset }: { jobId: string; onReset: () => void }) {
  const { job, error } = usePollJob(jobId)

  if (error || job?.status === 'FAILED') {
    return (
      <section className="card stack" aria-labelledby="failed-title">
        <h1 id="failed-title" className="card-title">
          We could not finish this one
        </h1>
        <Alert tone="error">{error ?? job?.error?.message ?? 'The job failed. Please try again.'}</Alert>
        <div>
          <Button variant="primary" onClick={onReset}>
            Try again
          </Button>
        </div>
      </section>
    )
  }
  if (job?.status === 'DONE' && job.result) {
    return <ResultView result={job.result} downloadUrl={job.downloadUrl} email={job.email} onReset={onReset} />
  }
  return <Processing stage={job?.stage ?? null} />
}

export function TailorPage() {
  const { email } = useAuth()
  const [jobId, setJobId] = useState<string | null>(null)
  return jobId ? (
    <JobView key={jobId} jobId={jobId} onReset={() => setJobId(null)} />
  ) : (
    <TailorForm email={email} onSubmitted={setJobId} />
  )
}
