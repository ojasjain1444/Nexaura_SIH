export type ChatRole = 'user' | 'assistant'

export interface SourceCitation {
  id: string
  standardCode: string
  title: string
  clause?: string
  url?: string
}

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  timestamp: string
  sources?: SourceCitation[]
  quickReplies?: string[]
}

export interface ChatSession {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  messages: ChatMessage[]
}

export type MessageStatus = 'idle' | 'sending' | 'thinking' | 'error'

export type Language = 'en' | 'hi' | 'bn' | 'ta' | 'te' | 'mr' | 'gu' | 'kn'
