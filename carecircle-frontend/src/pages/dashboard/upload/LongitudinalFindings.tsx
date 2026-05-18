import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CheckSquare, Square, ChevronDown } from 'lucide-react'
import { ConcernCard } from '../../../components/ConcernCard'
import { Button } from '../../../components/ui/Button'
import { SkeletonList } from '../../../components/ui/SkeletonCard'
import { PageTransition } from '../../../components/ui/PageTransition'
import api from '../../../lib/api'
import { usePatientStore } from '../../../store/patient'
import { useToast } from '../../../store/toast'
import type { LongitudinalFindings as LongitudinalFindingsType, TodoItem, Concern } from '../../../types'

const CONCERN_GROUPS = [
  { key: 'new', label: 'New', color: '#0891B2', bg: '#F0F9FF' },
  { key: 'escalated', label: 'Escalated', color: '#DC2626', bg: '#FEF2F2' },
  { key: 'improved', label: 'Improved', color: '#0D9488', bg: '#F0FDFA' },
  { key: 'resolved', label: 'Resolved', color: '#16A34A', bg: '#F0FDF4' },
]

export function LongitudinalFindings() {
  const { uploadEventId } = useParams<{ uploadEventId: string }>()
  const navigate = useNavigate()
  const { patient_id } = usePatientStore()
  const toast = useToast()
  const [checkedTodos, setCheckedTodos] = useState<Set<string>>(new Set())
  const [confirming, setConfirming] = useState(false)
  const [showResolved, setShowResolved] = useState(false)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['longitudinal-findings', patient_id, uploadEventId],
    queryFn: async () => {
      const res = await api.get(
        `/api/longitudinal/findings/${patient_id}/${uploadEventId}`
      )
      return res.data as LongitudinalFindingsType
    },
    enabled: !!patient_id && !!uploadEventId,
    retry: 2,
  })

  const toggleTodo = (id: string) => {
    setCheckedTodos((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const handleConfirm = async () => {
    setConfirming(true)
    try {
      await api.post(
        `/api/longitudinal/confirm_findings/${patient_id}/${uploadEventId}`,
        {}
      )
      toast.success('Analysis saved. Dashboard updated.')
      navigate('/dashboard')
    } catch {
      toast.error('Could not confirm findings. Please try again.')
    } finally {
      setConfirming(false)
    }
  }

  const getConcernsByStatus = (status: string) =>
    (data?.concerns ?? []).filter((c) => c.status === status)

  return (
    <PageTransition className="px-4 py-6 max-w-xl mx-auto">
      <h2
        className="text-2xl font-normal text-text-primary mb-1"
        style={{ fontFamily: 'Fraunces, serif' }}
      >
        What changed
      </h2>
      <p className="text-sm text-text-secondary mb-6">
        Based on your new documents compared to previous analysis.
      </p>

      {isLoading && <SkeletonList count={4} />}

      {isError && (
        <div className="bg-[#FEF2F2] border border-[#DC262630] rounded-xl p-5 text-center mb-6">
          <p className="text-sm font-semibold text-severity-critical mb-1">Couldn't load findings</p>
          <p className="text-sm text-severity-critical opacity-80 mb-4">
            Something went wrong. Your data is saved — try fetching again.
          </p>
          <button
            onClick={() => refetch()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-[#DC262630] text-severity-critical text-sm font-medium hover:bg-[#FEF2F2] transition-colors"
          >
            Try again
          </button>
        </div>
      )}

      {!isLoading && !isError && data && (
        <>
          {/* Medication changes */}
          {data.medication_changes && data.medication_changes.length > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-3">
                Medication changes
              </h3>
              <div className="flex gap-2 overflow-x-auto pb-2 -mx-4 px-4">
                {data.medication_changes.map((change, i) => (
                  <MedChangePill key={i} change={change} />
                ))}
              </div>
            </div>
          )}

          {/* Summary strip */}
          {data.summary && (
            <div className="flex flex-wrap gap-2 mb-6">
              {data.summary.new_count > 0 && (
                <SummaryPill label={`${data.summary.new_count} new`} color="#0891B2" bg="#F0F9FF" />
              )}
              {data.summary.escalated_count > 0 && (
                <SummaryPill label={`${data.summary.escalated_count} escalated`} color="#DC2626" bg="#FEF2F2" />
              )}
              {data.summary.improved_count > 0 && (
                <SummaryPill label={`${data.summary.improved_count} improved`} color="#0D9488" bg="#F0FDFA" />
              )}
              {data.summary.resolved_count > 0 && (
                <SummaryPill label={`${data.summary.resolved_count} resolved`} color="#16A34A" bg="#F0FDF4" />
              )}
            </div>
          )}

          {/* Concern groups */}
          {CONCERN_GROUPS.map(({ key, label, color, bg }) => {
            const group = getConcernsByStatus(key)
            if (group.length === 0) return null
            return (
              <ConcernGroup
                key={key}
                label={label}
                color={color}
                bg={bg}
                concerns={group}
              />
            )
          })}

          {/* To-do sections */}
          <div className="mb-6">
            <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-4">
              Updated to-do list
            </h3>
            {data.todos.do_now && data.todos.do_now.length > 0 && (
              <TodoSection
                title="Do now"
                items={data.todos.do_now}
                checked={checkedTodos}
                onToggle={toggleTodo}
                borderColor="#DC2626"
              />
            )}
            {data.todos.follow_up && data.todos.follow_up.length > 0 && (
              <TodoSection
                title="Follow up"
                items={data.todos.follow_up}
                checked={checkedTodos}
                onToggle={toggleTodo}
                borderColor="#D97706"
              />
            )}
            {data.todos.keep_monitoring && data.todos.keep_monitoring.length > 0 && (
              <TodoSection
                title="Keep monitoring"
                items={data.todos.keep_monitoring}
                checked={checkedTodos}
                onToggle={toggleTodo}
                borderColor="#0D9488"
              />
            )}

            {/* Resolved todos */}
            {data.todos.resolved && data.todos.resolved.length > 0 && (
              <div className="mt-2">
                <button
                  onClick={() => setShowResolved((v) => !v)}
                  className="flex items-center gap-2 text-sm text-text-muted hover:text-text-secondary transition-colors mb-2"
                >
                  <ChevronDown
                    className={`w-4 h-4 transition-transform ${showResolved ? 'rotate-180' : ''}`}
                  />
                  {data.todos.resolved.length} completed tasks
                </button>
                {showResolved && (
                  <TodoSection
                    title="Completed"
                    items={data.todos.resolved}
                    checked={new Set(data.todos.resolved.map((t) => t.todo_id))}
                    onToggle={() => {}}
                    borderColor="#16A34A"
                  />
                )}
              </div>
            )}
          </div>
        </>
      )}

      <Button fullWidth size="lg" loading={confirming} disabled={isLoading} onClick={handleConfirm}>
        I've reviewed everything
      </Button>
    </PageTransition>
  )
}

function ConcernGroup({
  label,
  color,
  bg,
  concerns,
}: {
  label: string
  color: string
  bg: string
  concerns: Concern[]
}) {
  return (
    <div className="mb-5">
      <div
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg mb-3 w-fit"
        style={{ backgroundColor: bg }}
      >
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
        <h3 className="text-sm font-semibold" style={{ color }}>
          {label} ({concerns.length})
        </h3>
      </div>
      <div className="flex flex-col gap-3">
        {concerns.map((c) => (
          <ConcernCard key={c.id} concern={c} />
        ))}
      </div>
    </div>
  )
}

function MedChangePill({ change }: { change: { brand_name: string; change_type: string } }) {
  const colors: Record<string, { color: string; bg: string }> = {
    added: { color: '#16A34A', bg: '#F0FDF4' },
    removed: { color: '#DC2626', bg: '#FEF2F2' },
    modified: { color: '#D97706', bg: '#FFFBEB' },
    unchanged: { color: '#6B7280', bg: '#F9FAFB' },
  }
  const style = colors[change.change_type] ?? colors.unchanged

  return (
    <span
      className="flex-shrink-0 inline-flex px-3 py-1.5 rounded-full text-sm font-medium"
      style={{ color: style.color, backgroundColor: style.bg }}
    >
      {change.change_type === 'added' ? '+ ' : change.change_type === 'removed' ? '– ' : ''}
      {change.brand_name}
    </span>
  )
}

function TodoSection({
  title,
  items,
  checked,
  onToggle,
  borderColor,
}: {
  title: string
  items: TodoItem[]
  checked: Set<string>
  onToggle: (id: string) => void
  borderColor: string
}) {
  return (
    <div
      className="mb-3 bg-bg-card rounded-xl border border-border shadow-sm overflow-hidden"
      style={{ borderLeftWidth: '4px', borderLeftColor: borderColor }}
    >
      <div className="px-4 py-2.5 border-b border-border">
        <h4 className="text-sm font-semibold text-text-primary">{title}</h4>
      </div>
      <div className="divide-y divide-border">
        {items.map((item) => (
          <button
            key={item.todo_id}
            onClick={() => onToggle(item.todo_id)}
            className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-bg-secondary transition-colors"
            style={{ minHeight: '44px' }}
          >
            {checked.has(item.todo_id) ? (
              <CheckSquare className="w-5 h-5 shrink-0 mt-0.5 text-accent-primary" />
            ) : (
              <Square className="w-5 h-5 shrink-0 mt-0.5 text-text-muted" />
            )}
            <span
              className={`text-sm leading-relaxed ${
                checked.has(item.todo_id) ? 'text-text-muted line-through' : 'text-text-primary'
              }`}
            >
              {item.text}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

function SummaryPill({ label, color, bg }: { label: string; color: string; bg: string }) {
  return (
    <span
      className="inline-flex px-3 py-1 rounded-full text-sm font-medium"
      style={{ color, backgroundColor: bg }}
    >
      {label}
    </span>
  )
}
