import { useEffect, useState } from 'react'

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(timer)
  }, [copied])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
    } catch {
      // Clipboard can be blocked (permissions, insecure context); the text stays selectable.
    }
  }

  return (
    <button type="button" className="btn btn-ghost btn-sm" onClick={() => void copy()} aria-live="polite">
      {copied ? 'Copied' : label}
    </button>
  )
}
