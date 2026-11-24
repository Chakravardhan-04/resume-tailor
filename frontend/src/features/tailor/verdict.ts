export type Tone = 'good' | 'fair' | 'low'

/** Human label for a 0-100 match score. */
export function verdict(score: number): { label: string; tone: Tone } {
  if (score >= 75) return { label: 'Strong match', tone: 'good' }
  if (score >= 50) return { label: 'Partial match', tone: 'fair' }
  return { label: 'Low match', tone: 'low' }
}
