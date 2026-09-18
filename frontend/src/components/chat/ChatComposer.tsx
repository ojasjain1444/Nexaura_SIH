import { SendHorizontal } from 'lucide-react'
import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { Button } from '../ui'

interface ChatComposerProps {
  onSend: (text: string) => void
  disabled?: boolean
}

export function ChatComposer({ onSend, disabled }: ChatComposerProps) {
  const [value, setValue] = useState('')

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!value.trim() || disabled) return
    onSend(value)
    setValue('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2 border-t border-slate-200 bg-white p-3 sm:p-4">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        // Shortened from the original longer placeholder ("Ask about a
        // standard, certification scheme, or testing lab...") — that
        // text wrapped to 2 lines on a normal phone and 3 lines on a
        // narrower one (confirmed via computed styles: scrollHeight kept
        // exceeding whatever fixed min-height was set, since the exact
        // wrap point depends on viewport width). A short placeholder
        // that reliably fits one line at any real phone width fixes the
        // root cause instead of chasing per-width pixel values.
        placeholder="Ask a question..."
        rows={1}
        aria-label="Message"
        className="max-h-32 flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/20"
      />
      <Button type="submit" disabled={!value.trim() || disabled} aria-label="Send message">
        <SendHorizontal size={16} />
      </Button>
    </form>
  )
}
