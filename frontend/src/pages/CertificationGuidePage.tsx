import { CheckCircle2, ChevronDown, Clock, IndianRupee, ShieldQuestion } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Card, EmptyState, ErrorState, Spinner } from '../components/ui'
import { listSchemes } from '../services/api'
import type { CertificationScheme } from '../types'

const typeLabels: Record<CertificationScheme['type'], string> = {
  'product-certification': 'Product Certification',
  hallmarking: 'Hallmarking',
  'management-system': 'Management System',
  'foreign-manufacturers': 'Foreign Manufacturers',
}

function SchemeCard({ scheme }: { scheme: CertificationScheme }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <Card className="overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full items-start justify-between gap-4 p-5 text-left"
      >
        <div>
          <span className="inline-block rounded-full bg-accent-50 px-2.5 py-0.5 text-xs font-medium text-accent-700">
            {typeLabels[scheme.type]}
          </span>
          <h3 className="mt-2 text-sm font-semibold text-slate-900">{scheme.name}</h3>
          <p className="mt-1 text-sm text-slate-500">{scheme.summary}</p>
          <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-500">
            <span className="flex items-center gap-1">
              <Clock size={13} /> ~{scheme.averageDurationDays} days
            </span>
            <span className="flex items-center gap-1">
              <IndianRupee size={13} /> {scheme.fees}
            </span>
          </div>
        </div>
        <ChevronDown
          size={18}
          className={`mt-1 shrink-0 text-slate-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
        />
      </button>

      {expanded && (
        <div className="border-t border-slate-100 bg-slate-50/50 p-5">
          <div className="mb-5">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <ShieldQuestion size={14} /> Eligibility
            </p>
            <ul className="space-y-1.5">
              {scheme.eligibility.map((item) => (
                <li key={item} className="flex items-start gap-2 text-sm text-slate-600">
                  <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-emerald-500" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Process Steps</p>
            <ol className="space-y-3">
              {scheme.steps.map((step) => (
                <li key={step.order} className="flex gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-600 text-xs font-semibold text-white">
                    {step.order}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-slate-800">{step.title}</p>
                    <p className="text-sm text-slate-500">{step.description}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </Card>
  )
}

export function CertificationGuidePage() {
  const [schemes, setSchemes] = useState<CertificationScheme[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    listSchemes()
      .then((results) => {
        setSchemes(results)
        setLoading(false)
      })
      .catch(() => {
        setError(true)
        setLoading(false)
      })
  }, [])

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-50 text-accent-600">
          <ShieldQuestion size={18} />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Certification Guide</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Explore BIS certification schemes, eligibility requirements, and step-by-step processes.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner size={28} />
        </div>
      ) : error ? (
        <ErrorState onRetry={() => window.location.reload()} />
      ) : schemes.length === 0 ? (
        <EmptyState icon={ShieldQuestion} title="No certification schemes available" />
      ) : (
        <div className="space-y-4">
          {schemes.map((scheme) => (
            <SchemeCard key={scheme.id} scheme={scheme} />
          ))}
        </div>
      )}
    </div>
  )
}
