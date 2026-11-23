import { useEffect, useState } from 'react'
import { getJob } from '../api'
import type { Job } from '../types'

const INTERVAL_MS = 3000
const MAX_CONSECUTIVE_ERRORS = 5
const MAX_DURATION_MS = 6 * 60 * 1000

export interface PollState {
  job: Job | null
  error: string | null
}

/** Polls GET /api/jobs/{id} until the job is DONE or FAILED. Stops on unmount or id change. */
export function usePollJob(jobId: string | null): PollState {
  const [state, setState] = useState<PollState>({ job: null, error: null })

  useEffect(() => {
    if (!jobId) return
    const controller = new AbortController()
    const startedAt = Date.now()
    let timer: ReturnType<typeof setTimeout> | undefined
    let failures = 0

    const tick = async () => {
      try {
        const job = await getJob(jobId, controller.signal)
        if (controller.signal.aborted) return
        failures = 0
        setState({ job, error: null })
        if (job.status !== 'RUNNING') return
      } catch (err) {
        if (controller.signal.aborted) return
        failures += 1
        if (failures >= MAX_CONSECUTIVE_ERRORS) {
          setState((s) => ({ ...s, error: err instanceof Error ? err.message : 'Lost connection to the server.' }))
          return
        }
      }
      if (Date.now() - startedAt > MAX_DURATION_MS) {
        setState((s) => ({ ...s, error: 'This is taking longer than expected. Please try again.' }))
        return
      }
      timer = setTimeout(tick, INTERVAL_MS)
    }

    void tick()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [jobId])

  return jobId ? state : { job: null, error: null }
}
