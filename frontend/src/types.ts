export type JobStatus = 'RUNNING' | 'DONE' | 'FAILED'

export interface Gap {
  requirement: string
  category: 'must_have' | 'nice_to_have'
  reason: string
}

export interface TailoredResult {
  score: number
  summary: string
  bullets: string[]
  gaps: Gap[]
  matched: { requirement: string; evidence: string }[]
}

export interface Job {
  jobId: string
  status: JobStatus
  stage: string | null
  result?: TailoredResult
  downloadUrl?: string
  error?: { code: string | null; message: string | null }
}
