import { BookMarked, Building2, FileText, FlaskConical, History, LayoutGrid, MessageSquareText, Settings } from 'lucide-react'
import type { NavItem } from '../types'

export const navItems: NavItem[] = [
  { to: '/', label: 'Home', icon: LayoutGrid, end: true, color: 'slate' },
  // Emerald — the system's one accent color — reserved for the Assistant,
  // the app's core/primary feature, so its color carries actual meaning
  // ("the main thing to use") rather than being one of several
  // arbitrarily-assigned tones.
  { to: '/assistant', label: 'Assistant', icon: MessageSquareText, color: 'emerald' },
  { to: '/standards', label: 'Standards Explorer', icon: BookMarked, color: 'sky' },
  { to: '/certification', label: 'Certification Guide', icon: FlaskConical, color: 'violet' },
  { to: '/labs', label: 'Lab Directory', icon: Building2, color: 'sky' },
  { to: '/documents', label: 'Document Manager', icon: FileText, color: 'amber' },
  { to: '/history', label: 'History', icon: History, color: 'rose' },
  { to: '/settings', label: 'Settings', icon: Settings, color: 'slate' },
]
