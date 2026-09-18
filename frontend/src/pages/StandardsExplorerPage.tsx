import { BookMarked, FileText, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { StandardStatusBadge } from '../components/standards/StandardStatusBadge'
import { Card, EmptyState, ErrorState, Spinner } from '../components/ui'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { searchStandards } from '../services/api'
import type { IndianStandard } from '../types'

export function StandardsExplorerPage() {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<string>('all')
  const [standards, setStandards] = useState<IndianStandard[]>([])
  const [allCategories, setAllCategories] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const debouncedQuery = useDebouncedValue(query, 300)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)
    searchStandards({ search: debouncedQuery, category: category === 'all' ? undefined : category })
      .then((results) => {
        if (cancelled) return
        setStandards(results)
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
  }, [debouncedQuery, category])

  useEffect(() => {
    searchStandards()
      .then((all) => setAllCategories(Array.from(new Set(all.map((s) => s.category)))))
      .catch(() => {
        // Backend unreachable — leave categories empty; the search box and
        // "All categories" option remain usable without the filter list.
      })
  }, [])

  const categories = useMemo(() => ['all', ...allCategories], [allCategories])

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-50 text-accent-600">
          <BookMarked size={18} />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Standards Explorer</h1>
          <p className="mt-0.5 text-sm text-slate-500">Search and browse Indian Standards by keyword, code, or category.</p>
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by standard code, title, or keyword..."
            aria-label="Search standards"
            className="w-full rounded-xl border border-slate-200 py-2.5 pl-9 pr-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/20"
          />
        </div>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          aria-label="Filter by category"
          className="rounded-xl border border-slate-200 px-3 py-2.5 text-sm text-slate-700 focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/20"
        >
          {categories.map((c) => (
            <option key={c} value={c}>
              {c === 'all' ? 'All categories' : c}
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner size={28} />
        </div>
      ) : error ? (
        <ErrorState onRetry={() => setQuery((q) => q)} />
      ) : standards.length === 0 ? (
        <EmptyState
          icon={BookMarked}
          title="No standards found"
          description="Try a different keyword or clear the category filter."
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {standards.map((standard) => (
            <Link key={standard.id} to={`/standards/${standard.id}`}>
              <Card className="h-full p-5 transition-colors hover:border-accent-300">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <FileText size={14} className="text-slate-400" />
                    <span className="text-sm font-semibold text-accent-700">{standard.code}</span>
                  </div>
                  <StandardStatusBadge status={standard.status} />
                </div>
                <h3 className="mt-2 text-sm font-medium text-slate-900">{standard.title}</h3>
                <p className="mt-2 line-clamp-2 text-sm text-slate-500">{standard.description}</p>
                <p className="mt-3 text-xs text-slate-500">{standard.category}</p>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
