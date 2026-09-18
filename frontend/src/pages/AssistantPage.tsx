import { ClipboardCheck, MessageSquareText, RotateCcw } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChatComposer } from '../components/chat/ChatComposer'
import { MessageBubble } from '../components/chat/MessageBubble'
import { ThinkingIndicator } from '../components/chat/ThinkingIndicator'
import { Button, ErrorState } from '../components/ui'
import { quickTopics } from '../data'
import { useChat } from '../hooks/useChat'
import { useLanguage } from '../hooks/useLanguage'

export function AssistantPage() {
  const { language } = useLanguage()
  const { messages, status, sendMessage, reset } = useChat(language)
  const [searchParams, setSearchParams] = useSearchParams()
  const scrollRef = useRef<HTMLDivElement>(null)
  const initialQueryHandled = useRef(false)

  useEffect(() => {
    const initialQuery = searchParams.get('q')
    if (initialQuery && !initialQueryHandled.current) {
      initialQueryHandled.current = true
      sendMessage(initialQuery)
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, sendMessage, setSearchParams])

  // Phase 10: starts the product-discovery flow — the backend recognizes
  // this conversation as product discovery from this first message onward
  // (see useChat's discoveryStarted tracking) without any further UI state
  // here. Reusing the plain chat composer/bubble; no dedicated workspace.
  const startProductDiscovery = (productDescription: string) =>
    sendMessage(productDescription, { startProductDiscovery: true })

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, status])

  const isEmpty = messages.length === 0

  return (
    <div className="chat-viewport mx-auto flex max-w-4xl flex-col overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[var(--shadow-md)]">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3.5 sm:px-5">
        <div className="flex min-w-0 items-center gap-2 text-[13.5px] font-semibold text-slate-800 sm:gap-2.5">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-50 text-accent-600">
            <MessageSquareText size={14} />
          </span>
          {/* Shortened on narrow phones (confirmed via a real 375px-wide
             screenshot: "BIS Sahayak Assistant" wrapped to two lines and
             pushed the header taller than intended) — the full name
             appears at sm: and above. */}
          <span className="truncate">
            <span className="sm:hidden">Assistant</span>
            <span className="hidden sm:inline">BIS Sahayak Assistant</span>
          </span>
        </div>
        <Button variant="ghost" size="sm" onClick={reset} disabled={isEmpty} className="shrink-0">
          <RotateCcw size={13} /> <span className="hidden sm:inline">New chat</span>
        </Button>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-5 overflow-y-auto px-4 py-6 sm:px-6">
        {isEmpty ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-500 to-accent-700 text-white shadow-[var(--shadow-md)]">
              <MessageSquareText size={24} />
            </div>
            <h2 className="text-[15px] font-semibold text-slate-900">How can I help today?</h2>
            <p className="mt-1 max-w-sm text-[13.5px] text-slate-500">
              Ask about Indian Standards, certification schemes, hallmarking, or testing labs.
            </p>
            <div className="mt-7 grid w-full max-w-lg grid-cols-1 gap-2.5 sm:grid-cols-2">
              {quickTopics.map((topic) => (
                <button
                  key={topic.id}
                  onClick={() => sendMessage(topic.samplePrompt)}
                  className="rounded-2xl border border-slate-200 px-3.5 py-3 text-left text-sm text-slate-600 transition-all hover:-translate-y-0.5 hover:border-accent-300 hover:bg-accent-50/50 hover:shadow-[var(--shadow-sm)]"
                >
                  <span className="block font-medium text-slate-800">{topic.label}</span>
                  <span className="mt-0.5 block text-[12.5px] text-slate-400">{topic.samplePrompt}</span>
                </button>
              ))}
              <button
                onClick={() => startProductDiscovery('I want to launch a new product and need to understand BIS compliance requirements.')}
                className="rounded-2xl border border-accent-200 bg-accent-50/40 px-3.5 py-3 text-left text-sm text-slate-600 transition-all hover:-translate-y-0.5 hover:border-accent-300 hover:bg-accent-50 hover:shadow-[var(--shadow-sm)]"
              >
                <span className="flex items-center gap-1.5 font-medium text-slate-800">
                  <ClipboardCheck size={13} className="text-accent-600" /> Product compliance check
                </span>
                <span className="mt-0.5 block text-[12.5px] text-slate-400">
                  Describe a product to find relevant standards and requirements
                </span>
              </button>
            </div>
          </div>
        ) : (
          <>
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} onQuickReply={sendMessage} />
            ))}
            {status === 'thinking' && <ThinkingIndicator />}
            {status === 'error' && (
              <ErrorState
                title="Couldn't get a response"
                description="Something interrupted the assistant. Please try sending your question again."
                onRetry={() => messages.length > 0 && sendMessage(messages[messages.length - 1].content)}
              />
            )}
          </>
        )}
      </div>

      <ChatComposer onSend={sendMessage} disabled={status === 'thinking'} />
    </div>
  )
}
