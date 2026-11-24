import { type DragEvent, useId, useRef, useState } from 'react'
import { MAX_DOC_CHARS, MIN_DOC_CHARS } from '../../limits'

interface Props {
  label: string
  hint: string
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  placeholder?: string
}

const ACCEPT = '.txt,.md,text/plain,text/markdown'

export function DocInput({ label, hint, value, onChange, disabled, placeholder }: Props) {
  const id = useId()
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)

  const readFile = async (file: File | undefined) => {
    setFileError(null)
    if (!file) return
    if (!/\.(txt|md)$/i.test(file.name)) {
      setFileError('Use a .txt or .md file, or paste the text.')
      return
    }
    if (file.size > MAX_DOC_CHARS * 4) {
      setFileError('That file is too large.')
      return
    }
    onChange(await file.text())
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (!disabled) void readFile(e.dataTransfer.files[0])
  }

  const length = value.trim().length
  const over = value.length > MAX_DOC_CHARS
  const short = length > 0 && length < MIN_DOC_CHARS
  const status = over
    ? `Too long by ${(value.length - MAX_DOC_CHARS).toLocaleString()} characters`
    : short
      ? `At least ${MIN_DOC_CHARS} characters`
      : `${value.length.toLocaleString()} / ${MAX_DOC_CHARS.toLocaleString()}`

  return (
    <div className="card doc-card">
      <div className="doc-head">
        <div>
          <label htmlFor={id} className="doc-label">
            {label}
          </label>
          <p className="hint">{hint}</p>
        </div>
        <div className="doc-actions">
          {value && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange('')} disabled={disabled}>
              Clear
            </button>
          )}
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => fileRef.current?.click()}
            disabled={disabled}
          >
            Upload file
          </button>
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT}
            hidden
            aria-label={`Upload ${label} file`}
            onChange={(e) => {
              void readFile(e.target.files?.[0])
              e.target.value = ''
            }}
          />
        </div>
      </div>
      <textarea
        id={id}
        className={dragging ? 'textarea dragging' : 'textarea'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        disabled={disabled}
        placeholder={placeholder}
        spellCheck={false}
        aria-invalid={over || short || undefined}
        aria-describedby={`${id}-count`}
      />
      <div className="doc-foot">
        <span className="hint">Paste text, or drop a .txt / .md file</span>
        <span id={`${id}-count`} className={over || short ? 'count count-bad' : 'count'}>
          {status}
        </span>
      </div>
      {fileError && (
        <p role="alert" className="field-error">
          {fileError}
        </p>
      )}
    </div>
  )
}
