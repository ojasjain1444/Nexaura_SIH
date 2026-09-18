import { FileText, RefreshCw, Trash2, Upload } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Badge, Button, Card, EmptyState, ErrorState, Spinner } from '../components/ui'
import { deleteDocument, listDocuments, reindexDocument, uploadDocument } from '../services/api'
import { DOCUMENT_TYPE_OPTIONS } from '../types'
import type { DocumentDisplayStatus, DocumentType, ManagedDocument } from '../types'

const STATUS_TONE: Record<DocumentDisplayStatus, 'success' | 'warning' | 'danger'> = {
  INDEXED: 'success',
  PROCESSING: 'warning',
  FAILED: 'danger',
}

const SOURCE_TYPE_TONE: Record<string, 'success' | 'neutral'> = {
  verified_bis: 'success',
}

const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = Object.fromEntries(
  DOCUMENT_TYPE_OPTIONS.map((opt) => [opt.value, opt.label]),
) as Record<DocumentType, string>

function StatusBadge({ status }: { status: DocumentDisplayStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{status}</Badge>
}

function SourceTypeBadge({ sourceType }: { sourceType: string }) {
  // Only an explicitly verified document may ever show as verified — every
  // other source_type (unverified/test/demo) reads as a plain neutral tag,
  // never implying official BIS status. See docs/DATABASE.md.
  return <Badge tone={SOURCE_TYPE_TONE[sourceType] ?? 'neutral'}>{sourceType}</Badge>
}

function DocumentTypeBadge({ documentType }: { documentType: DocumentType }) {
  return <Badge tone="brand">{DOCUMENT_TYPE_LABELS[documentType] ?? documentType}</Badge>
}

function DocumentRow({
  document,
  onReindex,
  onDelete,
  busy,
}: {
  document: ManagedDocument
  onReindex: (id: string) => void
  onDelete: (id: string) => void
  busy: boolean
}) {
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <FileText size={14} className="shrink-0 text-slate-400" />
            <span className="truncate text-sm font-semibold text-slate-900">{document.originalFilename}</span>
            <StatusBadge status={document.displayStatus} />
            <DocumentTypeBadge documentType={document.documentType} />
            <SourceTypeBadge sourceType={document.sourceType} />
          </div>

          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs text-slate-500 sm:grid-cols-4">
            <div>
              <dt className="text-slate-400">Standard number</dt>
              <dd className="text-slate-700">{document.extractedStandardNumber ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-slate-400">Edition</dt>
              <dd className="text-slate-700">{document.extractedEdition ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-slate-400">Publication year</dt>
              <dd className="text-slate-700">{document.extractedPublicationYear ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-slate-400">Pages</dt>
              <dd className="text-slate-700">{document.pageCount ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-slate-400">Chunks indexed</dt>
              <dd className="text-slate-700">{document.chunkCount}</dd>
            </div>
            <div>
              <dt className="text-slate-400">Linked standard</dt>
              <dd className="text-slate-700">{document.standardId ?? 'Not linked'}</dd>
            </div>
            <div className="col-span-2">
              <dt className="text-slate-400">Uploaded</dt>
              <dd className="text-slate-700">{new Date(document.ingestedAt).toLocaleString()}</dd>
            </div>
          </dl>
          {document.extractedTitle && <p className="mt-2 text-xs text-slate-500">{document.extractedTitle}</p>}
        </div>

        <div className="flex shrink-0 gap-2 sm:flex-col">
          <Button variant="secondary" size="sm" onClick={() => onReindex(document.id)} disabled={busy}>
            <RefreshCw size={13} /> Re-index
          </Button>
          <Button variant="danger" size="sm" onClick={() => onDelete(document.id)} disabled={busy}>
            <Trash2 size={13} /> Delete
          </Button>
        </div>
      </div>
    </Card>
  )
}

export function DocumentManagerPage() {
  const [documents, setDocuments] = useState<ManagedDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [selectedDocumentType, setSelectedDocumentType] = useState<DocumentType>('OTHER')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const refresh = useCallback(() => {
    setError(false)
    return listDocuments()
      .then(setDocuments)
      .catch(() => setError(true))
  }, [])

  useEffect(() => {
    setLoading(true)
    refresh().finally(() => setLoading(false))
  }, [refresh])

  // While any document is still processing/indexing in the background,
  // poll so status transitions (PROCESSING -> INDEXED/FAILED) show up
  // without the user having to click refresh manually.
  useEffect(() => {
    const hasPending = documents.some((d) => d.displayStatus === 'PROCESSING')
    if (!hasPending) return
    const timer = setInterval(() => refresh(), 3000)
    return () => clearInterval(timer)
  }, [documents, refresh])

  const handleFileSelected = async (file: File | undefined) => {
    if (!file) return
    setUploading(true)
    setUploadError(null)
    try {
      await uploadDocument(file, selectedDocumentType)
      await refresh()
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed.')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleReindex = async (id: string) => {
    setBusyId(id)
    try {
      await reindexDocument(id)
      await refresh()
    } catch {
      setError(false) // list itself is still fine; the row's own state is unaffected by this failure
      setUploadError('Re-indexing failed. Please try again.')
    } finally {
      setBusyId(null)
    }
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm('Delete this document? This removes it and its indexed chunks permanently.')) return
    setBusyId(id)
    try {
      await deleteDocument(id)
      await refresh()
    } catch {
      setUploadError('Delete failed. Please try again.')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-50 text-accent-600">
          <FileText size={18} />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Document Manager</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Upload PDFs for the assistant to retrieve from. Processing and indexing run locally.
          </p>
        </div>
      </div>

      <Card className="p-5">
        <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Upload a PDF</h2>
            <p className="mt-1 text-xs text-slate-500">
              Only PDF files are accepted. A duplicate of an already-uploaded file is detected automatically.
            </p>
          </div>
          <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">
            <select
              value={selectedDocumentType}
              onChange={(e) => setSelectedDocumentType(e.target.value as DocumentType)}
              aria-label="Document type"
              className="rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-700 focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/20"
            >
              {DOCUMENT_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(e) => handleFileSelected(e.target.files?.[0])}
            />
            <Button size="sm" onClick={() => fileInputRef.current?.click()} isLoading={uploading}>
              <Upload size={14} /> {uploading ? 'Uploading…' : 'Upload PDF'}
            </Button>
          </div>
        </div>
        {uploadError && <p className="mt-3 text-xs text-red-600">{uploadError}</p>}
      </Card>

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">Documents</h2>
        <Button variant="ghost" size="sm" onClick={() => refresh()}>
          <RefreshCw size={13} /> Refresh
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner size={28} />
        </div>
      ) : error ? (
        <ErrorState onRetry={refresh} />
      ) : documents.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Upload a PDF above to make it retrievable by the assistant."
        />
      ) : (
        <div className="space-y-3">
          {documents.map((document) => (
            <DocumentRow
              key={document.id}
              document={document}
              onReindex={handleReindex}
              onDelete={handleDelete}
              busy={busyId === document.id}
            />
          ))}
        </div>
      )}
    </div>
  )
}
