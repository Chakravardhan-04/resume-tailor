import { useEffect, useState } from 'react'
import { Spinner } from '../../components/ui/Spinner'

const STAGES = [
  { key: 'analyzer', title: 'Reading the job', text: 'Extracting must-have and nice-to-have requirements.' },
  { key: 'scorer', title: 'Scoring your resume', text: 'Matching each requirement to evidence in your resume.' },
  { key: 'rewriter', title: 'Rewriting honestly', text: 'Tailoring your bullets and checking every claim.' },
] as const

function useElapsedSeconds() {
  const [start] = useState(() => Date.now())
  const [now, setNow] = useState(start)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  return Math.floor((now - start) / 1000)
}

export function Processing({ stage }: { stage: string | null }) {
  const elapsed = useElapsedSeconds()
  const current = Math.max(
    0,
    STAGES.findIndex((s) => s.key === stage),
  )
  return (
    <section className="card processing" aria-labelledby="processing-title">
      <div className="processing-head">
        <div>
          <h1 id="processing-title" className="card-title">
            Tailoring your resume…
          </h1>
          <p className="muted">This usually takes under a minute. You can keep this tab open.</p>
        </div>
        <span className="elapsed" aria-label={`${elapsed} seconds elapsed`}>
          {elapsed}s
        </span>
      </div>
      <ol className="stepper" aria-label="Pipeline progress">
        {STAGES.map((s, i) => {
          const state = i < current ? 'done' : i === current ? 'active' : 'pending'
          return (
            <li key={s.key} className={`step step-${state}`} aria-current={state === 'active' ? 'step' : undefined}>
              <span className="step-marker" aria-hidden="true">
                {state === 'done' ? '✓' : state === 'active' ? <Spinner /> : i + 1}
              </span>
              <div>
                <strong>{s.title}</strong>
                <span className="muted">{s.text}</span>
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
