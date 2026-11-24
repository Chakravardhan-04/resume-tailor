import type { Job } from './types'

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError('Network error. Check your connection and try again.', 0)
  }
  const body = (await res.json().catch(() => ({}))) as { error?: string } & Record<string, unknown>
  if (!res.ok) {
    throw new ApiError(body.error ?? `Request failed (${res.status}).`, res.status)
  }
  return body as T
}

export async function submitJob(resume: string, jobDescription: string, email: string): Promise<string> {
  const { jobId } = await request<{ jobId: string }>('/api/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resume, jobDescription, email }),
  })
  return jobId
}

export function getJob(jobId: string, signal?: AbortSignal): Promise<Job> {
  return request<Job>(`/api/jobs/${encodeURIComponent(jobId)}`, { signal })
}
