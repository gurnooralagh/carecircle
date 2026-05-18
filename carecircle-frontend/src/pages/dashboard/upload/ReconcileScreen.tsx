import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle, XCircle } from 'lucide-react'
import { SkeletonList } from '../../../components/ui/SkeletonCard'
import { Button } from '../../../components/ui/Button'
import { PageTransition } from '../../../components/ui/PageTransition'
import api from '../../../lib/api'
import { usePatientStore } from '../../../store/patient'
import { useToast } from '../../../store/toast'
import type { MedicationReconciliation, NewMedicationReconcile } from '../../../types'

type GuardianAction = 'still_taking' | 'stopped' | 'held' | 'not_sure'

const TRANSITION_CONFIG: Record<string, { label: string; bg: string; color: string; defaultGuardian: GuardianAction }> = {
  added:              { label: 'NEW',            bg: '#F0F9FF', color: '#0891B2', defaultGuardian: 'still_taking' },
  removed:            { label: 'REMOVED',        bg: '#FEF2F2', color: '#DC2626', defaultGuardian: 'stopped' },
  dose_changed:       { label: 'DOSE CHANGED',   bg: '#FFFBEB', color: '#D97706', defaultGuardian: 'still_taking' },
  frequency_changed:  { label: 'FREQ CHANGED',   bg: '#FFFBEB', color: '#D97706', defaultGuardian: 'still_taking' },
  restarted:          { label: 'RESTARTED',      bg: '#F0FDF4', color: '#16A34A', defaultGuardian: 'still_taking' },
}

const GUARDIAN_LABELS: { key: GuardianAction; label: string }[] = [
  { key: 'still_taking', label: 'Still taking' },
  { key: 'stopped',      label: 'Stopped' },
  { key: 'held',         label: 'On hold' },
  { key: 'not_sure',     label: 'Not sure' },
]

