import { History, MessageSquareText } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { MessageBubble } from '../components/chat/MessageBubble'
import { Card, EmptyState, ErrorState, Spinner } from '../components/ui'
import { getHistory, getHistoryById } from '../services/api'
import type { ChatSession } from '../types'

function formatRelativeDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function HistoryPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [selected, setSelected] = useState<ChatSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)

  const loadHistory = () => {
    setLoading(true)
    setError(false)
    getHistory()
      .then((results) => {
        setSessions(results)
        setLoading(false)
      })
      .catch(() => {
        setError(true)
        setLoading(false)
      })
  }

  useEffect(() => {
    loadHistory()
  }, [])

  const handleSelect = (session: ChatSession) => {
    setDetailLoading(true)
    getHistoryById(session.id)
      .then((full) => {
        setSelected(full ?? session)
        setDetailLoading(false)
      })
      .catch(() => {
        setDetailLoading(false)
      })
  }

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size={28} />
      </div>
    )
  }

  if (error) {
    return <ErrorState onRetry={loadHistory} description="Could not load conversation history from the backend." />
  }

  if (sessions.length === 0) {
    return (
      <EmptyState
        icon={History}
        title="No conversation history yet"
        description="Your past conversations with the assistant will appear here."
        action={
          <Link to="/assistant" className="text-sm font-medium text-accent-600 hover:text-accent-700">
            Start a conversation &rarr;
          </Link>
        }
      />
    )
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-50 text-accent-600">
          <History size={18} />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Conversation History</h1>
          <p className="mt-0.5 text-sm text-slate-500">Review your previous questions and assistant responses.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
        <div className="space-y-2">
          {sessions.map((session) => (
            <button
              key={session.id}
              onClick={() => handleSelect(session)}
              className={`block w-full rounded-xl border p-3 text-left transition-all ${
                selected?.id === session.id
                  ? 'border-accent-300 bg-accent-50 shadow-[var(--shadow-xs)]'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-[var(--shadow-xs)]'
              }`}
            >
              <p className="truncate text-sm font-medium text-slate-800">{session.title}</p>
              <p className="mt-1 text-xs text-slate-500">{formatRelativeDate(session.updatedAt)}</p>
            </button>
          ))}
        </div>

        <Card className="min-h-[24rem] p-5 sm:p-6">
          {detailLoading ? (
            <div className="flex h-full items-center justify-center py-12">
              <Spinner size={24} />
            </div>
          ) : selected ? (
            <div className="space-y-5">
              {selected.messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}
              <div className="border-t border-slate-100 pt-4">
                <Link
                  to={`/assistant?q=${encodeURIComponent(selected.messages[0]?.content ?? '')}`}
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-accent-600 hover:text-accent-700"
                >
                  <MessageSquareText size={14} /> Continue this topic in Assistant
                </Link>
              </div>
            </div>
          ) : (
            <EmptyState icon={MessageSquareText} title="Select a conversation" />
          )}
        </Card>
      </div>
    </div>
  )
}
