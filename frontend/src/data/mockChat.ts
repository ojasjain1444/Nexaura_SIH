import type { ChatMessage, SourceCitation } from '../types'

/**
 * Placeholder assistant responses for frontend demonstration only.
 * These simulate the future RAG-based AI assistant (see services/api.ts) and are NOT real model output.
 */

export interface MockTopic {
  id: string
  label: string
  description: string
  samplePrompt: string
}

export const quickTopics: MockTopic[] = [
  {
    id: 'find-standard',
    label: 'Find applicable standards',
    description: 'Identify Indian Standards relevant to a product or process',
    samplePrompt: 'Which Indian Standard applies to packaged drinking water bottles?',
  },
  {
    id: 'certification',
    label: 'Certification schemes',
    description: 'Understand BIS certification schemes and requirements',
    samplePrompt: 'What certification do I need to sell electric kettles in India?',
  },
  {
    id: 'process',
    label: 'Certification process',
    description: 'Step-by-step guidance on obtaining a license',
    samplePrompt: 'Walk me through the process of getting an ISI mark license.',
  },
  {
    id: 'hallmarking',
    label: 'Hallmarking guidance',
    description: 'Gold jewellery hallmarking rules and procedure',
    samplePrompt: 'How does gold jewellery hallmarking work and what purities are allowed?',
  },
  {
    id: 'labs',
    label: 'Testing laboratories',
    description: 'Find BIS-recognized labs for product testing',
    samplePrompt: 'Suggest testing laboratories near Chennai for plastics testing.',
  },
]

const citation = (standardCode: string, title: string, clause?: string): SourceCitation => ({
  id: `${standardCode}-${clause ?? 'main'}`,
  standardCode,
  title,
  clause,
})

interface MockResponse {
  keywords: string[]
  content: string
  sources?: SourceCitation[]
  quickReplies?: string[]
}

const mockResponses: MockResponse[] = [
  {
    keywords: ['drinking water', 'bottle', 'packaged water'],
    content:
      'Packaged drinking water (other than natural mineral water) sold in India must conform to IS 14625. This standard covers permissible limits for physical, chemical, and microbiological parameters, along with labelling requirements. Products in this category require mandatory BIS certification before sale.',
    sources: [citation('IS 14625', 'Packaged Drinking Water (Other than Natural Mineral Water) — Specification', 'Clause 4: Requirements')],
    quickReplies: ['What is the certification process for this?', 'Which labs test packaged water?'],
  },
  {
    keywords: ['electric kettle', 'household appliance', 'electrical appliance'],
    content:
      'Electric kettles fall under household electrical appliances and are governed by IS 302-1 (general safety requirements) along with the applicable Part 2 standard for the specific appliance type. Sale in India requires registration under the Compulsory Registration Scheme (CRS) after testing at a BIS-recognized lab.',
    sources: [citation('IS 302-1', 'Safety of Household and Similar Electrical Appliances, Part 1', 'Clause 3: Scope')],
    quickReplies: ['Show me the CRS registration steps', 'Find a lab for electrical testing'],
  },
  {
    keywords: ['isi mark', 'isi license', 'product certification', 'certification process'],
    content:
      'To obtain an ISI Mark license: (1) submit an application with product and factory details, (2) undergo a factory evaluation by BIS officers, (3) have product samples tested against the applicable Indian Standard, and (4) receive the license upon satisfactory evaluation. The average duration is around 90 days.',
    sources: [citation('Product Certification Scheme', 'Product Certification Scheme (ISI Mark)')],
    quickReplies: ['What documents are required?', 'What are the fees involved?'],
  },
  {
    keywords: ['hallmark', 'hallmarking', 'gold jewellery', 'gold purity'],
    content:
      'Gold jewellery hallmarking in India is governed by IS 15885. Jewellers must register under the BIS Hallmarking Scheme, and items are tested for purity at a registered Assaying & Hallmarking Centre (AHC) before receiving a hallmark with a unique HUID. Permitted fineness grades include 22K916, 18K750, and 14K585.',
    sources: [citation('IS 15885', 'Hallmarking of Gold Jewellery and Artefacts', 'Clause 5: Fineness Grades')],
    quickReplies: ['How do I register as a jeweller?', 'How can I verify a HUID?'],
  },
  {
    keywords: ['lab', 'laboratory', 'testing', 'plastics testing', 'chennai'],
    content:
      'Here are BIS-recognized testing laboratories that may be relevant based on your query. You can filter by test category, city, and accreditation type in the Lab Directory for a complete list with contact details.',
    quickReplies: ['Open the Lab Directory', 'Find labs near Delhi'],
  },
  {
    keywords: ['verify', 'genuine', 'fake', 'complaint', 'consumer'],
    content:
      'You can verify an ISI/hallmark license by checking the license number against the BIS database, which lists the manufacturer, product, and validity status. If you suspect a product is falsely marked, you can file a complaint through the BIS CARE portal or the National Consumer Helpline.',
    quickReplies: ['How do I file a complaint?', 'What information do I need to verify a mark?'],
  },
]

const defaultResponse: MockResponse = {
  keywords: [],
  content:
    "I can help with Indian Standards, certification schemes, hallmarking, testing labs, and consumer queries. Try asking something like \"Which standard applies to my product?\" or select a quick topic below to get started.",
  quickReplies: quickTopics.slice(0, 3).map((t) => t.samplePrompt),
}

export function findMockResponse(userText: string): MockResponse {
  const lower = userText.toLowerCase()
  const match = mockResponses.find((r) => r.keywords.some((k) => lower.includes(k)))
  return match ?? defaultResponse
}

export const sampleConversationStarters: ChatMessage[] = []
