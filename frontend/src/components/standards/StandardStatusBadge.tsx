import { Badge } from '../ui'
import type { StandardStatus } from '../../types'

const statusConfig: Record<StandardStatus, { label: string; tone: 'success' | 'warning' | 'danger' }> = {
  active: { label: 'Active', tone: 'success' },
  'under-revision': { label: 'Under Revision', tone: 'warning' },
  withdrawn: { label: 'Withdrawn', tone: 'danger' },
}

export function StandardStatusBadge({ status }: { status: StandardStatus }) {
  const config = statusConfig[status]
  return <Badge tone={config.tone}>{config.label}</Badge>
}
