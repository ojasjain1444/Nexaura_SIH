import { useEffect, useState } from 'react'
import { Bot } from 'lucide-react'

// Answering takes a few seconds, most of it in the language model. Three
// silent dots for that long reads as a hung app, so the indicator names the
// stage it is in. The timings are approximate on purpose — they describe
// what the backend does in order (retrieve, then read, then compose)
// without pretending to report real progress events.
const STAGES = [
  { after: 0, label: 'Searching the standards…' },
  { after: 1200, label: 'Reading the matching clauses…' },
  { after: 3500, label: 'Composing a grounded answer…' },
  { after: 8000, label: 'Almost there…' },
]

export function ThinkingIndicator() {
  const [label, setLabel] = useState(STAGES[0].label)

  useEffect(() => {
    const timers = STAGES.slice(1).map((stage) =>
      window.setTimeout(() => setLabel(stage.label), stage.after),
    )
    return () => timers.forEach(window.clearTimeout)
  }, [])

  return (
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-600 text-white">
        <Bot size={16} />
      </div>
      <div className="flex items-center gap-2.5 rounded-2xl rounded-tl-sm border border-slate-200 bg-white px-4 py-3.5">
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
        </span>
        <span className="text-sm text-slate-500">{label}</span>
      </div>
    </div>
  )
}
