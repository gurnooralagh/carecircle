import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { SkeletonList } from '../../../components/ui/SkeletonCard'
import { Button } from '../../../components/ui/Button'
import { PageTransition } from '../../../components/ui/PageTransition'
import api from '../../../lib/api'
import { usePatientStore } from '../../../store/patient'
import { useToast } from '../../../store/toast'
import type { MedicationReconciliation, NewMedicationReconcile, ExistingMedicationReconcile } from '../../../types'

type GuardianAction = 'still_taking' | 'stopped' | 'not_sure'

const CONTEXT_MSG: Record<string, (t: NewMedicationReconcile) => string> = {
  added:              (t) => `We can see this medication was added in the new documents${t.source_document ? ` (${t.source_document})` : ''}.`,
  removed:            (t) => `We did not find ${t.drug_name_brand || t.drug_name_generic || 'this medication'} in the new documents. Are they still taking it?`,
  dose_changed:       (t) => `The dosage for this medication has changed${t.prior_dose_mg ? ` from ${t.prior_dose_mg}` : ''}${t.new_dose_mg ? ` to ${t.new_dose_mg}` : ''}.`,
  frequency_changed:  (t) => `The frequency for this medication has changed${t.prior_frequency ? ` from ${t.prior_frequency}` : ''}${t.new_frequency ? ` to ${t.new_frequency}` : ''}.`,
  restarted:          () => `This medication appears to have been restarted in the new documents.`,
}

const CONTEXT_BG: Record<string, string> = {
  added:             '#f0fdf4',
  removed:           '#fef9c3',
  dose_changed:      '#eff6ff',
  frequency_changed: '#eff6ff',
  restarted:         '#f0fdf4',
}

const DEFAULT_GUARDIAN: Record<string, GuardianAction> = {
  added:             'still_taking',
  removed:           'stopped',
  dose_changed:      'still_taking',
  frequency_changed: 'still_taking',
  restarted:         'still_taking',
}

