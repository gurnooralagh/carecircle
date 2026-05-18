import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, AlertCircle, Clock, Activity } from 'lucide-react'
import { SkeletonCard, SkeletonList } from '../../components/ui/SkeletonCard'
import { PageTransition } from '../../components/ui/PageTransition'
import api from '../../lib/api'
import { usePatientStore } from '../../store/patient'
import { calcAge, formatDate } from '../../lib/utils'
import type { DashboardSummary, ActionItem, AnalysisRun } from '../../types'

export function DashboardHome() {
  const navigate = useNavigate()
  const { patient_id } = usePatientStore()

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-summary', patient_id],
    queryFn: async () => {
      try {
        const res = await api.get(`/api/dashboard/summary/${patient_id}`)
        return res.data as DashboardSummary
      } catch {
        return null
      }
    },
    enabled: !!patient_id,
  })

  if (isLoading) {
    return (
      <PageTransition className="px-4 py-6 max-w-xl mx-auto space-y-4">
        <SkeletonCard lines={3} />
        <div className="grid grid-cols-2 gap-3">
          <SkeletonCard lines={2} />
          <SkeletonCard lines={2} />
        </div>
        <SkeletonList count={2} />
      </PageTransition>
    )
  }

  if (!data) {
    return (
      <PageTransition className="px-4 py-6 max-w-xl mx-auto space-y-4">
        <div className="bg-bg-card border border-border rounded-2xl p-6 text-center">
          <p className="text-base font-semibold text-text-primary mb-1">Dashboard coming soon</p>
          <p className="text-sm text-text-secondary">
            Use the tabs below to see your findings and medications.
          </p>
        </div>
      </PageTransition>
    )
  }

  const {
    patient,
    last_analysis_at,
    runs,
    active_concerns_count,
    active_medications_count,
    top_concerns,
    action_summary,
  } = data

  const age = calcAge(patient.date_of_birth)

  return (
    <PageTransition className="px-4 py-6 max-w-xl mx-auto">
      {/* Patient card */}
      <div className="bg-bg-card rounded-xl border border-border shadow-sm p-5 mb-4">
        <h2 className="text-xl font-semibold text-text-primary">{patient.full_name}</h2>
        <p className="text-sm text-text-secondary mt-0.5">
          {age} years · {patient.gender}
          {patient.city ? ` · ${patient.city}` : ''}
        </p>
        <p className="text-xs text-text-muted mt-2">
          Last analysis: {formatDate(last_analysis_at)}
        </p>
      </div>

      {/* Analysis runs history */}
      {runs && runs.length > 0 && <RunsHistory runs={runs} />}

      {/* Stat tiles */}
      <div className="grid grid-cols-2 gap-3 mb-6">
        <button
          onClick={() => navigate('/dashboard/findings')}
          className="bg-bg-card rounded-xl border border-border shadow-sm p-4 text-center hover:bg-bg-secondary transition-colors active:scale-[0.98]"
          style={{ minHeight: '44px' }}
        >
          <p className="text-2xl font-semibold" style={{ color: '#EA580C' }}>
            {active_concerns_count}
          </p>
          <p className="text-xs text-text-muted mt-0.5">Concerns</p>
        </button>
        <button
          onClick={() => navigate('/dashboard/medications')}
          className="bg-bg-card rounded-xl border border-border shadow-sm p-4 text-center hover:bg-bg-secondary transition-colors active:scale-[0.98]"
          style={{ minHeight: '44px' }}
        >
          <p className="text-2xl font-semibold" style={{ color: '#0D9488' }}>
            {active_medications_count}
          </p>
          <p className="text-xs text-text-muted mt-0.5">Medications</p>
        </button>
      </div>

      {/* Top 1–2 concerns */}
      {top_concerns && top_concerns.length > 0 && (
        <div className="mb-6">
          <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-3">
            Priority concerns
          </h3>
          <div className="flex flex-col gap-3">
            {top_concerns.map((c) => (
              <MiniConcernCard
                key={c.id}
                concern={c}
                onClick={() => navigate('/dashboard/findings')}
              />
            ))}
          </div>
          {active_concerns_count > 2 && (
            <button
              onClick={() => navigate('/dashboard/findings')}
              className="w-full text-center text-sm text-accent-primary hover:underline mt-3"
            >
              View all {active_concerns_count} concerns
            </button>
          )}
        </div>
      )}

      {/* Action plan */}
      {action_summary && <ActionPlan actionSummary={action_summary} />}
    </PageTransition>
  )
}

import type { Concern } from '../../types'

