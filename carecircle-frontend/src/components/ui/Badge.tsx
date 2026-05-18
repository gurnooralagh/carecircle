import React from 'react'

interface BadgeProps {
  children: React.ReactNode
  color?: string
  bg?: string
  className?: string
}

export function Badge({ children, color = '#6B7280', bg = '#F9FAFB', className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold tracking-wide ${className}`}
      style={{ color, backgroundColor: bg }}
    >
      {children}
    </span>
  )
}

interface StatusBadgeProps {
  status: 'new' | 'escalated' | 'resolved' | 'improved' | 'existing'
}

const STATUS_MAP = {
  new: { label: 'NEW', color: '#0891B2', bg: '#F0F9FF' },
  escalated: { label: 'ESCALATED', color: '#DC2626', bg: '#FEF2F2' },
  resolved: { label: 'RESOLVED', color: '#16A34A', bg: '#F0FDF4' },
  improved: { label: 'IMPROVED', color: '#0891B2', bg: '#F0F9FF' },
  existing: { label: '', color: '', bg: '' },
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const { label, color, bg } = STATUS_MAP[status] ?? STATUS_MAP.existing
  if (!label) return null
  return <Badge color={color} bg={bg}>{label}</Badge>
}
