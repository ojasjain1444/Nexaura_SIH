/**
 * Service layer boundary between the UI and data.
 *
 * Backend status (Phase 5 — grounded chat + RAG answer generation):
 * standards, labs, certification schemes, conversation history, chat
 * persistence, and language preference are backed by a real FastAPI +
 * SQLAlchemy backend (see /backend). Chat now performs real retrieval
 * (POST /api/rag/retrieve internally) and, when an LLM provider is
 * configured server-side, real grounded generation with citations derived
 * from actual retrieved evidence — never invented. If no LLM provider is
 * configured, the backend returns a structured LLM_NOT_CONFIGURED error
 * (mapped to a thrown Error here) rather than a fabricated answer.
 *
 * Implemented against the real backend:
 *   GET  /api/health                -> checkBackendHealth()
 *   GET  /api/standards              -> searchStandards()
 *   GET  /api/standards/:id          -> getStandardById()
 *   GET  /api/certification          -> listSchemes()
 *   GET  /api/certification/:id      -> getSchemeById()
 *   GET  /api/labs                   -> searchLabs()
 *   GET  /api/history                -> getHistory()
 *   GET  /api/history/:id            -> getHistoryById()
 *   DELETE /api/history/:id          -> deleteHistoryItem()
 *   POST /api/chat                   -> sendChatMessage() (real retrieval + LLM when configured)
 *   GET  /api/preferences            -> getPreferences()
 *   PUT  /api/preferences            -> updatePreferences()
 *
 * Phase 6 adds response-language selection to sendChatMessage() (English
 * and Hindi supported; retrieval always runs against the original document
 * text regardless of the requested response language).
 *
 * Phase 9 adds local document management:
 *   GET    /api/documents            -> listDocuments()
 *   POST   /api/documents/upload     -> uploadDocument()
 *   POST   /api/documents/:id/reindex -> reindexDocument()
 *   DELETE /api/documents/:id        -> deleteDocument()
 * Uploading a document runs the existing Phase 3/8 ingestion pipeline and
 * Phase 4 indexing entirely server-side and locally (no cloud/paid
 * service) — once a document's displayStatus is "INDEXED" the assistant
 * can retrieve from it like any other document.
 *
 * Phase 12 adds an optional documentType to uploadDocument() — a
 * user-asserted classification (Indian Standard, QCO, BIS Scheme, etc.,
 * see src/types/documents.ts's DOCUMENT_TYPE_OPTIONS) of what KIND of BIS
 * material the file is. Never inferred by the backend; defaults to
 * "OTHER" when omitted. Kept separate from sourceType (unverified/test/
 * demo/verified_bis), which answers whether authenticity has been
 * verified.
 *
 * Phase 10 adds an optional product-discovery mode to sendChatMessage():
 * passing mode="product_discovery" on a conversation's first message makes
 * the backend build a structured ProductProfile from the conversation and
 * ask clarification questions before proposing candidate standards — see
 * app/product/ in the backend. Clarification questions are surfaced as
 * ChatMessage.quickReplies (reusing the existing clickable-question
 * mechanism); the detected product profile and candidate standards are
 * appended to the message content as readable text for this phase (no new
 * UI component yet — see docs/IMPLEMENTATION_ROADMAP.md).
 *
 * Still not implemented on the backend (see docs/IMPLEMENTATION_ROADMAP.md):
 * voice, external BIS integrations.
 */
import type {
  ChatMessage,
  ChatSession,
  CertificationScheme,
  IndianStandard,
  Language,
  ManagedDocument,
  SourceCitation,
  TestingLab,
} from '../types'

