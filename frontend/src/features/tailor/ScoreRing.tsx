import { verdict } from './verdict'

const RADIUS = 42
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export function ScoreRing({ score }: { score: number }) {
  const clamped = Math.min(100, Math.max(0, score))
  const { tone } = verdict(clamped)
  return (
    <div className={`score-ring score-${tone}`} role="img" aria-label={`Match score ${clamped} out of 100`}>
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle className="score-track" cx="50" cy="50" r={RADIUS} />
        <circle
          className="score-value"
          cx="50"
          cy="50"
          r={RADIUS}
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={CIRCUMFERENCE * (1 - clamped / 100)}
        />
      </svg>
      <span className="score-number">
        {clamped}
        <small>/100</small>
      </span>
    </div>
  )
}
