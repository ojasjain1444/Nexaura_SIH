import { FileText } from 'lucide-react'
import type { SourceCitation } from '../../types'

export function SourceCitationList({ sources }: { sources: SourceCitation[] }) {
  if (sources.length === 0) return null

  return (
    <div className="mt-3 space-y-1.5 border-t border-slate-200 pt-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Sources</p>
      {sources.map((source) => (
        <div
          key={source.id}
          className="flex items-start gap-2 rounded-lg bg-slate-50 px-2.5 py-2 text-xs text-slate-600"
        >
          <FileText size={14} className="mt-0.5 shrink-0 text-slate-400" />
          <span>
            <span className="font-semibold text-slate-700">{source.standardCode}</span>
            {' — '}
            {source.title}
            {source.clause && <span className="text-slate-400"> ({source.clause})</span>}
          </span>
        </div>
      ))}
    </div>
  )
}
