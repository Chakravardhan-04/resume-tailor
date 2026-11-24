import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'
import Tailor from './Tailor'
import type { Job } from './types'

const LONG = 'x'.repeat(60)

afterEach(() => vi.restoreAllMocks())

const doneJob: Job = {
  jobId: 'j1',
  status: 'DONE',
  stage: 'done',
  downloadUrl: 'https://example.com/file.pdf',
  email: { status: 'SENT', message: null },
  result: {
    score: 80,
    summary: 'Python engineer.',
    bullets: ['Built APIs in Python.'],
    gaps: [{ requirement: 'Kubernetes', category: 'nice_to_have', reason: 'Not in resume.' }],
    matched: [],
  },
}

async function fill(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Resume'), LONG)
  await user.type(screen.getByLabelText('Job description'), LONG)
}

describe('Tailor', () => {
  it('disables submit until both documents are long enough', async () => {
    const user = userEvent.setup()
    render(<Tailor />)
    const button = screen.getByRole('button', { name: /tailor my resume/i })
    expect(button).toBeDisabled()
    await fill(user)
    expect(button).toBeEnabled()
  })

  it('submits, polls, and renders the result with a download link and gap list', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'submitJob').mockResolvedValue('j1')
    vi.spyOn(api, 'getJob').mockResolvedValue(doneJob)
    render(<Tailor />)
    await fill(user)
    await user.click(screen.getByRole('button', { name: /tailor my resume/i }))

    await waitFor(() => expect(screen.getByText('Python engineer.')).toBeInTheDocument())
    expect(screen.getByText('Built APIs in Python.')).toBeInTheDocument()
    expect(screen.getByText('Kubernetes')).toBeInTheDocument()
    expect(screen.getByText(/we emailed this draft/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /download pdf/i })).toHaveAttribute('href', 'https://example.com/file.pdf')
  })

  it('explains a failed email while keeping the download link', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'submitJob').mockResolvedValue('j1')
    vi.spyOn(api, 'getJob').mockResolvedValue({
      ...doneJob,
      email: { status: 'FAILED', message: 'Recipient must be verified in SES sandbox.' },
    })
    render(<Tailor />)
    await fill(user)
    await user.click(screen.getByRole('button', { name: /tailor my resume/i }))
    expect(await screen.findByText(/must be verified in SES sandbox/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /download pdf/i })).toBeInTheDocument()
  })

  it('shows the server message when submit is rejected', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'submitJob').mockRejectedValue(new api.ApiError('The resume is too long.', 400))
    render(<Tailor />)
    await fill(user)
    await user.click(screen.getByRole('button', { name: /tailor my resume/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The resume is too long.')
  })

  it('shows a clear failure message from the pipeline', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'submitJob').mockResolvedValue('j1')
    vi.spyOn(api, 'getJob').mockResolvedValue({
      jobId: 'j1',
      status: 'FAILED',
      stage: 'analyzer',
      error: { code: 'InputError', message: 'The resume is missing.' },
    })
    render(<Tailor />)
    await fill(user)
    await user.click(screen.getByRole('button', { name: /tailor my resume/i }))
    expect(await screen.findByText('The resume is missing.')).toBeInTheDocument()
  })
})
