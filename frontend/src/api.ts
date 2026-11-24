import type { Job } from './types'

interface AuthHandlers {
  getToken: () => Promise<string | null>
  onUnauthorized: () => void
}

let handlers: AuthHandlers = { getToken: async () => null, onUnauthorized: () => undefined }

export function setAuthHandlers(h: AuthHandlers): void {
  handlers = h
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await handlers.getToken()
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let res: Response
  try {
    res = await fetch(path, { ...init, headers })
  } catch {
    throw new ApiError('Network error. Check your connection and try again.', 0)
  }
  const body = (await res.json().catch(() => ({}))) as { error?: string } & Record<string, unknown>
  if (res.status === 401) {
    handlers.onUnauthorized()
    throw new ApiError('Your session has expired. Please sign in again.', 401)
  }
  if (!res.ok) {
    throw new ApiError(body.error ?? `Request failed (${res.status}).`, res.status)
  }
  return body as T
}

export async function submitJob(resume: string, jobDescription: string): Promise<string> {
  const { jobId } = await request<{ jobId: string }>('/api/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resume, jobDescription }),
  })
  return jobId
}

export function getJob(jobId: string, signal?: AbortSignal): Promise<Job> {
  return request<Job>(`/api/jobs/${encodeURIComponent(jobId)}`, { signal })
}
