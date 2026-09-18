import type { ComponentType } from 'react'
import type { LucideProps } from 'lucide-react'

export interface NavItem {
  to: string
  label: string
  icon: ComponentType<LucideProps>
  end?: boolean
  /** Tailwind color name (e.g. "indigo", "amber") used to tint this
   * item's icon badge in the sidebar — each section gets its own color
   * so the nav reads as a set of distinct tools, not one uniform list. */
  color: string
}
