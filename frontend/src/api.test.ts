import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getJob, submitJob } from './api'

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status })

afterEach(() => vi.restoreAllMocks())

describe('api', () => {
  it('submits both documents and returns the job id', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(202, { jobId: 'abc' }))
    await expect(submitJob('r', 'j')).resolves.toBe('abc')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/submit')
    expect(JSON.parse(String(init?.body))).toEqual({ resume: 'r', jobDescription: 'j' })
  })

  it('surfaces the server error message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(400, { error: 'The resume is too short.' }))
    await expect(submitJob('r', 'j')).rejects.toThrow('The resume is too short.')
  })

  it('maps network failures to a friendly ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('failed'))
    await expect(getJob('x')).rejects.toBeInstanceOf(ApiError)
  })

  it('encodes the job id in the path', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(200, { jobId: 'a/b', status: 'RUNNING' }))
    await getJob('a/b')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/jobs/a%2Fb')
  })
})
