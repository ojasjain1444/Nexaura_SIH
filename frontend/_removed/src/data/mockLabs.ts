import type { TestingLab } from '../types'

/**
 * Placeholder directory of testing laboratories for frontend demonstration.
 * In production this will be replaced by the live BIS-recognized lab registry (see services/api.ts).
 */
export const mockLabs: TestingLab[] = [
  {
    id: 'lab-1',
    name: 'National Test House (Eastern Region)',
    city: 'Kolkata',
    state: 'West Bengal',
    accreditations: ['NABL', 'BIS-Recognized'],
    testCategories: ['Electrical Appliances', 'Textiles', 'Chemicals'],
    contact: 'nth-er@example.gov.in',
    distanceKm: 12,
  },
  {
    id: 'lab-2',
    name: 'Shriram Institute for Industrial Research',
    city: 'New Delhi',
    state: 'Delhi',
    accreditations: ['NABL', 'ISO-17025'],
    testCategories: ['Food & Beverages', 'Plastics & Polymers', 'Cosmetics'],
    contact: 'contact@shriraminstitute.example.org',
    distanceKm: 5,
  },
  {
    id: 'lab-3',
    name: 'Central Institute of Plastics Engineering & Technology (CIPET)',
    city: 'Chennai',
    state: 'Tamil Nadu',
    accreditations: ['BIS-Recognized', 'ISO-17025'],
    testCategories: ['Plastics & Polymers', 'Packaging'],
    contact: 'testing@cipet.example.gov.in',
    distanceKm: 30,
  },
  {
    id: 'lab-4',
    name: 'Electronics Regional Test Laboratory',
    city: 'Bengaluru',
    state: 'Karnataka',
    accreditations: ['NABL', 'BIS-Recognized'],
    testCategories: ['Electronics & Electrical', 'IT Equipment'],
    contact: 'ertl-blr@example.gov.in',
    distanceKm: 18,
  },
  {
    id: 'lab-5',
    name: 'Regional Assaying & Hallmarking Centre',
    city: 'Jaipur',
    state: 'Rajasthan',
    accreditations: ['BIS-Recognized'],
    testCategories: ['Precious Metals'],
    contact: 'rahc-jaipur@example.gov.in',
    distanceKm: 8,
  },
  {
    id: 'lab-6',
    name: 'National Metallurgical Laboratory',
    city: 'Jamshedpur',
    state: 'Jharkhand',
    accreditations: ['NABL', 'ISO-17025'],
    testCategories: ['Metals & Alloys', 'Construction Materials'],
    contact: 'nml-testing@example.gov.in',
    distanceKm: 22,
  },
]
