import { render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../api'
import { AuthContext } from '../../auth/context'
import type { Job } from '../../types'
import { Processing } from './Processing'
import { ResultView } from './ResultView'
import { TailorForm } from './TailorForm'
import { TailorPage } from './TailorPage'
import { verdict } from './verdict'

const LONG = 'x'.repeat(60)

const signedIn = ({ children }: { children: ReactNode }) => (
  <AuthContext.Provider
    value={{ status: 'signedIn', email: 'me@example.com', signIn: async () => {}, signOut: async () => {} }}
  >
    {children}
  </AuthContext.Provider>
)

afterEach(() => vi.restoreAllMocks())

const result: NonNullable<Job['result']> = {
  score: 67,
  summary: 'Python engineer.',
  bullets: ['Built APIs in Python.', 'Designed DynamoDB tables.'],
  gaps: [
    { requirement: 'Terraform or AWS CDK', category: 'must_have', reason: 'Only AWS SAM is mentioned.' },
    { requirement: 'Kubernetes', category: 'nice_to_have', reason: 'Not in resume.' },
  ],
  matched: [
    { requirement: 'Strong Python skills', evidence: 'Built REST APIs in Python and Flask' },
    { requirement: 'AWS serverless', evidence: 'Designed DynamoDB tables....Deployed serverless services' },
  ],
}

const doneJob: Job = {
  jobId: 'j1',
  status: 'DONE',
  stage: 'done',
  downloadUrl: 'https://example.com/file.pdf',
  email: { status: 'SENT', message: null },
  result,
}

describe('verdict', () => {
  it('labels scores', () => {
    expect(verdict(80).label).toBe('Strong match')
    expect(verdict(67).label).toBe('Partial match')
    expect(verdict(20).label).toBe('Low match')
  })
})

describe('TailorForm', () => {
  it('enables submit only when both documents are valid', async () => {
    const user = userEvent.setup()
    render(<TailorForm email="me@example.com" onSubmitted={() => undefined} />)
    const submit = screen.getByRole('button', { name: /tailor my resume/i })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText('Resume'), LONG)
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText('Job description'), LONG)
    expect(submit).toBeEnabled()
    expect(screen.getByText('me@example.com')).toBeInTheDocument()
  })

  it('shows a short-text warning', async () => {
    const user = userEvent.setup()
    render(<TailorForm email="me@example.com" onSubmitted={() => undefined} />)
    await user.type(screen.getByLabelText('Resume'), 'too short')
    expect(screen.getByText(/at least 50 characters/i)).toBeInTheDocument()
    expect(screen.getByLabelText('Resume')).toHaveAttribute('aria-invalid', 'true')
  })

  it('fills both documents from the sample', async () => {
    const user = userEvent.setup()
    render(<TailorForm email="me@example.com" onSubmitted={() => undefined} />)
    await user.click(screen.getByRole('button', { name: /try a sample/i }))
    expect((screen.getByLabelText('Resume') as HTMLTextAreaElement).value).toContain('Alex Morgan')
    expect(screen.getByRole('button', { name: /tailor my resume/i })).toBeEnabled()
  })

  it('reads an uploaded .txt file', async () => {
    const user = userEvent.setup()
    render(<TailorForm email="me@example.com" onSubmitted={() => undefined} />)
    const file = new File([LONG], 'resume.txt', { type: 'text/plain' })
    await user.upload(screen.getByLabelText('Upload Resume file'), file)
    await waitFor(() => expect(screen.getByLabelText('Resume')).toHaveValue(LONG))
  })

  it('shows the server error and stays editable', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'submitJob').mockRejectedValue(new api.ApiError('Daily limit reached.', 429))
    render(<TailorForm email="me@example.com" onSubmitted={() => undefined} />)
    await user.click(screen.getByRole('button', { name: /try a sample/i }))
    await user.click(screen.getByRole('button', { name: /tailor my resume/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Daily limit reached.')
    expect(screen.getByLabelText('Resume')).toBeEnabled()
  })
})

describe('Processing', () => {
  it('marks earlier stages done and the current one active', () => {
    render(<Processing stage="scorer" />)
    const steps = within(screen.getByRole('list', { name: /pipeline progress/i })).getAllByRole('listitem')
    expect(steps[0]).toHaveClass('step-done')
    expect(steps[1]).toHaveAttribute('aria-current', 'step')
    expect(steps[2]).toHaveClass('step-pending')
  })
})

describe('ResultView', () => {
  it('shows score, verdict, bullets, grouped gaps, evidence and the download link', () => {
    render(<ResultView result={result} downloadUrl="https://example.com/file.pdf" onReset={() => undefined} />)
    expect(screen.getByRole('img', { name: 'Match score 67 out of 100' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Partial match' })).toBeInTheDocument()
    expect(screen.getByText(/evidence for 2 of 4 requirements/i)).toBeInTheDocument()
    expect(screen.getByText('Designed DynamoDB tables … Deployed serverless services')).toBeInTheDocument()
    expect(screen.getByText('Built APIs in Python.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /must have/i })).toBeInTheDocument()
    expect(screen.getByText('Terraform or AWS CDK')).toBeInTheDocument()
    expect(screen.getByText('Built REST APIs in Python and Flask')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /download pdf/i })).toHaveAttribute('href', 'https://example.com/file.pdf')
  })

  it('explains a failed email', () => {
    render(
      <ResultView
        result={result}
        email={{ status: 'FAILED', message: 'Recipient must be verified.' }}
        onReset={() => undefined}
      />,
    )
    expect(screen.getByText('Email not sent')).toBeInTheDocument()
    expect(screen.getByText('Recipient must be verified.')).toBeInTheDocument()
  })

  it('copies the bullets', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    render(<ResultView result={result} onReset={() => undefined} />)
    await user.click(screen.getByRole('button', { name: 'Copy all' }))
    expect(writeText).toHaveBeenCalledWith('• Built APIs in Python.\n• Designed DynamoDB tables.')
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })
})

describe('TailorPage', () => {
  it('submits, polls and renders the result with the email confirmation', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'submitJob').mockResolvedValue('j1')
    vi.spyOn(api, 'getJob').mockResolvedValue(doneJob)
    render(<TailorPage />, { wrapper: signedIn })
    await user.click(screen.getByRole('button', { name: /try a sample/i }))
    await user.click(screen.getByRole('button', { name: /tailor my resume/i }))
    expect(await screen.findByText('Python engineer.')).toBeInTheDocument()
    expect(screen.getByText(/we emailed this draft/i)).toBeInTheDocument()
  })

  it('shows the pipeline failure message with a retry', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'submitJob').mockResolvedValue('j1')
    vi.spyOn(api, 'getJob').mockResolvedValue({
      jobId: 'j1',
      status: 'FAILED',
      stage: 'analyzer',
      error: { code: 'InputError', message: 'The resume is missing.' },
    })
    render(<TailorPage />, { wrapper: signedIn })
    await user.click(screen.getByRole('button', { name: /try a sample/i }))
    await user.click(screen.getByRole('button', { name: /tailor my resume/i }))
    expect(await screen.findByText('The resume is missing.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(screen.getByLabelText('Resume')).toBeInTheDocument()
  })
})
