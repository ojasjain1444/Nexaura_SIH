export type StandardStatus = 'active' | 'under-revision' | 'withdrawn'

export interface IndianStandard {
  id: string
  code: string
  title: string
  category: string
  description: string
  status: StandardStatus
  lastAmended: string
  sector: string
  relatedCodes: string[]
}

export type SchemeType = 'product-certification' | 'hallmarking' | 'management-system' | 'foreign-manufacturers'

export interface CertificationScheme {
  id: string
  name: string
  type: SchemeType
  summary: string
  eligibility: string[]
  steps: CertificationStep[]
  averageDurationDays: number
  fees: string
}

export interface CertificationStep {
  order: number
  title: string
  description: string
}

export type LabAccreditation = 'NABL' | 'BIS-Recognized' | 'ISO-17025'

export interface TestingLab {
  id: string
  name: string
  city: string
  state: string
  accreditations: LabAccreditation[]
  testCategories: string[]
  contact: string
  distanceKm?: number
}