// Backend base URL. VITE_API_BASE_URL in a .env file overrides this
// explicitly when set. Otherwise, it's derived from whatever hostname the
// page itself was loaded from (window.location.hostname), not hardcoded
// to "localhost" — confirmed necessary the hard way: a hardcoded
// .env value of the Mac's LAN IP (needed for the phone/Expo WebView to
// reach the backend) broke registration/login for anyone opening the app
// via "localhost" on the same machine, since the browser then tried to
// reach that LAN IP directly and got ERR_ADDRESS_UNREACHABLE. Deriving
// from the current page's own hostname means the exact same build works
// correctly whether opened as localhost:5173 or <LAN IP>:5173, with no
// per-environment .env editing required.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  (typeof window !== 'undefined' ? `http://${window.location.hostname}:8000` : 'http://localhost:8000')

export interface BackendHealth {
  status: string
  service: string
  environment: string
}

interface ApiErrorBody {
  error?: { code?: string; message?: string }
}

// Demo-grade auth (see backend app/models/user.py's module docstring —
// this is a short numeric PIN, not real account security). The token is
// kept in localStorage, read fresh on every request rather than cached in
// a module variable, so logging in/out in one tab takes effect on the
// very next request without needing a page reload.
const AUTH_TOKEN_STORAGE_KEY = 'bis-sahayak-auth-token'

export function getStoredAuthToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)
}

