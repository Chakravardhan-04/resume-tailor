import { Alert } from '../../components/ui/Alert'
import { Button } from '../../components/ui/Button'
import { CopyButton } from '../../components/ui/CopyButton'
import type { Gap, Job, TailoredResult } from '../../types'
import { ScoreRing } from './ScoreRing'
import { verdict } from './verdict'

interface Props {
  result: TailoredResult
  downloadUrl?: string
  email?: Job['email']
  onReset: () => void
}

function GapGroup({ title, gaps, tone }: { title: string; gaps: Gap[]; tone: 'must' | 'nice' }) {
  if (gaps.length === 0) return null
  return (
    <div className="gap-group">
      <h3 className={`gap-heading gap-${tone}`}>
        {title} <span className="badge">{gaps.length}</span>
      </h3>
      <ul className="gap-list">
        {gaps.map((g) => (
          <li key={g.requirement}>
            <strong>{g.requirement}</strong>
            <span className="muted">{g.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function ResultView({ result, downloadUrl, email, onReset }: Props) {
  const must = result.gaps.filter((g) => g.category === 'must_have')
  const nice = result.gaps.filter((g) => g.category !== 'must_have')
  const total = result.matched.length + result.gaps.length
  const { label } = verdict(result.score)
  const bulletsText = result.bullets.map((b) => `• ${b}`).join('\n')

  return (
    <div className="stack">
      <section className="card result-hero" aria-label="Match overview">
        <ScoreRing score={result.score} />
        <div className="result-summary">
          <h1 className="card-title">{label}</h1>
          <p className="muted">
            Your resume shows evidence for {result.matched.length} of {total} requirements.{' '}
            {must.length > 0
              ? `${must.length} must-have ${must.length === 1 ? 'requirement is' : 'requirements are'} missing.`
              : 'No must-have requirements are missing.'}
          </p>
          <div className="result-actions">
            {downloadUrl && (
              <a className="btn btn-primary" href={downloadUrl} download="tailored-resume.pdf">
                Download PDF
              </a>
            )}
            <Button onClick={onReset}>Tailor another</Button>
          </div>
        </div>
      </section>

      {email?.status === 'SENT' && (
        <Alert tone="success">We emailed this draft, with the PDF attached, to the email address on your account.</Alert>
      )}
      {email?.status === 'FAILED' && (
        <Alert tone="warning" title="Email not sent">
          {email.message ?? 'The email could not be sent. You can still download the PDF.'}
        </Alert>
      )}

      <div className="result-grid">
        <div className="stack">
          <section className="card" aria-labelledby="summary-title">
            <div className="section-head">
              <h2 id="summary-title">Summary</h2>
              <CopyButton text={result.summary} />
            </div>
            <p className="prose">{result.summary}</p>
          </section>

          <section className="card" aria-labelledby="bullets-title">
            <div className="section-head">
              <h2 id="bullets-title">Tailored bullets</h2>
              <CopyButton text={bulletsText} label="Copy all" />
            </div>
            <ul className="bullet-list">
              {result.bullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
            <p className="hint">Each bullet is based on a line in your resume and was fact-checked against it.</p>
          </section>
        </div>

        <div className="stack">
          <section className="card" aria-labelledby="gaps-title">
            <div className="section-head">
              <h2 id="gaps-title">Gap list</h2>
            </div>
            {result.gaps.length === 0 ? (
              <p className="muted">No gaps. Your resume supports every stated requirement.</p>
            ) : (
              <>
                <p className="hint">Requirements your resume does not show yet. These are never invented into bullets.</p>
                <GapGroup title="Must have" gaps={must} tone="must" />
                <GapGroup title="Nice to have" gaps={nice} tone="nice" />
              </>
            )}
          </section>

          {result.matched.length > 0 && (
            <details className="card evidence">
              <summary>
                <h2>Matched requirements</h2>
                <span className="badge">{result.matched.length}</span>
              </summary>
              <ul className="evidence-list">
                {result.matched.map((m) => (
                  <li key={m.requirement}>
                    <strong>{m.requirement}</strong>
                    <blockquote>{m.evidence}</blockquote>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
      <p className="hint center">The download link expires after 15 minutes. Review the draft before sending it.</p>
    </div>
  )
}
