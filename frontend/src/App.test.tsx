import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'
import App from './App'
import type { Job } from './types'

const LONG = 'x'.repeat(60)

afterEach(() => vi.restoreAllMocks())

const doneJob: Job = {
  jobId: 'j1',
  status: 'DONE',
  stage: 'done',
  downloadUrl: 'https://example.com/file.pdf',
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

describe('App', () => {
  it('shows the demo-only warning', () => {
    render(<App />)
    expect(screen.getByRole('note')).toHaveTextContent(/demo only/i)
  })

  it('disables submit until both documents are long enough', async () => {
    const user = userEvent.setup()
    render(<App />)
    const button = screen.getByRole('button', { name: /tailor my resume/i })
    expect(button).toBeDisabled()
    await fill(user)
    expect(button).toBeEnabled()
  })

  it('submits, polls, and renders the result with a download link and gap list', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'submitJob').mockResolvedValue('j1')
    vi.spyOn(api, 'getJob').mockResolvedValue(doneJob)
    render(<App />)
    await fill(user)
    await user.click(screen.getByRole('button', { name: /tailor my resume/i }))

    await waitFor(() => expect(screen.getByText('Python engineer.')).toBeInTheDocument())
    expect(screen.getByText('Built APIs in Python.')).toBeInTheDocument()
    expect(screen.getByText('Kubernetes')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /download pdf/i })).toHaveAttribute('href', 'https://example.com/file.pdf')
  })

  it('shows the server message when submit is rejected', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'submitJob').mockRejectedValue(new api.ApiError('The resume is too long.', 400))
    render(<App />)
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
    render(<App />)
    await fill(user)
    await user.click(screen.getByRole('button', { name: /tailor my resume/i }))
    expect(await screen.findByText('The resume is missing.')).toBeInTheDocument()
  })
})
