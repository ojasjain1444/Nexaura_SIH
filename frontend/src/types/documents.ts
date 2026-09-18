export type DocumentDisplayStatus = 'PROCESSING' | 'INDEXED' | 'FAILED'

// Phase 12: what KIND of BIS material a document is — kept separate from
// sourceType, which answers whether authenticity has been verified.
export type DocumentType =
  | 'INDIAN_STANDARD'
  | 'REGULATORY_ORDER'
  | 'QCO'
  | 'BIS_SCHEME'
  | 'PRODUCT_MANUAL'
  | 'TESTING_GUIDANCE'
  | 'CERTIFICATION_GUIDANCE'
  | 'OTHER'

export const DOCUMENT_TYPE_OPTIONS: { value: DocumentType; label: string }[] = [
  { value: 'INDIAN_STANDARD', label: 'Indian Standard' },
  { value: 'REGULATORY_ORDER', label: 'Regulatory Order' },
  { value: 'QCO', label: 'Quality Control Order (QCO)' },
  { value: 'BIS_SCHEME', label: 'BIS Certification Scheme' },
  { value: 'PRODUCT_MANUAL', label: 'Product Manual' },
  { value: 'TESTING_GUIDANCE', label: 'Testing Guidance' },
  { value: 'CERTIFICATION_GUIDANCE', label: 'Certification Guidance' },
  { value: 'OTHER', label: 'Other' },
]

export interface ManagedDocument {
  id: string
  originalFilename: string
  status: string
  displayStatus: DocumentDisplayStatus
  pageCount: number | null
  sourceType: string
  documentType: DocumentType
  source: string | null
  sourceUrl: string | null
  acquisitionDate: string | null
  standardId: string | null
  extractedStandardNumber: string | null
  extractedTitle: string | null
  extractedEdition: string | null
  extractedPublicationYear: string | null
  chunkCount: number
  fileHash: string
  ingestedAt: string
}
