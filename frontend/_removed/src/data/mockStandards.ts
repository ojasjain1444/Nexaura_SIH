import type { IndianStandard } from '../types'

/**
 * Placeholder catalog of Indian Standards for frontend demonstration.
 * In production this will be replaced by a live BIS knowledge-base query (see services/api.ts).
 */
export const mockStandards: IndianStandard[] = [
  {
    id: 'is-1',
    code: 'IS 302-1',
    title: 'Safety of Household and Similar Electrical Appliances, Part 1: General Requirements',
    category: 'Electrical Appliances',
    description:
      'Specifies general safety requirements for household and similar electrical appliances, covering protection against electric shock, mechanical hazards, and fire.',
    status: 'active',
    lastAmended: '2023-04-11',
    sector: 'Electronics & Electrical',
    relatedCodes: ['IS 302-2', 'IEC 60335-1'],
  },
  {
    id: 'is-2',
    code: 'IS 1786',
    title: 'High Strength Deformed Steel Bars and Wires for Concrete Reinforcement',
    category: 'Construction Materials',
    description:
      'Covers requirements for high strength deformed steel bars and wires used for reinforcement of concrete structures, including chemical composition and tensile properties.',
    status: 'active',
    lastAmended: '2022-08-02',
    sector: 'Construction & Infrastructure',
    relatedCodes: ['IS 432', 'IS 1139'],
  },
  {
    id: 'is-3',
    code: 'IS 15885',
    title: 'Hallmarking of Gold Jewellery and Artefacts',
    category: 'Precious Metals',
    description:
      'Specifies requirements for hallmarking of gold jewellery and artefacts, including fineness grades, marking symbols, and testing methods.',
    status: 'active',
    lastAmended: '2021-11-19',
    sector: 'Jewellery & Precious Metals',
    relatedCodes: ['IS 1417', 'IS 2790'],
  },
  {
    id: 'is-4',
    code: 'IS 16046',
    title: 'Face Masks for General Use — Specification',
    category: 'Personal Protective Equipment',
    description:
      'Specifies requirements, sampling and test methods for reusable and single-use face masks intended for general public use.',
    status: 'active',
    lastAmended: '2020-06-15',
    sector: 'Healthcare & Safety',
    relatedCodes: ['IS 9873'],
  },
  {
    id: 'is-5',
    code: 'IS 4905',
    title: 'Random Sampling and Randomization Methods',
    category: 'Quality Management',
    description:
      'Provides methods for random sampling and randomization to be applied during quality inspection and conformity assessment procedures.',
    status: 'under-revision',
    lastAmended: '2019-01-10',
    sector: 'Quality Management',
    relatedCodes: ['IS/ISO 2859-1'],
  },
  {
    id: 'is-6',
    code: 'IS 14625',
    title: 'Packaged Drinking Water (Other than Natural Mineral Water) — Specification',
    category: 'Food & Beverages',
    description:
      'Specifies quality, safety, and labelling requirements for packaged drinking water sold for human consumption.',
    status: 'active',
    lastAmended: '2023-02-28',
    sector: 'Food & Public Distribution',
    relatedCodes: ['IS 13428'],
  },
  {
    id: 'is-7',
    code: 'IS 13360',
    title: 'Plastics — Methods of Testing, Part 1: General Guidelines',
    category: 'Plastics & Polymers',
    description:
      'Lays down general guidelines and terminology for methods used to test plastic materials and products across all parts of this standard series.',
    status: 'active',
    lastAmended: '2020-09-05',
    sector: 'Manufacturing',
    relatedCodes: ['IS 13360-3'],
  },
  {
    id: 'is-8',
    code: 'IS 2062',
    title: 'Hot Rolled Medium and High Tensile Structural Steel — Specification',
    category: 'Metals & Alloys',
    description:
      'Covers requirements for hot rolled steel plates, strips, shapes and sections used in structural applications including welded, bolted, and riveted construction.',
    status: 'active',
    lastAmended: '2022-05-30',
    sector: 'Construction & Infrastructure',
    relatedCodes: ['IS 800'],
  },
]
