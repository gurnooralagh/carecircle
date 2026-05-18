import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CheckSquare, Square, AlertCircle, Clock, Activity, ClipboardCheck, RefreshCw } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { SkeletonList } from '../../components/ui/SkeletonCard'
import { PageTransition } from '../../components/ui/PageTransition'
import { EmptyState } from '../../components/ui/EmptyState'
import api from '../../lib/api'
import { usePatientStore } from '../../store/patient'
import { useToast } from '../../store/toast'
import type { ActionSummary, ActionItem } from '../../types'

interface RawItem {
  id?: string
  text?: string
  action?: string
  category?: string
}

export function OnboardingChecklist() {
  const navigate = useNavigate()
  const { patient_id, setPatient } = usePatientStore()
  const toast = useToast()
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [completing, setCompleting] = useState(false)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['onboarding-action-summary', patient_id],
    queryFn: async () => {
      const res = await api.get(`/api/onboarding/findings/${patient_id}`)
      const raw = res.data?.action_summary ?? {}
      // Normalise: backend uses 'action' field per item and 'ongoing_monitoring' key
      const normalise = (items: RawItem[] = []) =>
        items.map((item, i) => ({
          id: item.id ?? `item-${i}`,
          text: item.action ?? item.text ?? '',
          category: item.category ?? 'keep_monitoring',
        }))
      return {
        do_now: normalise(raw.do_now),
        follow_up: normalise(raw.follow_up),
        keep_monitoring: normalise(raw.keep_monitoring ?? raw.ongoing_monitoring),
      } as ActionSummary
    },
    enabled: !!patient_id,
    retry: 2,
  })

  const toggle = (id: string) => {
    setChecked((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const handleComplete = async () => {
    setCompleting(true)
    try {
      await api.post(`/api/onboarding/confirm/${patient_id}`, {})
      setPatient({ onboarding_complete: true })
      toast.success('Welcome to CareCircle! Your dashboard is ready.')
      navigate('/dashboard')
    } catch {
      toast.error('Could not complete onboarding. Please try again.')
    } finally {
      setCompleting(false)
    }
  }

  return (
    <div className="min-h-screen bg-bg-primary flex flex-col">
      <header className="px-6 py-4 border-b border-border">
        <span
          className="text-lg font-semibold text-accent-primary"
          style={{ fontFamily: 'Fraunces, serif' }}
        >
          CareCircle
        </span>
      </header>

      <PageTransition className="flex-1 max-w-xl mx-auto w-full px-6 py-8">
        <h2
          className="text-2xl font-normal text-text-primary mb-1"
          style={{ fontFamily: 'Fraunces, serif' }}
        >
          Your action plan
        </h2>
        <p className="text-sm text-text-secondary mb-8">
          Here's what we recommend based on the analysis.
        </p>

        {isLoading && <SkeletonList count={3} />}

        {isError && (
          <div className="bg-[#FEF2F2] border border-[#DC262630] rounded-xl p-5 text-center mb-4">
            <p className="text-sm font-semibold text-severity-critical mb-1">Couldn't load action plan</p>
            <p className="text-sm text-severity-critical opacity-80 mb-4">
              You can still proceed to the dashboard. Your findings are saved.
            </p>
            <button
              onClick={() => refetch()}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-[#DC262630] text-severity-critical text-sm font-medium hover:bg-[#FEF2F2] transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Try again
            </button>
          </div>
        )}

        {!isLoading && !isError && !data && (
          <EmptyState
            icon={ClipboardCheck}
            title="No action items yet"
            description="The analysis didn't generate specific action items this time. You can still proceed to your dashboard and review your findings there."
          />
        )}

        {!isLoading && !isError && data &&
          !data.do_now?.length && !data.follow_up?.length && !data.keep_monitoring?.length && (
          <EmptyState
            icon={ClipboardCheck}
            title="No action items yet"
            description="The analysis didn't generate specific action items this time. You can still proceed to your dashboard and review your findings there."
          />
        )}

        {!isLoading && !isError && data && (!!data.do_now?.length || !!data.follow_up?.length || !!data.keep_monitoring?.length) && (
          <div className="flex flex-col gap-6 mb-8">
            {(data.do_now?.length ?? 0) > 0 && (
              <Section
                title="Do now"
                icon={AlertCircle}
                borderColor="#DC2626"
                iconColor="#DC2626"
                items={data.do_now}
                checked={checked}
                onToggle={toggle}
              />
            )}
            {(data.follow_up?.length ?? 0) > 0 && (
              <Section
                title="Follow up"
                icon={Clock}
                borderColor="#D97706"
                iconColor="#D97706"
                items={data.follow_up}
                checked={checked}
                onToggle={toggle}
              />
            )}
            {(data.keep_monitoring?.length ?? 0) > 0 && (
              <Section
                title="Keep monitoring"
                icon={Activity}
                borderColor="#0D9488"
                iconColor="#0D9488"
                items={data.keep_monitoring}
                checked={checked}
                onToggle={toggle}
              />
            )}
          </div>
        )}

        <Button
          onClick={handleComplete}
          fullWidth
          size="lg"
          loading={completing}
          disabled={isLoading}
        >
          I've reviewed everything
        </Button>
      </PageTransition>
    </div>
  )
}

function Section({
  title,
  icon: Icon,
  borderColor,
  iconColor,
  items,
  checked,
  onToggle,
}: {
  title: string
  icon: React.ElementType
  borderColor: string
  iconColor: string
  items: ActionItem[]
  checked: Set<string>
  onToggle: (id: string) => void
}) {
  return (
    <div
      className="bg-bg-card rounded-xl border-l-4 border border-border shadow-sm overflow-hidden"
      style={{ borderLeftColor: borderColor }}
    >
      <div className="px-4 py-3 flex items-center gap-2 border-b border-border">
        <Icon className="w-4 h-4" style={{ color: iconColor }} />
        <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
      </div>
      <div className="divide-y divide-border">
        {items.map((item) => (
          <button
            key={item.id}
            onClick={() => onToggle(item.id)}
            className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-bg-secondary transition-colors"
            style={{ minHeight: '44px' }}
          >
            {checked.has(item.id) ? (
              <CheckSquare className="w-5 h-5 shrink-0 mt-0.5 text-accent-primary" />
            ) : (
              <Square className="w-5 h-5 shrink-0 mt-0.5 text-text-muted" />
            )}
            <span
              className={`text-sm leading-relaxed ${
                checked.has(item.id) ? 'text-text-muted line-through' : 'text-text-primary'
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
