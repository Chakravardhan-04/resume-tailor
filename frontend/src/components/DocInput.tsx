import { useId, useState } from 'react'
import { MAX_DOC_CHARS } from '../limits'

interface Props {
  label: string
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  placeholder?: string
}

const ACCEPTED = '.txt,.md,text/plain,text/markdown'

export function DocInput({ label, value, onChange, disabled, placeholder }: Props) {
  const id = useId()
  const [fileError, setFileError] = useState<string | null>(null)

  const onFile = async (file: File | undefined) => {
    setFileError(null)
    if (!file) return
    if (!/\.(txt|md)$/i.test(file.name)) {
      setFileError('Please choose a .txt or .md file, or paste the text.')
      return
    }
    if (file.size > MAX_DOC_CHARS * 4) {
      setFileError('That file is too large.')
      return
    }
    onChange(await file.text())
  }

  const over = value.length > MAX_DOC_CHARS
  return (
    <div className="field">
      <div className="field-head">
        <label htmlFor={id}>{label}</label>
        <label className="file-btn">
          Upload .txt
          <input
            type="file"
            accept={ACCEPTED}
            disabled={disabled}
            aria-label={`Upload ${label} file`}
            onChange={(e) => {
              void onFile(e.target.files?.[0])
              e.target.value = ''
            }}
          />
        </label>
      </div>
      <textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        placeholder={placeholder}
        rows={12}
        aria-invalid={over}
      />
      <div className={over ? 'count over' : 'count'}>
        {value.length.toLocaleString()} / {MAX_DOC_CHARS.toLocaleString()} characters
      </div>
      {fileError && (
        <div role="alert" className="error">
          {fileError}
        </div>
      )}
    </div>
  )
}
