import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import type { Job } from '../types'
import { usePollJob } from './usePollJob'

const running: Job = { jobId: 'j', status: 'RUNNING', stage: 'scorer' }
const done: Job = { jobId: 'j', status: 'DONE', stage: 'done' }

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('usePollJob', () => {
  it('polls until the job is done, then stops', async () => {
    const spy = vi.spyOn(api, 'getJob').mockResolvedValueOnce(running).mockResolvedValueOnce(running).mockResolvedValue(done)
    const { result } = renderHook(() => usePollJob('j'))

    await act(async () => {})
    expect(result.current.job?.status).toBe('RUNNING')
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(result.current.job?.status).toBe('DONE')

    await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
    expect(spy).toHaveBeenCalledTimes(3)
  })

  it('reports an error after repeated failures', async () => {
    vi.spyOn(api, 'getJob').mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => usePollJob('j'))
    for (let i = 0; i < 6; i++) await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(result.current.error).toBe('boom')
  })

  it('stops polling on unmount', async () => {
    const spy = vi.spyOn(api, 'getJob').mockResolvedValue(running)
    const { unmount } = renderHook(() => usePollJob('j'))
    await act(async () => {})
    unmount()
    await act(async () => { await vi.advanceTimersByTimeAsync(20000) })
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('does nothing without a job id', () => {
    const spy = vi.spyOn(api, 'getJob')
    renderHook(() => usePollJob(null))
    expect(spy).not.toHaveBeenCalled()
  })
})
