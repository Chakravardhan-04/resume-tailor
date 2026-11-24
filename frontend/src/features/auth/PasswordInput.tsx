import { useState } from 'react'

interface Props {
  id: string
  value: string
  onChange: (value: string) => void
  autoComplete: 'current-password' | 'new-password'
  disabled?: boolean
  describedBy?: string
}

export function PasswordInput({ id, value, onChange, autoComplete, disabled, describedBy }: Props) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="input-group">
      <input
        id={id}
        className="input"
        type={visible ? 'text' : 'password'}
        autoComplete={autoComplete}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        aria-describedby={describedBy}
      />
      <button
        type="button"
        className="input-addon"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? 'Hide password' : 'Show password'}
        aria-pressed={visible}
      >
        {visible ? 'Hide' : 'Show'}
      </button>
    </div>
  )
}
