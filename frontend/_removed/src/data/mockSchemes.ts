import type { CertificationScheme } from '../types'

/**
 * Placeholder catalog of BIS certification schemes for frontend demonstration.
 * In production this will be replaced by a live BIS scheme database (see services/api.ts).
 */
export const mockSchemes: CertificationScheme[] = [
  {
    id: 'scheme-1',
    name: 'Product Certification Scheme (ISI Mark)',
    type: 'product-certification',
    summary:
      'Voluntary and mandatory certification allowing manufacturers to use the ISI Mark, certifying that products conform to relevant Indian Standards.',
    eligibility: [
      'Manufacturing unit with in-house or accredited testing facility',
      'Product covered under an existing Indian Standard',
      'Compliance with quality control requirements specified in the scheme',
    ],
    steps: [
      { order: 1, title: 'Application Submission', description: 'Submit application with product and factory details via the BIS portal.' },
      { order: 2, title: 'Factory Evaluation', description: 'BIS officers conduct an on-site audit of manufacturing and testing facilities.' },
      { order: 3, title: 'Sample Testing', description: 'Product samples are tested against the applicable Indian Standard.' },
      { order: 4, title: 'Grant of License', description: 'On satisfactory evaluation, BIS grants the license to use the Standard Mark.' },
    ],
    averageDurationDays: 90,
    fees: '₹1,000 application fee + testing and marking fees as per scheme',
  },
  {
    id: 'scheme-2',
    name: 'Hallmarking Scheme for Gold Jewellery',
    type: 'hallmarking',
    summary:
      'Certification scheme ensuring gold jewellery and artefacts meet declared purity standards through registered Assaying & Hallmarking Centres.',
    eligibility: [
      'Jewellers registered under the BIS Hallmarking Scheme',
      'Products conforming to permitted fineness grades (e.g. 22K916, 18K750, 14K585)',
    ],
    steps: [
      { order: 1, title: 'Jeweller Registration', description: 'Register as a BIS-recognized jeweller via the online portal.' },
      { order: 2, title: 'Submit to AHC', description: 'Submit jewellery items to a registered Assaying & Hallmarking Centre.' },
      { order: 3, title: 'Purity Testing', description: 'AHC tests fineness/purity using approved methods.' },
      { order: 4, title: 'Hallmark Application', description: 'Approved items receive the BIS hallmark with unique HUID.' },
    ],
    averageDurationDays: 3,
    fees: 'Nominal per-piece hallmarking charge as notified by BIS',
  },
  {
    id: 'scheme-3',
    name: 'Compulsory Registration Scheme (CRS)',
    type: 'product-certification',
    summary:
      'Applicable to electronics and IT products notified under the Electronics and IT Goods (Requirements for Compulsory Registration) Order, ensuring safety compliance before sale in India.',
    eligibility: [
      'Product listed under the notified CRS product list',
      'Testing conducted at a BIS-recognized laboratory',
    ],
    steps: [
      { order: 1, title: 'Lab Testing', description: 'Get the product tested at a BIS-recognized lab against the applicable safety standard.' },
      { order: 2, title: 'Online Registration', description: 'Submit test reports and product details on the CRS portal.' },
      { order: 3, title: 'Registration Grant', description: 'BIS reviews and grants registration allowing legal sale of the product.' },
    ],
    averageDurationDays: 30,
    fees: 'Registration fee per model as per CRS fee schedule',
  },
  {
    id: 'scheme-4',
    name: 'Management System Certification',
    type: 'management-system',
    summary:
      'Certification of Quality (ISO 9001), Environmental (ISO 14001), and other management systems for organizations seeking process-level conformity recognition.',
    eligibility: [
      'Documented management system in operation for a minimum period',
      'Internal audits and management review completed',
    ],
    steps: [
      { order: 1, title: 'Application & Documentation Review', description: 'Submit application along with the management system manual and records.' },
      { order: 2, title: 'Stage 1 Audit', description: 'BIS assessors review documentation and readiness for certification audit.' },
      { order: 3, title: 'Stage 2 Audit', description: 'On-site audit verifying implementation and effectiveness of the management system.' },
      { order: 4, title: 'Certification Decision', description: 'Certificate issued upon successful closure of non-conformities, if any.' },
    ],
    averageDurationDays: 60,
    fees: 'As per man-day audit charges based on organization size',
  },
]
