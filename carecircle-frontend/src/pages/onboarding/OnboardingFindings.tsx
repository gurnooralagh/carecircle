import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ShieldCheck, RefreshCw } from 'lucide-react'
import { ConcernCard } from '../../components/ConcernCard'
import { Button } from '../../components/ui/Button'
import { SkeletonList } from '../../components/ui/SkeletonCard'
import { EmptyState } from '../../components/ui/EmptyState'
import { PageTransition } from '../../components/ui/PageTransition'
import api from '../../lib/api'
import { usePatientStore } from '../../store/patient'
import { useToast } from '../../store/toast'
import type { FindingsResponse } from '../../types'

const PRIORITY_ORDER = ['critical_concern', 'high_priority', 'moderate', 'for_your_awareness']

export function OnboardingFindings() {
  const navigate = useNavigate()
  const { patient_id, patient_name } = usePatientStore()
  const toast = useToast()
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['onboarding-findings', patient_id],
    queryFn: async () => {
      const res = await api.get(`/api/onboarding/findings/${patient_id}`)
      return res.data as FindingsResponse
    },
    enabled: !!patient_id,
    retry: 2,
    refetchInterval: (query) =>
      query.state.data?.status === 'ready' ? false : 3000,
  })

  const handleRerunAnalysis = async () => {
    try {
      await api.post(`/api/onboarding/rerun_analysis/${patient_id}`)
      toast.success('Re-running analysis. This takes 2–3 minutes.')
      navigate('/onboarding/analysis')
    } catch {
      toast.error('Could not restart analysis. Please try again.')
    }
  }

  const concerns = data?.concerns ?? []
  const concernSummary = data?.concern_summary

  const sorted = [...concerns].sort((a, b) => {
    return (
      PRIORITY_ORDER.indexOf(a.priority) - PRIORITY_ORDER.indexOf(b.priority)
    )
  })

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
          Here's what we found{patient_name ? ` for ${patient_name}` : ''}
        </h2>

        {concernSummary && (
          <div className="flex flex-wrap gap-3 mt-3 mb-6">
            {(concernSummary.critical_concern ?? 0) > 0 && (
              <SummaryPill
                label={`${concernSummary.critical_concern} critical concern${concernSummary.critical_concern !== 1 ? 's' : ''}`}
                color="#DC2626"
                bg="#FEF2F2"
              />
            )}
            {(concernSummary.high_priority ?? 0) > 0 && (
              <SummaryPill
                label={`${concernSummary.high_priority} high priority`}
                color="#EA580C"
                bg="#FFF7ED"
              />
            )}
            {(concernSummary.moderate ?? 0) > 0 && (
              <SummaryPill
                label={`${concernSummary.moderate} need attention`}
                color="#D97706"
                bg="#FFFBEB"
              />
            )}
            {(concernSummary.for_your_awareness ?? 0) > 0 && (
              <SummaryPill
                label={`${concernSummary.for_your_awareness} for your awareness`}
                color="#6B7280"
                bg="#F9FAFB"
              />
            )}
          </div>
        )}

        {(isLoading || data?.status === 'running') && <SkeletonList count={4} />}

        {isError && (
          <div className="bg-[#FEF2F2] border border-[#DC262630] rounded-xl p-5 text-center mb-4">
            <p className="text-sm font-semibold text-severity-critical mb-1">Couldn't load findings</p>
            <p className="text-sm text-severity-critical opacity-80 mb-4">
              The analysis may have saved incorrectly or not finished. You can retry fetching, or re-run the full analysis.
            </p>
            <div className="flex flex-col gap-2">
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                <RefreshCw className="w-4 h-4" />
                Retry fetching
              </Button>
              <Button variant="ghost" size="sm" onClick={handleRerunAnalysis} className="text-severity-critical hover:bg-[#FEF2F2]">
                Re-run analysis from scratch
              </Button>
            </div>
          </div>
        )}

        {!isLoading && !isError && data?.status === 'ready' && sorted.length === 0 && (
          <EmptyState
            icon={ShieldCheck}
            title="Nothing concerning found"
            description="Great news — we didn't identify any issues with the documents you provided."
          />
        )}

        {!isLoading && data?.status === 'ready' && sorted.length > 0 && (
          <div className="flex flex-col gap-3 mb-8">
            {sorted.map((c) => (
              <ConcernCard key={c.id ?? c.title} concern={c} />
            ))}
          </div>
        )}

        <Button
          onClick={() => navigate('/onboarding/checklist')}
          fullWidth
          size="lg"
          disabled={isLoading || data?.status !== 'ready'}
        >
          Continue to action plan
        </Button>
      </PageTransition>
    </div>
  )
}

function SummaryPill({
  label,
  color,
  bg,
}: {
  label: string
  color: string
  bg: string
}) {
  return (
    <span
      className="inline-flex px-3 py-1 rounded-full text-sm font-medium"
      style={{ color, backgroundColor: bg }}
    >
      {label}
    </span>
  )
}
