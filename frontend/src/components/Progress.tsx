const STAGES = [
  { key: 'analyzer', label: 'Analyzing the job requirements' },
  { key: 'scorer', label: 'Scoring your resume and finding gaps' },
  { key: 'rewriter', label: 'Rewriting honestly from your resume' },
] as const

export function Progress({ stage }: { stage: string | null }) {
  const current = STAGES.findIndex((s) => s.key === stage)
  return (
    <ol className="progress" aria-live="polite" aria-label="Pipeline progress">
      {STAGES.map((s, i) => {
        const state = i < current ? 'done' : i === current ? 'active' : 'pending'
        return (
          <li key={s.key} className={state} aria-current={state === 'active' ? 'step' : undefined}>
            {s.label}
          </li>
        )
      })}
    </ol>
  )
}
