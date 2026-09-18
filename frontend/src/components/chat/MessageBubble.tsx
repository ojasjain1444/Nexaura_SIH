import { Bot, User } from 'lucide-react'
import type { ChatMessage } from '../../types'
import { SourceCitationList } from './SourceCitationList'

interface MessageBubbleProps {
  message: ChatMessage
  onQuickReply?: (text: string) => void
}

export function MessageBubble({ message, onQuickReply }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const time = new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
          isUser ? 'bg-slate-700 text-white' : 'bg-accent-600 text-white'
        }`}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>
      <div className={`flex max-w-[85%] flex-col sm:max-w-[70%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? 'rounded-tr-sm bg-accent-600 text-white'
              : 'rounded-tl-sm border border-slate-200 bg-white text-slate-700'
          }`}
        >
          <p className="whitespace-pre-wrap">{message.content}</p>
          {!isUser && message.sources && <SourceCitationList sources={message.sources} />}
        </div>
        <span className="mt-1 px-1 text-[11px] text-slate-500">{time}</span>

        {!isUser && message.quickReplies && message.quickReplies.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {message.quickReplies.map((reply) => (
              <button
                key={reply}
                onClick={() => onQuickReply?.(reply)}
                className="rounded-full border border-accent-200 bg-accent-50 px-3 py-1.5 text-xs font-medium text-accent-700 hover:bg-accent-100"
              >
                {reply}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