export function ReconcileScreen() {
  const { uploadEventId } = useParams<{ uploadEventId: string }>()
  const navigate = useNavigate()
  const { patient_id } = usePatientStore()
  const toast = useToast()

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

  const getGuardianAction = (id: string, type: string): GuardianAction =>
    guardianActions[id] ?? (DEFAULT_GUARDIAN[type] ?? 'still_taking')

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      const confirmations = (data?.newly_extracted_medications ?? []).map((t) => ({
        transition_id: t.transition_id,
        action: 'confirm' as const,
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
  const existingMeds = data?.existing_medications ?? []
  const continuedCount = data?.continued_medications ?? 0

  return (
    <PageTransition className="px-4 py-6 max-w-xl mx-auto">
      <h2
        className="text-2xl font-normal text-text-primary mb-1"
        style={{ fontFamily: 'Fraunces, serif' }}
      >
        Review medications
      </h2>
      <p className="text-sm text-text-secondary mb-6">
        We compared your new documents with existing records. Confirm what's changed.
      </p>

      {isLoading && <SkeletonList count={3} />}

      {isError && (
        <div className="bg-[#FEF2F2] border border-[#DC262630] rounded-xl p-5 text-center mb-4">
          <p className="text-sm font-semibold text-severity-critical mb-1">Couldn't load medication changes</p>
          <p className="text-sm text-severity-critical opacity-80 mb-4">Something went wrong. Please try again.</p>
          <button
            onClick={() => refetch()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-[#DC262630] text-severity-critical text-sm font-medium"
          >
            Try again
          </button>
        </div>
      )}

      {!isLoading && !isError && data && (
        <>
          {/* Section 1: Active medications */}
          {existingMeds.length > 0 && (
            <div className="mb-6">
              <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">
                Active medications ({existingMeds.length})
              </h3>
              <div className="flex flex-col gap-2">
                {existingMeds.map((med) => (
                  <ExistingMedRow key={med.medication_id} med={med} />
                ))}
              </div>
            </div>
          )}

          {/* Section 2: New & changed */}
          <div className="mb-6">
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-3">
              New &amp; changed medications
            </h3>

            {transitions.length === 0 ? (
              <div className="bg-bg-card border border-border rounded-xl p-5 text-center">
                <p className="text-base font-semibold text-text-primary mb-1">No changes detected</p>
                <p className="text-sm text-text-secondary">
                  {continuedCount > 0
                    ? `${continuedCount} medication${continuedCount !== 1 ? 's' : ''} found — all match existing records with no changes.`
                    : 'No new or changed medications were found in the uploaded documents.'}
                </p>
              </div>
            ) : (
              <>
                {continuedCount > 0 && (
                  <p className="text-xs text-text-muted mb-3">
                    {continuedCount} medication{continuedCount !== 1 ? 's' : ''} matched existing records unchanged.
                  </p>
                )}
                <div className="flex flex-col gap-4">
                  {transitions.map((t) => (
                    <TransitionCard
                      key={t.transition_id}
                      transition={t}
                      guardianAction={getGuardianAction(t.transition_id, t.transition_type)}
                      onGuardianActionChange={(a) =>
                        setGuardianActions((p) => ({ ...p, [t.transition_id]: a }))
                      }
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        </>
      )}

      <Button fullWidth size="lg" loading={submitting} disabled={isLoading} onClick={handleSubmit}>
        Confirm &amp; continue
      </Button>
    </PageTransition>
  )
}

function ExistingMedRow({ med }: { med: ExistingMedicationReconcile }) {
  const name = med.drug_name_brand || med.drug_name_generic || 'Unknown'
  const generic =
    med.drug_name_generic && med.drug_name_generic !== name ? med.drug_name_generic : null
  const doseInfo = [med.dose_text, med.frequency].filter(Boolean).join(' · ')

  return (
    <div className="bg-bg-card border border-border rounded-xl px-4 py-3 flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-text-primary">
          {name}
          {generic && (
            <span className="text-xs font-normal text-text-muted ml-1">({generic})</span>
          )}
        </p>
        {doseInfo && <p className="text-xs text-text-secondary mt-0.5">{doseInfo}</p>}
      </div>
      <span className="text-xs px-2 py-1 rounded-full bg-[#F0FDF4] text-[#16A34A] font-medium flex-shrink-0">
        Active
      </span>
    </div>
  )
}

function TransitionCard({
  transition,
  guardianAction,
  onGuardianActionChange,
}: {
  transition: NewMedicationReconcile
  guardianAction: GuardianAction
  onGuardianActionChange: (a: GuardianAction) => void
}) {
  const drugName =
    transition.drug_name_brand || transition.drug_name_generic || 'Unknown medication'
  const genericName =
    transition.drug_name_generic && transition.drug_name_brand
      ? transition.drug_name_generic
      : null
  const contextMsg =
    CONTEXT_MSG[transition.transition_type]?.(transition) ??
    `Change detected: ${transition.transition_type.replace(/_/g, ' ')}`
  const contextBg = CONTEXT_BG[transition.transition_type] ?? '#eff6ff'

  return (
    <div className="bg-bg-card border border-border rounded-xl p-4">
      {/* Context message */}
      <p
        className="text-xs text-[#374151] rounded-lg px-3 py-2 mb-3 leading-relaxed"
        style={{ backgroundColor: contextBg }}
      >
        {contextMsg}
      </p>

      {/* Drug name */}
      <div className="mb-3">
        <p className="text-base font-semibold text-text-primary">
          {drugName}
          {genericName && (
            <span className="text-sm font-normal text-text-muted ml-1">({genericName})</span>
          )}
        </p>
        {transition.source_document && (
          <p className="text-xs text-text-muted mt-0.5">From: {transition.source_document}</p>
        )}
      </div>

      {/* Currently taking? */}
      <div>
        <p className="text-xs font-medium text-text-muted mb-1.5">Currently taking?</p>
        <div className="flex gap-2">
          {(
            [
              { value: 'still_taking', label: '✓ Yes' },
              { value: 'stopped',      label: '✗ No' },
              { value: 'not_sure',     label: '? Not sure' },
            ] as { value: GuardianAction; label: string }[]
          ).map(({ value, label }) => (
            <button
              key={value}
              type="button"
              onClick={() => onGuardianActionChange(value)}
              className={`flex-1 h-8 rounded-lg border text-xs font-medium transition-all ${
                guardianAction === value
                  ? 'bg-accent-primary border-accent-primary text-white ring-2 ring-accent-primary ring-offset-1'
                  : 'border-border text-text-secondary hover:border-accent-primary hover:text-accent-primary'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
