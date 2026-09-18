import { useCallback, useState } from 'react'
import { sendChatMessage } from '../services/api'
import type { ChatMessage, Language, MessageStatus } from '../types'

function createUserMessage(content: string): ChatMessage {
  return {
    id: `user-${Date.now()}`,
    role: 'user',
    content,
    timestamp: new Date().toISOString(),
  }
}

// The chat backend deliberately supports a smaller language set than the
// language preference selector overall (see docs/CHAT_RAG.md — Phase 6 is
// intentionally limited to English + Hindi). Any other preference falls
// back to the backend's English default here rather than surfacing a
// validation error to the user.
const CHAT_SUPPORTED_LANGUAGES = new Set<Language>(['en', 'hi'])

export function useChat(language?: Language) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [status, setStatus] = useState<MessageStatus>('idle')
  const [conversationId, setConversationId] = useState<string | undefined>(undefined)
  // Phase 10: once a conversation enters product-discovery mode, the
  // backend keeps it in that mode for every later turn on its own (it
  // looks up the conversation's ProductProfile) — this only needs to be
  // sent once, on the message that starts discovery mode.
  const [discoveryStarted, setDiscoveryStarted] = useState(false)

  const chatLanguage = language && CHAT_SUPPORTED_LANGUAGES.has(language) ? language : undefined

  const sendMessage = useCallback(
    async (text: string, options?: { startProductDiscovery?: boolean }) => {
      const trimmed = text.trim()
      if (!trimmed) return

      const userMessage = createUserMessage(trimmed)
      setMessages((prev) => [...prev, userMessage])
      setStatus('thinking')

      const startDiscovery = options?.startProductDiscovery ?? false
      const mode = startDiscovery && !discoveryStarted ? 'product_discovery' : undefined

      try {
        const result = await sendChatMessage(trimmed, conversationId, undefined, chatLanguage, mode)
        setConversationId(result.conversationId)
        setMessages((prev) => [...prev, result.message])
        setStatus('idle')
        if (mode) setDiscoveryStarted(true)
      } catch {
        setStatus('error')
      }
    },
    [conversationId, chatLanguage, discoveryStarted],
  )

  const reset = useCallback(() => {
    setMessages([])
    setStatus('idle')
    setConversationId(undefined)
    setDiscoveryStarted(false)
  }, [])

  return { messages, status, sendMessage, reset, conversationId }
}
