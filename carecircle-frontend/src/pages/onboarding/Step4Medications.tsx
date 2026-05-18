import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Pill, ChevronDown, ChevronUp } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { SkeletonList } from '../../components/ui/SkeletonCard'
import { EmptyState } from '../../components/ui/EmptyState'
import { PageTransition } from '../../components/ui/PageTransition'
import api from '../../lib/api'
import { usePatientStore } from '../../store/patient'
import { useToast } from '../../store/toast'
import type { Medication } from '../../types'

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
interface Step4MedicationsProps {}

type TakingStatus = 'yes_currently_taking' | 'no_stopped' | 'not_sure'

interface MedState {
  dose: string
  frequency: string
  takingStatus: TakingStatus | null
  showFixName: boolean
  editedName: string
}

export function Step4Medications(_props: Step4MedicationsProps) {
  const navigate = useNavigate()
  const { patient_id } = usePatientStore()
  const toast = useToast()
  const [medStates, setMedStates] = useState<Record<string, MedState>>({})
  const [submitting, setSubmitting] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['onboarding-medications', patient_id],
    queryFn: async () => {
      const res = await api.get(`/api/onboarding/extracted_medications/${patient_id}`)
      return res.data as { medications: Medication[] }
    },
    enabled: !!patient_id,
  })

  const medications = data?.medications ?? []

  const getMedState = (med: Medication): MedState => {
    return medStates[med.medication_id] ?? {
      dose: med.dose_text ?? med.dosage ?? '',
      frequency: med.frequency ?? '',
      takingStatus: null,
      showFixName: false,
      editedName: '',
    }
  }

  const updateMedState = (id: string, updates: Partial<MedState>) => {
    setMedStates((prev) => {
      // If already initialised, merge directly — avoids wiping dose/frequency on first click
      if (prev[id]) {
        return { ...prev, [id]: { ...prev[id], ...updates } }
      }
      // Seed from the original medication data on first interaction
      const med = medications.find((m) => m.medication_id === id)
      const base: MedState = {
        dose: med?.dose_text ?? med?.dosage ?? '',
        frequency: med?.frequency ?? '',
        takingStatus: null,
        showFixName: false,
        editedName: '',
      }
      return { ...prev, [id]: { ...base, ...updates } }
    })
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      const confirmed_medications = medications.map((med) => {
        const state = getMedState(med)
        const takingStatus = state.takingStatus ?? 'not_sure'
        const action = takingStatus === 'no_stopped'
          ? 'remove'
          : state.editedName.trim()
          ? 'edit'
          : 'confirm'

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const entry: any = {
          medication_id: med.medication_id,
          action,
          guardian_taking_status: takingStatus,
          guardian_confirmed_dose_text: state.dose || undefined,
          guardian_confirmed_frequency: state.frequency || undefined,
        }

        if (action === 'edit' && state.editedName.trim()) {
          entry.updated_fields = { drug_name_brand: state.editedName.trim() }
        }

        return entry
      })

      await api.post(`/api/onboarding/confirm_medications/${patient_id}`, {
        confirmed_medications,
        added_medications: [],
      })
      navigate('/onboarding/analysis')
    } catch {
      toast.error('Could not confirm medications. Please try again.')
    } finally {
      setSubmitting(false)
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

      <PageTransition className="flex-1 max-w-xl mx-auto w-full px-4 py-8 pb-12">
      <h2
        className="text-2xl font-normal text-text-primary mb-1"
        style={{ fontFamily: 'Fraunces, serif' }}
      >
        Review medications
      </h2>
      <p className="text-sm text-text-secondary mb-8">
        We extracted these from your documents. Please verify and correct if needed.
      </p>

      {isLoading && <SkeletonList count={3} />}

      {error && (
        <div className="bg-[#FEF2F2] border border-[#DC2626] rounded-xl p-4 text-sm text-severity-critical mb-4">
          Could not load medications. You can continue and review them later.
        </div>
      )}

      {!isLoading && medications.length === 0 && (
        <EmptyState
          icon={Pill}
          title="No medications found"
          description="We couldn't extract medications from your documents. You can add them manually from the dashboard later."
        />
      )}

      {!isLoading && medications.length > 0 && (
        <div className="flex flex-col gap-3 mb-6">
          {medications.map((med) => {
            const state = getMedState(med)
            const drugName = med.drug_name_brand ?? med.drug_name ?? 'Unknown'
            const genericName = med.drug_name_generic
            const showGeneric = genericName && genericName !== drugName

            return (
              <div
                key={med.medication_id}
                className="bg-bg-card rounded-xl border border-border shadow-sm p-4"
              >
                {/* Drug name */}
                <div className="mb-3">
                  <p className="text-base font-semibold text-text-primary">
                    {drugName}
                    {showGeneric && (
                      <span className="text-sm font-normal text-text-secondary ml-1">
                        ({genericName})
                      </span>
                    )}
                  </p>
                </div>

                {/* Dose & Frequency inputs */}
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div>
                    <label className="block text-xs font-medium text-text-muted mb-1">Dose</label>
                    <input
                      type="text"
                      value={state.dose}
                      onChange={(e) =>
                        updateMedState(med.medication_id, { dose: e.target.value })
                      }
                      placeholder="e.g. 500mg"
                      className="w-full h-9 rounded-lg border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent-primary transition-colors"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-text-muted mb-1">Frequency</label>
                    <input
                      type="text"
                      value={state.frequency}
                      onChange={(e) =>
                        updateMedState(med.medication_id, { frequency: e.target.value })
                      }
                      placeholder="e.g. twice daily"
                      className="w-full h-9 rounded-lg border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent-primary transition-colors"
                    />
                  </div>
                </div>

                {/* Currently taking? */}
                <div className="mb-3">
                  <p className="text-xs font-medium text-text-muted mb-1.5">Currently taking?</p>
                  <div className="flex gap-2">
                    {(
                      [
                        { value: 'yes_currently_taking', label: '✓ Yes' },
                        { value: 'no_stopped', label: '✗ No' },
                        { value: 'not_sure', label: '? Not sure' },
                      ] as { value: TakingStatus; label: string }[]
                    ).map(({ value, label }) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() =>
                          updateMedState(med.medication_id, { takingStatus: value })
                        }
                        className={`flex-1 h-8 rounded-lg border text-xs font-medium transition-all ${
                          state.takingStatus === value
                            ? 'bg-accent-primary border-accent-primary text-white ring-2 ring-accent-primary ring-offset-1'
                            : 'border-border text-text-secondary hover:border-accent-primary hover:text-accent-primary'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Fix name toggle */}
                <button
                  type="button"
                  onClick={() =>
                    updateMedState(med.medication_id, {
                      showFixName: !state.showFixName,
                    })
                  }
                  className="flex items-center gap-1 text-xs text-text-muted hover:text-text-primary transition-colors"
                >
                  {state.showFixName ? (
                    <ChevronUp className="w-3 h-3" />
                  ) : (
                    <ChevronDown className="w-3 h-3" />
                  )}
                  Fix name
                </button>

                {state.showFixName && (
                  <div className="mt-2">
                    <input
                      type="text"
                      value={state.editedName}
                      onChange={(e) =>
                        updateMedState(med.medication_id, { editedName: e.target.value })
                      }
                      placeholder={`Correct name (currently: ${drugName})`}
                      className="w-full h-9 rounded-lg border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent-primary transition-colors"
                    />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <Button
        onClick={handleSubmit}
        fullWidth
        size="lg"
        loading={submitting}
        disabled={isLoading}
      >
        Continue to analysis
      </Button>
      </PageTransition>
    </div>
  )
}