export function ReconcileScreen() {
  const { uploadEventId } = useParams<{ uploadEventId: string }>()
  const navigate = useNavigate()
  const { patient_id } = usePatientStore()
  const toast = useToast()

  const [actions, setActions] = useState<Record<string, 'confirm' | 'remove'>>({})
  const [guardianActions, setGuardianActions] = useState<Record<string, GuardianAction>>({})
  const [submitting, setSubmitting] = useState(false)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['medication-reconciliation', patient_id, uploadEventId],
    queryFn: async () => {
      const res = await api.get(
        `/api/longitudinal/medication_reconciliation/${patient_id}/${uploadEventId}`
      )
      return res.data as MedicationReconciliation
    },
    enabled: !!patient_id && !!uploadEventId,
    retry: 2,
  })

  const getAction = (id: string): 'confirm' | 'remove' => actions[id] ?? 'confirm'
  const getGuardianAction = (id: string, type: string): GuardianAction =>
    guardianActions[id] ?? (TRANSITION_CONFIG[type]?.defaultGuardian ?? 'still_taking')

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      const confirmations = (data?.newly_extracted_medications ?? []).map((t) => ({
        transition_id: t.transition_id,
        action: getAction(t.transition_id),
        guardian_action: getGuardianAction(t.transition_id, t.transition_type),
      }))

      await api.post(
        `/api/longitudinal/confirm_reconciliation/${patient_id}/${uploadEventId}`,
        { confirmations }
      )

      navigate(`/dashboard/upload/processing/${uploadEventId}`)
    } catch {
      toast.error('Could not submit reconciliation. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const transitions = data?.newly_extracted_medications ?? []
  const continuedCount = data?.continued_medications ?? 0

  return (
    <PageTransition className="px-4 py-6 max-w-xl mx-auto">
      <h2
        className="text-2xl font-normal text-text-primary mb-1"
        style={{ fontFamily: 'Fraunces, serif' }}
      >
        Review medication changes
      </h2>
      <p className="text-sm text-text-secondary mb-8">
        These changes were detected in your uploaded documents. Confirm or reject each one.
      </p>

      {isLoading && <SkeletonList count={3} />}

      {isError && (
        <div className="bg-[#FEF2F2] border border-[#DC262630] rounded-xl p-5 text-center mb-4">
          <p className="text-sm font-semibold text-severity-critical mb-1">Couldn't load medication changes</p>
          <p className="text-sm text-severity-critical opacity-80 mb-4">Something went wrong. Please try again.</p>
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
          {transitions.length === 0 ? (
            <div className="bg-bg-card border border-border rounded-xl p-5 text-center mb-6">
              <p className="text-base font-semibold text-text-primary mb-1">No medication changes detected</p>
              <p className="text-sm text-text-secondary">
                {continuedCount > 0
                  ? `${continuedCount} medication${continuedCount !== 1 ? 's' : ''} continuing unchanged.`
                  : 'No changes were found in the uploaded documents.'}
              </p>
            </div>
          ) : (
            <>
              {continuedCount > 0 && (
                <p className="text-xs text-text-muted mb-4">
                  {continuedCount} medication{continuedCount !== 1 ? 's' : ''} continuing unchanged
                </p>
              )}
              <div className="flex flex-col gap-4 mb-6">
                {transitions.map((t) => (
                  <TransitionCard
                    key={t.transition_id}
                    transition={t}
                    action={getAction(t.transition_id)}
                    guardianAction={getGuardianAction(t.transition_id, t.transition_type)}
                    onActionChange={(a) => setActions((p) => ({ ...p, [t.transition_id]: a }))}
                    onGuardianActionChange={(a) => setGuardianActions((p) => ({ ...p, [t.transition_id]: a }))}
                  />
                ))}
              </div>
            </>
          )}
        </>
      )}

      <Button fullWidth size="lg" loading={submitting} disabled={isLoading} onClick={handleSubmit}>
        Continue
      </Button>
    </PageTransition>
  )
}

function TransitionCard({
  transition,
  action,
  guardianAction,
  onActionChange,
  onGuardianActionChange,
}: {
  transition: NewMedicationReconcile
  action: 'confirm' | 'remove'
  guardianAction: GuardianAction
  onActionChange: (a: 'confirm' | 'remove') => void
  onGuardianActionChange: (a: GuardianAction) => void
}) {
  const config = TRANSITION_CONFIG[transition.transition_type] ?? {
    label: transition.transition_type.replace(/_/g, ' ').toUpperCase(),
    bg: '#F9FAFB',
    color: '#6B7280',
    defaultGuardian: 'still_taking' as GuardianAction,
  }
  const isRejected = action === 'remove'
  const drugName = transition.drug_name_brand || transition.drug_name_generic || 'Unknown medication'

  let doseInfo: string | null = null
  const type = transition.transition_type
  if (type === 'added' || type === 'restarted') {
    const parts = [transition.new_dose_mg, transition.new_frequency].filter(Boolean)
    doseInfo = parts.join(' · ') || null
  } else if (type === 'removed') {
    const parts = [transition.prior_dose_mg, transition.prior_frequency].filter(Boolean)
    doseInfo = parts.join(' · ') || null
  } else if (type === 'dose_changed') {
    const before = transition.prior_dose_mg ?? '?'
    const after = transition.new_dose_mg ?? '?'
    doseInfo = `${before} → ${after}`
    if (transition.new_frequency) doseInfo += ` · ${transition.new_frequency}`
  } else if (type === 'frequency_changed') {
    const before = transition.prior_frequency ?? '?'
    const after = transition.new_frequency ?? '?'
    doseInfo = `${before} → ${after}`
    if (transition.new_dose_mg) doseInfo = `${transition.new_dose_mg} · ${doseInfo}`
  }

  return (
    <div
      className={`bg-bg-card border rounded-xl p-4 transition-opacity ${isRejected ? 'opacity-50 border-border' : 'border-border'}`}
      style={!isRejected ? { borderLeft: `4px solid ${config.color}` } : undefined}
    >
      {/* Header */}
      <div className="mb-3">
        <span
          className="text-xs font-semibold px-2 py-0.5 rounded-full inline-block mb-1.5"
          style={{ backgroundColor: config.bg, color: config.color }}
        >
          {config.label}
        </span>
        <p className="text-base font-semibold text-text-primary">{drugName}</p>
        {transition.drug_name_generic && transition.drug_name_brand && (
          <p className="text-sm text-text-muted">{transition.drug_name_generic}</p>
        )}
        {doseInfo && <p className="text-sm text-text-secondary mt-0.5">{doseInfo}</p>}
        {transition.source_document && (
          <p className="text-xs text-text-muted mt-1">From: {transition.source_document}</p>
        )}
      </div>

      {/* Guardian status — only shown when confirming */}
      {!isRejected && (
        <div className="flex flex-wrap gap-2 mb-3">
          {GUARDIAN_LABELS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => onGuardianActionChange(key)}
              className={`px-3 h-8 rounded-lg text-xs font-medium border transition-colors ${
                guardianAction === key
                  ? 'bg-accent-primary text-white border-accent-primary'
                  : 'bg-bg-secondary border-border text-text-secondary hover:bg-border'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Confirm / Reject */}
      <div className="flex gap-2">
        <button
          onClick={() => onActionChange('confirm')}
          className={`flex-1 h-9 rounded-lg text-sm font-medium border flex items-center justify-center gap-1.5 transition-colors ${
            !isRejected
              ? 'bg-[#F0FDF4] text-[#16A34A] border-[#16A34A40]'
              : 'bg-bg-secondary border-border text-text-secondary hover:bg-border'
          }`}
        >
          <CheckCircle className="w-4 h-4" />
          Confirm
        </button>
        <button
          onClick={() => onActionChange('remove')}
          className={`flex-1 h-9 rounded-lg text-sm font-medium border flex items-center justify-center gap-1.5 transition-colors ${
            isRejected
              ? 'bg-[#FEF2F2] text-[#DC2626] border-[#DC262640]'
              : 'bg-bg-secondary border-border text-text-secondary hover:bg-border'
          }`}
        >
          <XCircle className="w-4 h-4" />
          Reject
        </button>
      </div>
    </div>
  )
}
