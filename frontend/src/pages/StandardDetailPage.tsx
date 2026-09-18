import { ArrowLeft, Calendar, Factory, MessageSquareText, Tag } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { StandardStatusBadge } from '../components/standards/StandardStatusBadge'
import { Button, Card, ErrorState, Spinner } from '../components/ui'
import { getStandardById } from '../services/api'
import type { IndianStandard } from '../types'

export function StandardDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [standard, setStandard] = useState<IndianStandard | null | undefined>(undefined)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!id) return
    setStandard(undefined)
    setError(false)
    getStandardById(id)
      .then((result) => setStandard(result ?? null))
      .catch(() => setError(true))
  }, [id])

  if (error) {
    return <ErrorState onRetry={() => navigate(0)} />
  }

  if (standard === undefined) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size={28} />
      </div>
    )
  }

  if (standard === null) {
    return (
      <div className="mx-auto max-w-2xl text-center">
        <p className="text-sm text-slate-500">Standard not found.</p>
        <Link to="/standards" className="mt-4 inline-block text-sm font-medium text-accent-600 hover:text-accent-700">
          &larr; Back to Standards Explorer
        </Link>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <button
        onClick={() => navigate('/standards')}
        className="flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-700"
      >
        <ArrowLeft size={16} /> Back to Standards Explorer
      </button>

      <Card className="p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-accent-700">{standard.code}</p>
            <h1 className="mt-1 text-xl font-semibold text-slate-900">{standard.title}</h1>
          </div>
          <StandardStatusBadge status={standard.status} />
        </div>

        <p className="mt-4 text-sm leading-relaxed text-slate-600">{standard.description}</p>

        <div className="mt-6 grid grid-cols-1 gap-4 border-t border-slate-100 pt-6 sm:grid-cols-3">
          <div className="flex items-start gap-2">
            <Tag size={16} className="mt-0.5 text-slate-400" />
            <div>
              <p className="text-xs text-slate-500">Category</p>
              <p className="text-sm font-medium text-slate-700">{standard.category}</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <Factory size={16} className="mt-0.5 text-slate-400" />
            <div>
              <p className="text-xs text-slate-500">Sector</p>
              <p className="text-sm font-medium text-slate-700">{standard.sector}</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <Calendar size={16} className="mt-0.5 text-slate-400" />
            <div>
              <p className="text-xs text-slate-500">Last Amended</p>
              <p className="text-sm font-medium text-slate-700">
                {new Date(standard.lastAmended).toLocaleDateString('en-IN', { year: 'numeric', month: 'long', day: 'numeric' })}
              </p>
            </div>
          </div>
        </div>

        {standard.relatedCodes.length > 0 && (
          <div className="mt-6 border-t border-slate-100 pt-6">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Related Standards</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {standard.relatedCodes.map((code) => (
                <span key={code} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                  {code}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="mt-6 border-t border-slate-100 pt-6">
          <Link to={`/assistant?q=${encodeURIComponent(`Tell me more about ${standard.code}`)}`}>
            <Button variant="secondary" size="sm">
              <MessageSquareText size={14} /> Ask the assistant about this standard
            </Button>
          </Link>
        </div>
      </Card>
    </div>
  )
}
