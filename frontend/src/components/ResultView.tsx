import type { TailoredResult } from '../types'

interface Props {
  result: TailoredResult
  downloadUrl?: string
  onReset: () => void
}

export function ResultView({ result, downloadUrl, onReset }: Props) {
  return (
    <section className="result" aria-label="Tailored result">
      <div className="result-head">
        <div className="score" aria-label={`Match score ${result.score} out of 100`}>
          <span>{result.score}</span>/100
        </div>
        <div className="actions">
          {downloadUrl && (
            <a className="btn primary" href={downloadUrl} download="tailored-resume.pdf">
              Download PDF
            </a>
          )}
          <button type="button" className="btn" onClick={onReset}>
            Start over
          </button>
        </div>
      </div>

      <h2>Summary</h2>
      <p>{result.summary}</p>

      <h2>Tailored bullets</h2>
      <ul>
        {result.bullets.map((b, i) => (
          <li key={i}>{b}</li>
        ))}
      </ul>

      <h2>Gap list</h2>
      {result.gaps.length === 0 ? (
        <p>No gaps found. Your resume supports every stated requirement.</p>
      ) : (
        <>
          <p className="muted">Requirements your resume does not yet demonstrate. These are never invented into bullets.</p>
          <ul className="gaps">
            {result.gaps.map((g, i) => (
              <li key={i}>
                <span className={`tag ${g.category}`}>{g.category === 'must_have' ? 'Must have' : 'Nice to have'}</span>{' '}
                <strong>{g.requirement}</strong>
                <div className="muted">{g.reason}</div>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="muted small">The download link expires after 15 minutes.</p>
    </section>
  )
}