function MiniConcernCard({ concern, onClick }: { concern: Concern; onClick: () => void }) {
  const PRIORITY_COLOR: Record<string, string> = {
    critical_concern: '#DC2626',
    high_priority: '#EA580C',
    moderate: '#D97706',
    for_your_awareness: '#0891B2',
  }
  const PRIORITY_LABEL: Record<string, string> = {
    critical_concern: 'Critical',
    high_priority: 'High priority',
    moderate: 'Moderate',
    for_your_awareness: 'For your awareness',
  }
  const color = PRIORITY_COLOR[concern.priority] ?? '#6B7280'
  const label = PRIORITY_LABEL[concern.priority] ?? concern.priority

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
      className="bg-bg-card rounded-xl border border-border shadow-sm p-4 flex items-start gap-3 cursor-pointer hover:bg-bg-secondary transition-colors"
      style={{ borderLeft: `4px solid ${color}` }}
    >
      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold mb-0.5" style={{ color }}>{label}</p>
        <p className="text-sm font-semibold text-text-primary leading-tight">{concern.title}</p>
        <p className="text-xs text-text-secondary mt-1 line-clamp-2">{concern.summary}</p>
      </div>
      <ChevronRight className="w-4 h-4 text-text-muted shrink-0 mt-0.5" />
    </div>
  )
}

function RunsHistory({ runs }: { runs: AnalysisRun[] }) {
  const mostRecentId = runs[runs.length - 1]?.run_id

  return (
    <div className="mb-5">
      <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-2">
        Analysis history
      </h3>
      <div className="flex flex-col gap-0 bg-bg-card rounded-xl border border-border shadow-sm overflow-hidden divide-y divide-border">
        {[...runs].reverse().map((run) => {
          const isLatest = run.run_id === mostRecentId
          return (
            <div key={run.run_id} className="flex items-center justify-between px-4 py-3">
              <div className="flex items-center gap-2">
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: run.run_type === 'onboarding' ? '#0891B2' : '#8B5CF6' }}
                />
                <div>
                  <p className="text-sm font-medium text-text-primary">{run.label}</p>
                  <p className="text-xs text-text-muted">{formatDate(run.run_date)}</p>
                </div>
              </div>
              {isLatest && (
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-[#F0FDF4] text-[#16A34A]">
                  Latest
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

const ACTION_SECTIONS: {
  key: 'do_now' | 'follow_up' | 'keep_monitoring'
  label: string
  icon: React.ElementType
  dotColor: string
}[] = [
  { key: 'do_now', label: 'Do now', icon: AlertCircle, dotColor: '#DC2626' },
  { key: 'follow_up', label: 'Follow up', icon: Clock, dotColor: '#D97706' },
  { key: 'keep_monitoring', label: 'Keep monitoring', icon: Activity, dotColor: '#0891B2' },
]

function ActionPlan({
  actionSummary,
}: {
  actionSummary: { do_now: ActionItem[]; follow_up: ActionItem[]; keep_monitoring: ActionItem[] }
}) {
  const [open, setOpen] = useState<Set<string>>(new Set(['do_now']))

  const hasItems =
    actionSummary.do_now.length > 0 ||
    actionSummary.follow_up.length > 0 ||
    actionSummary.keep_monitoring.length > 0

  if (!hasItems) return null

  const toggle = (key: string) => {
    setOpen((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  return (
    <div className="mb-6">
      <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-3">
        Action plan
      </h3>
      <div className="bg-bg-card rounded-xl border border-border shadow-sm divide-y divide-border overflow-hidden">
        {ACTION_SECTIONS.map(({ key, label, icon: Icon, dotColor }) => {
          const items = actionSummary[key]
          if (items.length === 0) return null
          const isOpen = open.has(key)

          return (
            <div key={key}>
              <button
                onClick={() => toggle(key)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-bg-secondary transition-colors"
                style={{ minHeight: '44px' }}
              >
                <span className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                  <Icon className="w-4 h-4 shrink-0" style={{ color: dotColor }} />
                  {label}
                  <span
                    className="text-xs font-medium px-1.5 py-0.5 rounded-full"
                    style={{ color: dotColor, backgroundColor: `${dotColor}18` }}
                  >
                    {items.length}
                  </span>
                </span>
                <ChevronDown
                  className={`w-4 h-4 text-text-muted transition-transform ${isOpen ? 'rotate-180' : ''}`}
                />
              </button>

              {isOpen && (
                <ul className="px-4 pb-3 flex flex-col gap-2">
                  {items.map((item) => (
                    <li
                      key={item.id}
                      className="flex items-start gap-2 text-sm text-text-primary leading-relaxed"
                    >
                      <span
                        className="mt-2 w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ backgroundColor: dotColor }}
                      />
                      {item.text}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
