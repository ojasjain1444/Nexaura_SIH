import type { ChatSession } from '../types'

/**
 * Placeholder conversation history for frontend demonstration.
 * In production this will be replaced by persisted user conversation history from the backend.
 */
export const mockHistory: ChatSession[] = [
  {
    id: 'session-1',
    title: 'ISI mark for electric kettles',
    createdAt: '2026-09-10T09:15:00.000Z',
    updatedAt: '2026-09-10T09:22:00.000Z',
    messages: [
      { id: 'h1-1', role: 'user', content: 'What certification do I need to sell electric kettles in India?', timestamp: '2026-09-10T09:15:00.000Z' },
      {
        id: 'h1-2',
        role: 'assistant',
        content:
          'Electric kettles fall under household electrical appliances and are governed by IS 302-1 along with the applicable Part 2 standard. Sale in India requires registration under the Compulsory Registration Scheme (CRS) after testing at a BIS-recognized lab.',
        timestamp: '2026-09-10T09:15:40.000Z',
        sources: [{ id: 'is-302-1', standardCode: 'IS 302-1', title: 'Safety of Household and Similar Electrical Appliances, Part 1' }],
      },
    ],
  },
  {
    id: 'session-2',
    title: 'Gold hallmarking purity grades',
    createdAt: '2026-09-08T14:02:00.000Z',
    updatedAt: '2026-09-08T14:05:00.000Z',
    messages: [
      { id: 'h2-1', role: 'user', content: 'How does gold jewellery hallmarking work?', timestamp: '2026-09-08T14:02:00.000Z' },
      {
        id: 'h2-2',
        role: 'assistant',
        content:
          'Gold jewellery hallmarking is governed by IS 15885. Jewellers register under the BIS Hallmarking Scheme, and items are tested for purity at a registered Assaying & Hallmarking Centre before receiving a hallmark with a unique HUID.',
        timestamp: '2026-09-08T14:02:35.000Z',
        sources: [{ id: 'is-15885', standardCode: 'IS 15885', title: 'Hallmarking of Gold Jewellery and Artefacts' }],
      },
    ],
  },
  {
    id: 'session-3',
    title: 'Packaged drinking water standard',
    createdAt: '2026-09-05T11:30:00.000Z',
    updatedAt: '2026-09-05T11:33:00.000Z',
    messages: [
      { id: 'h3-1', role: 'user', content: 'Which Indian Standard applies to packaged drinking water bottles?', timestamp: '2026-09-05T11:30:00.000Z' },
      {
        id: 'h3-2',
        role: 'assistant',
        content:
          'Packaged drinking water (other than natural mineral water) must conform to IS 14625, which covers permissible limits and labelling requirements. Mandatory BIS certification is required before sale.',
        timestamp: '2026-09-05T11:30:30.000Z',
        sources: [{ id: 'is-14625', standardCode: 'IS 14625', title: 'Packaged Drinking Water Specification' }],
      },
    ],
  },
]
