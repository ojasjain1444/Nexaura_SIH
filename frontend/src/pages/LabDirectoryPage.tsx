import { Building2, Mail, MapPin, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Badge, Card, EmptyState, ErrorState, Spinner } from '../components/ui'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { searchLabs } from '../services/api'
import type { TestingLab } from '../types'

export function LabDirectoryPage() {
  const [query, setQuery] = useState('')
  const [labs, setLabs] = useState<TestingLab[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const debouncedQuery = useDebouncedValue(query, 300)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)
    searchLabs({ search: debouncedQuery })
      .then((results) => {
        if (cancelled) return
        setLabs(results)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setError(true)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [debouncedQuery])

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-50 text-accent-600">
          <Building2 size={18} />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Lab Directory</h1>
          <p className="mt-0.5 text-sm text-slate-500">Find BIS-recognized testing laboratories by name or city.</p>
        </div>
      </div>

      <div className="relative max-w-md">
        <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by lab name or city..."
          aria-label="Search labs"
          className="w-full rounded-xl border border-slate-200 py-2.5 pl-9 pr-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/20"
        />
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner size={28} />
        </div>
      ) : error ? (
        <ErrorState onRetry={() => setQuery((q) => q)} />
      ) : labs.length === 0 ? (
        <EmptyState icon={Building2} title="No laboratories found" description="Try a different city or lab name." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {labs.map((lab) => (
            <Card key={lab.id} className="p-5">
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent-50 text-accent-600">
                  <Building2 size={16} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">{lab.name}</h3>
                  <div className="mt-1 flex items-center gap-1.5 text-sm text-slate-500">
                    <MapPin size={13} />
                    {lab.city}, {lab.state}
                  </div>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {lab.accreditations.map((acc) => (
                  <Badge key={acc} tone="brand">
                    {acc}
                  </Badge>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {lab.testCategories.map((cat) => (
                  <span key={cat} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-600">
                    {cat}
                  </span>
                ))}
              </div>
              <div className="mt-4 flex items-center gap-1.5 border-t border-slate-100 pt-3 text-xs text-slate-500">
                <Mail size={13} />
                {lab.contact}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
