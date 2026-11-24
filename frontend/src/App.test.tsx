import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'
import App from './App'
import JobView from './JobView'

// A token that is valid for one hour, for user me@example.com.
const payload = btoa(JSON.stringify({ email: 'me@example.com', exp: Date.now() / 1000 + 3600 }))
const signIn = () => sessionStorage.setItem('resume-tailor.idToken', `h.${payload}.s`)

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

const done: api.Job = {
  status: 'DONE',
  stage: 'done',
  downloadUrl: 'https://example.com/file.pdf',
  emailStatus: null,
  result: {
    score: 67,
    summary: 'Python engineer.',
    bullets: ['Built APIs in Python.'],
    gaps: [{ requirement: 'Kubernetes', category: 'nice_to_have', reason: 'Not in resume.' }],
    matched: [{ requirement: 'Python', evidence: 'Built REST APIs in Python' }],
  },
}

describe('App', () => {
  it('shows the sign-in form when signed out', () => {
    render(<App />)
    expect(screen.getByRole('form', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('submits, polls and shows the draft, gap list, PDF link and email status', async () => {
    signIn()
    vi.spyOn(api, 'submitJob').mockResolvedValue({ jobId: 'j1' })
    vi.spyOn(api, 'getJob').mockResolvedValue(done)
    render(<App />)

    await userEvent.click(screen.getByRole('button', { name: 'Try a sample' }))
    await userEvent.click(screen.getByRole('button', { name: 'Tailor my resume' }))

    expect(await screen.findByText('Python engineer.')).toBeInTheDocument()
    expect(screen.getByText('Kubernetes')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download PDF' })).toHaveAttribute('href', done.downloadUrl)
    // email only when the user asks for it
    const emailSpy = vi.spyOn(api, 'emailJob').mockResolvedValue({ emailStatus: 'SENT' })
    await userEvent.click(screen.getByRole('button', { name: 'Email me this draft' }))
    expect(emailSpy).toHaveBeenCalledWith('j1')
    expect(await screen.findByText(/check your inbox/i)).toBeInTheDocument()
  })

  it('rejects a PDF upload and explains why submit is disabled', async () => {
    signIn()
    render(<App />)
    const pdf = new File(['%PDF-1.4 binary'], 'resume.pdf', { type: 'application/pdf' })
    await userEvent.upload(screen.getByLabelText('Upload Resume'), pdf, { applyAccept: false })
    expect(screen.getByRole('alert')).toHaveTextContent('resume.pdf is not a .txt file')
    expect(screen.getByText('Add the resume.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tailor my resume' })).toBeDisabled()
  })

  it('shows a no-match message instead of a draft for a different job', async () => {
    const low = { ...done, result: { ...done.result!, score: 0, lowMatch: true, summary: '', bullets: [], matched: [] } }
    vi.spyOn(api, 'getJob').mockResolvedValue(low)
    render(<JobView jobId="j1" onReset={() => {}} />)
    expect(await screen.findByText('This job does not match your resume')).toBeInTheDocument()
    expect(screen.queryByText('Tailored bullets')).not.toBeInTheDocument()
    expect(screen.getByText('Kubernetes')).toBeInTheDocument() // the gap list is still shown
  })

  it('shows the clear message from a failed pipeline', async () => {
    vi.spyOn(api, 'getJob').mockResolvedValue({ status: 'FAILED', stage: 'analyzer', error: 'The job description is missing for this job.' })
    render(<JobView jobId="j1" onReset={() => {}} />)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('The job description is missing'))
  })
})
