import type { ReactNode } from 'react'

type Tone = 'info' | 'success' | 'warning' | 'error'

const ICONS: Record<Tone, string> = { info: 'i', success: '✓', warning: '!', error: '!' }

export function Alert({ tone = 'info', title, children }: { tone?: Tone; title?: string; children: ReactNode }) {
  return (
    <div className={`alert alert-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span className="alert-icon" aria-hidden="true">
        {ICONS[tone]}
      </span>
      <div>
        {title && <strong className="alert-title">{title}</strong>}
        <div>{children}</div>
      </div>
    </div>
  )
}