export function setStoredAuthToken(token: string | null): void {
  if (typeof window === 'undefined') return
  if (token) window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token)
  else window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`
  const token = getStoredAuthToken()
  const response = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  })
  if (!response.ok) {
    let message = `Request to ${path} failed with status ${response.status}`
    try {
      const body: ApiErrorBody = await response.json()
      if (body?.error?.message) message = body.error.message
    } catch {
      // response body wasn't JSON — keep the generic message
    }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

/**
 * Calls the real backend's GET /api/health. Useful for confirming the
 * backend is reachable during local development.
 */
export async function checkBackendHealth(): Promise<BackendHealth> {
  return request<BackendHealth>('/api/health')
}

export interface StandardsQuery {
  search?: string
  category?: string
  status?: IndianStandard['status']
}

export async function searchStandards(query: StandardsQuery = {}): Promise<IndianStandard[]> {
  const params = new URLSearchParams()
  if (query.search) params.set('search', query.search)
  if (query.category) params.set('category', query.category)
  if (query.status) params.set('status', query.status)
  const qs = params.toString()
  const path = qs ? `/api/standards?${qs}` : '/api/standards'
  return request<IndianStandard[]>(path)
}

export async function getStandardById(id: string): Promise<IndianStandard | undefined> {
  try {
    return await request<IndianStandard>(`/api/standards/${id}`)
  } catch {
    return undefined
  }
}

export async function listSchemes(): Promise<CertificationScheme[]> {
  return request<CertificationScheme[]>('/api/certification')
}

export async function getSchemeById(id: string): Promise<CertificationScheme | undefined> {
  try {
    return await request<CertificationScheme>(`/api/certification/${id}`)
  } catch {
    return undefined
  }
}

export interface LabsQuery {
  search?: string
  city?: string
  category?: string
}

export async function searchLabs(query: LabsQuery = {}): Promise<TestingLab[]> {
  const params = new URLSearchParams()
  if (query.search) params.set('search', query.search)
  if (query.city) params.set('city', query.city)
  if (query.category) params.set('category', query.category)
  const qs = params.toString()
  const path = qs ? `/api/labs?${qs}` : '/api/labs'
  return request<TestingLab[]>(path)
}

export async function getHistory(): Promise<ChatSession[]> {
  const summaries = await request<{ id: string; title: string; createdAt: string; updatedAt: string }[]>(
    '/api/history',
  )
  // History list intentionally omits messages (matches backend's summary
  // response) — callers that need the transcript should call getHistoryById.
  return summaries.map((s) => ({ ...s, messages: [] }))
}

interface BackendConversationDetail {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  messages: BackendMessage[]
}

export async function getHistoryById(id: string): Promise<ChatSession | undefined> {
  try {
    const detail = await request<BackendConversationDetail>(`/api/history/${id}`)
    return { ...detail, messages: detail.messages.map((m) => toChatMessage(m)) }
  } catch {
    return undefined
  }
}

export async function deleteHistoryItem(id: string): Promise<void> {
  await request<void>(`/api/history/${id}`, { method: 'DELETE' })
}

export interface SendChatMessageResult {
  conversationId: string
  message: ChatMessage
}

interface BackendCitation {
  documentId: string
  documentName: string
  pageNumber: number
  section: string | null
  chunkId: string
}

interface BackendMessage {
  id: string
  role: ChatMessage['role']
  content: string
  timestamp: string
  citations: BackendCitation[]
}

interface BackendProductProfile {
  productName: string | null
  productCategory: string | null
  productType: string | null
  intendedUse: string | null
  targetMarket: string | null
  manufacturingLocation: string | null
  electricalCharacteristics: string | null
  capacity: string | null
  materials: string | null
  technology: string | null
  application: string | null
  otherAttributes: string | null
}

interface BackendCandidateStandard {
  document_name: string
  applicability_status: string
  applicability_reason: string
}

interface BackendComplianceRequirement {
  title: string
  description: string
  category: string
  status: string
  regulatory_status: string
}

interface BackendComplianceChecklist {
  items: BackendComplianceRequirement[]
  open_questions: string[]
}

interface BackendChatResponse {
  conversationId: string
  message: BackendMessage
  productProfile: BackendProductProfile | null
  clarificationQuestions: string[]
  candidateStandards: BackendCandidateStandard[]
  complianceChecklist: BackendComplianceChecklist | null
}

const PROFILE_FIELD_LABELS: [keyof BackendProductProfile, string][] = [
  ['productName', 'Product name'],
  ['productCategory', 'Category'],
  ['productType', 'Type'],
  ['intendedUse', 'Intended use'],
  ['targetMarket', 'Target market'],
  ['manufacturingLocation', 'Manufacturing location'],
  ['electricalCharacteristics', 'Electrical characteristics'],
  ['capacity', 'Capacity'],
  ['materials', 'Materials'],
  ['technology', 'Technology'],
  ['application', 'Application'],
  ['otherAttributes', 'Other details'],
]

const REQUIREMENT_CATEGORY_LABELS: Record<string, string> = {
  TESTING: 'Testing',
  DOCUMENTATION: 'Documentation',
  CERTIFICATION: 'Certification',
  CONFORMITY_ASSESSMENT: 'Conformity assessment',
  MARKING: 'Marking',
  MANUFACTURING_QUALITY: 'Manufacturing quality',
  OTHER: 'Other',
}

/**
 * Formats the Phase 10/11 product-discovery fields (profile, candidate
 * standards, and — once enough is known — the evidence-backed compliance
 * checklist) as readable plain text appended below the LLM's own reply.
 * ChatMessage.content renders as plain, non-markdown text
 * (whitespace-pre-wrap — see MessageBubble.tsx), so this uses simple
 * indentation and a heading per section rather than markdown syntax, to
 * visually separate Product Profile / Candidate Standards / Testing /
 * Documentation / Certification / Open Questions as distinct sections
 * within the one message. A dedicated structured UI is left to a later
 * phase — see docs/IMPLEMENTATION_ROADMAP.md.
 */
function formatDiscoveryAppendix(
  profile: BackendProductProfile | null,
  candidates: BackendCandidateStandard[],
  checklist: BackendComplianceChecklist | null,
): string {
  const sections: string[] = []

  if (profile) {
    const knownFields = PROFILE_FIELD_LABELS.filter(([key]) => profile[key])
    if (knownFields.length > 0) {
      const lines = knownFields.map(([key, label]) => `  ${label}: ${profile[key]}`)
      sections.push(['Product profile so far:', ...lines].join('\n'))
    }
  }

  if (candidates.length > 0) {
    const lines = candidates.map(
      (c) => `  - ${c.document_name} — ${c.applicability_status.replaceAll('_', ' ')}: ${c.applicability_reason}`,
    )
    sections.push(['Candidate standards:', ...lines].join('\n'))
  }

  if (checklist) {
    const itemsByCategory = new Map<string, BackendComplianceRequirement[]>()
    for (const item of checklist.items) {
      const existing = itemsByCategory.get(item.category) ?? []
      existing.push(item)
      itemsByCategory.set(item.category, existing)
    }

    if (itemsByCategory.size > 0) {
      for (const [category, items] of itemsByCategory) {
        const label = REQUIREMENT_CATEGORY_LABELS[category] ?? category
        const lines = items.map((item) => `  ☐ ${item.title} (${item.status.replaceAll('_', ' ')})`)
        sections.push([`${label}:`, ...lines].join('\n'))
      }
      sections.push(
        '  Note: mandatory/regulatory status could not be determined from available evidence for any of the above.',
      )
    }

    if (checklist.open_questions.length > 0) {
      sections.push(['Open questions:', ...checklist.open_questions.map((q) => `  - ${q}`)].join('\n'))
    }
  }

  return sections.join('\n\n')
}

/**
 * Maps a backend citation (document/page/section/chunk — real retrieval
 * metadata) onto the existing frontend SourceCitation shape
 * (standardCode/title/clause) so SourceCitationList renders it without any
 * component changes. SourceCitationList renders "{standardCode} — {title}
 * ({clause})", so `standardCode` carries the filename and `title` carries
 * page/section detail — the backend does not yet resolve a document back
 * to a catalogued Standard's `code` (that link is optional and often
 * unset — see StandardDocument.standard_id in the backend), so there is no
 * separate standard code to show alongside the filename.
 */
function toSourceCitation(citation: BackendCitation): SourceCitation {
  const title = citation.section ? `Page ${citation.pageNumber}, Section ${citation.section}` : `Page ${citation.pageNumber}`
  return {
    id: citation.chunkId,
    standardCode: citation.documentName,
    title,
  }
}

function toChatMessage(
  message: BackendMessage,
  productProfile: BackendProductProfile | null = null,
  clarificationQuestions: string[] = [],
  candidateStandards: BackendCandidateStandard[] = [],
  complianceChecklist: BackendComplianceChecklist | null = null,
): ChatMessage {
  const appendix = formatDiscoveryAppendix(productProfile, candidateStandards, complianceChecklist)
  return {
    id: message.id,
    role: message.role,
    content: appendix ? `${message.content}\n\n${appendix}` : message.content,
    timestamp: message.timestamp,
    sources: message.citations.length > 0 ? message.citations.map(toSourceCitation) : undefined,
    quickReplies: clarificationQuestions.length > 0 ? clarificationQuestions : undefined,
  }
}

/**
 * Sends a message to the real backend chat endpoint. The backend performs
 * real retrieval and, when an LLM provider is configured server-side,
 * real grounded generation with citations from actual retrieved evidence.
 * If no LLM provider is configured, or generation fails, this throws —
 * callers (see useChat) must not fall back to a fabricated response. Pass
 * the returned conversationId back in on the next call to continue the
 * same conversation; pass standardId to scope retrieval to documents
 * linked to a specific catalogued Standard.
 */
export async function sendChatMessage(
  userText: string,
  conversationId?: string,
  standardId?: string,
  language?: Language,
  mode?: 'product_discovery',
): Promise<SendChatMessageResult> {
  const response = await request<BackendChatResponse>('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ message: userText, conversationId, standardId, language, mode }),
  })
  return {
    conversationId: response.conversationId,
    message: toChatMessage(
      response.message,
      response.productProfile,
      response.clarificationQuestions,
      response.candidateStandards,
      response.complianceChecklist,
    ),
  }
}

export interface Preferences {
  language: Language
}

export async function getPreferences(): Promise<Preferences> {
  return request<Preferences>('/api/preferences')
}

export async function updatePreferences(language: Language): Promise<Preferences> {
  return request<Preferences>('/api/preferences', { method: 'PUT', body: JSON.stringify({ language }) })
}

interface BackendDocument {
  id: string
  original_filename: string
  status: string
  display_status: string
  page_count: number | null
  source_type: string
  document_type: string
  source: string | null
  source_url: string | null
  acquisition_date: string | null
  standard_id: string | null
  extracted_standard_number: string | null
  extracted_title: string | null
  extracted_edition: string | null
  extracted_publication_year: string | null
  chunk_count: number
  file_hash: string
  ingested_at: string
}

function toManagedDocument(doc: BackendDocument): ManagedDocument {
  return {
    id: doc.id,
    originalFilename: doc.original_filename,
    status: doc.status,
    displayStatus: doc.display_status as ManagedDocument['displayStatus'],
    pageCount: doc.page_count,
    sourceType: doc.source_type,
    documentType: doc.document_type as ManagedDocument['documentType'],
    source: doc.source,
    sourceUrl: doc.source_url,
    acquisitionDate: doc.acquisition_date,
    standardId: doc.standard_id,
    extractedStandardNumber: doc.extracted_standard_number,
    extractedTitle: doc.extracted_title,
    extractedEdition: doc.extracted_edition,
    extractedPublicationYear: doc.extracted_publication_year,
    chunkCount: doc.chunk_count,
    fileHash: doc.file_hash,
    ingestedAt: doc.ingested_at,
  }
}

/**
 * Lists all locally ingested documents, newest first. Used by the Document
 * Manager page — see src/pages/DocumentManagerPage.tsx.
 */
export async function listDocuments(): Promise<ManagedDocument[]> {
  const documents = await request<BackendDocument[]>('/api/documents')
  return documents.map(toManagedDocument)
}

/**
 * Uploads a PDF to the local backend. The backend validates it, registers
 * it, then runs the existing ingestion pipeline and local embedding
 * indexing in the background — the returned document's displayStatus is
 * typically "PROCESSING" immediately after this resolves; poll
 * listDocuments()/getDocumentStatus() to see it become "INDEXED".
 *
 * Uses fetch directly (not the shared `request` helper) because a file
 * upload needs a raw FormData body with a browser-generated multipart
 * boundary — setting Content-Type manually would break it.
 */
export async function uploadDocument(file: File, documentType?: string): Promise<ManagedDocument> {
  const formData = new FormData()
  formData.append('file', file)
  if (documentType) formData.append('document_type', documentType)
  const response = await fetch(`${API_BASE_URL}/api/documents/upload`, { method: 'POST', body: formData })
  if (!response.ok) {
    let message = `Upload failed with status ${response.status}`
    try {
      const body: ApiErrorBody = await response.json()
      if (body?.error?.message) message = body.error.message
    } catch {
      // response body wasn't JSON — keep the generic message
    }
    throw new Error(message)
  }
  return toManagedDocument(await response.json())
}

export async function getDocumentStatus(id: string): Promise<{ status: string; errorMessage: string | null }> {
  const result = await request<{ status: string; error_message: string | null }>(`/api/documents/${id}/status`)
  return { status: result.status, errorMessage: result.error_message }
}

export async function reindexDocument(id: string): Promise<ManagedDocument> {
  const result = await request<BackendDocument>(`/api/documents/${id}/reindex`, { method: 'POST' })
  return toManagedDocument(result)
}

export async function deleteDocument(id: string): Promise<void> {
  await request<void>(`/api/documents/${id}`, { method: 'DELETE' })
}

// --- Auth (demo-grade username + 2-digit-PIN accounts; see backend
// app/models/user.py's module docstring — this is not real account
// security, just enough to give each person their own saved history) ---

export interface AuthUser {
  id: string
  username: string
}

interface BackendLoginResponse {
  token: string
  user: AuthUser
}

export async function registerUser(username: string, pin: string): Promise<BackendLoginResponse> {
  return request<BackendLoginResponse>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, pin }),
  })
}

export async function loginUser(username: string, pin: string): Promise<BackendLoginResponse> {
  return request<BackendLoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, pin }),
  })
}

export async function logoutUser(): Promise<void> {
  await request<void>('/api/auth/logout', { method: 'POST' })
}

export async function getCurrentUser(): Promise<AuthUser> {
  return request<AuthUser>('/api/auth/me')
}
