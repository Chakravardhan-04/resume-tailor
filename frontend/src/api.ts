/** The two API calls. CloudFront forwards /api/* to API Gateway, so these are same-origin requests. */
import { getToken } from './auth'

export interface Gap {
  requirement: string
  category: 'must_have' | 'nice_to_have'
  reason: string
}

export interface Result {
  score: number
  lowMatch?: boolean // true when the job does not fit the resume: no draft, only the gap list
  summary: string
  bullets: string[]
  gaps: Gap[]
  matched: { requirement: string; evidence: string }[]
}

export interface Job {
  status: 'RUNNING' | 'DONE' | 'FAILED'
  stage: string
  result?: Result
  downloadUrl?: string
  emailStatus?: string | null // 'SENT' once the user has emailed it
  error?: string
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` }, // Cognito ID token
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.error ?? body.message ?? `Request failed (${res.status})`)
  return body
}

/** POST /api/submit -> starts the Step Functions pipeline and returns the job id immediately. */
export const submitJob = (resume: string, jobDescription: string) =>
  request<{ jobId: string }>('/api/submit', { method: 'POST', body: JSON.stringify({ resume, jobDescription }) })

/** GET /api/jobs/{id} -> status, current stage, and the result once DONE. */
export const getJob = (jobId: string) => request<Job>(`/api/jobs/${jobId}`)

/** POST /api/jobs/{id}/email -> email the draft (with the PDF) to the signed-in user's address. */
export const emailJob = (jobId: string) => request<{ emailStatus: string }>(`/api/jobs/${jobId}/email`, { method: 'POST' })
