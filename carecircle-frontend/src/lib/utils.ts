import { differenceInYears, format, parseISO } from 'date-fns'

export function calcAge(dateOfBirth: string): number {
  try {
    return differenceInYears(new Date(), parseISO(dateOfBirth))
  } catch {
    return 0
  }
}

export function formatDate(dateString: string, fmt = 'MMM d, yyyy'): string {
  try {
    return format(parseISO(dateString), fmt)
  } catch {
    return dateString
  }
}

export function formatDateShort(dateString: string): string {
  return formatDate(dateString, 'MMM d')
}

export type Severity =
  | 'critical'
  | 'high'
  | 'moderate'
  | 'low'
  | 'info'
  | 'resolved'
  | 'improved'

export const SEVERITY_COLORS: Record<Severity, string> = {
  critical: '#DC2626',
  high: '#EA580C',
  moderate: '#D97706',
  low: '#0D9488',
  info: '#6B7280',
  resolved: '#16A34A',
  improved: '#0891B2',
}

export const SEVERITY_BG: Record<Severity, string> = {
  critical: '#FEF2F2',
  high: '#FFF7ED',
  moderate: '#FFFBEB',
  low: '#F0FDFA',
  info: '#F9FAFB',
  resolved: '#F0FDF4',
  improved: '#F0F9FF',
}

export const SEVERITY_LABELS: Record<Severity, string> = {
  critical: 'URGENT',
  high: 'HIGH',
  moderate: 'MODERATE',
  low: 'FOR YOUR AWARENESS',
  info: 'INFO',
  resolved: 'RESOLVED',
  improved: 'IMPROVED',
}

const PRIORITY_TO_SEVERITY: Record<string, Severity> = {
  critical_concern: 'critical',
  high_priority: 'high',
  moderate: 'moderate',
  for_your_awareness: 'low',
}

export function getSeverityColor(severity: string): string {
  const mapped = PRIORITY_TO_SEVERITY[severity]
  return SEVERITY_COLORS[(mapped ?? severity) as Severity] ?? SEVERITY_COLORS.info
}

export function getSeverityBg(severity: string): string {
  const mapped = PRIORITY_TO_SEVERITY[severity]
  return SEVERITY_BG[(mapped ?? severity) as Severity] ?? SEVERITY_BG.info
}

export function getSeverityLabel(severity: string): string {
  const PRIORITY_LABELS: Record<string, string> = {
    critical_concern: 'CRITICAL CONCERN',
    high_priority: 'HIGH PRIORITY',
    moderate: 'NEEDS ATTENTION',
    for_your_awareness: 'FOR YOUR AWARENESS',
  }
  return PRIORITY_LABELS[severity] ?? SEVERITY_LABELS[severity as Severity] ?? severity.toUpperCase()
}

export function getHealthStatusColor(
  status: 'stable' | 'needs_attention' | 'urgent' | null
): string {
  switch (status) {
    case 'stable':
      return '#16A34A'
    case 'needs_attention':
      return '#D97706'
    case 'urgent':
      return '#DC2626'
    default:
      return '#9E9E9E'
  }
}

export function getHealthStatusLabel(
  status: 'stable' | 'needs_attention' | 'urgent' | null
): string {
  switch (status) {
    case 'stable':
      return 'Stable'
    case 'needs_attention':
      return 'Needs Attention'
    case 'urgent':
      return 'Urgent'
    default:
      return 'Unknown'
  }
}

export function classNames(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ')
}

export function isNotBuiltError(error: unknown): boolean {
  if (!error) return false
  const axiosErr = error as { response?: { status: number } }
  return (
    axiosErr.response?.status === 404 || axiosErr.response?.status === 500
  )
}
