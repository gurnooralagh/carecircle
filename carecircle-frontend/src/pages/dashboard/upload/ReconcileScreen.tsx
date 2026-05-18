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

// ─── Merged card structure ────────────────────────────────────────────────────

interface MergedCard {
  key: string
  // Display
  displayName: string
  genericName: string | null
  sourceDocument: string | null
  // Editable fields (seeded from transition or existing med)
  initialDose: string
  initialFrequency: string
  // Prompt
  contextMsg: string
  contextBg: string
  // Submission (only present when there's a transition)
  transitionId: string | null
  defaultGuardianAction: GuardianAction
}

// ─── Build merged list ────────────────────────────────────────────────────────

function normName(s: string | undefined | null): string {
  return (s || '').toLowerCase().trim()
}

function matchesExisting(
  t: NewMedicationReconcile,
  med: ExistingMedicationReconcile,
): boolean {
  const tb = normName(t.drug_name_brand)
  const tg = normName(t.drug_name_generic)
  const mb = normName(med.drug_name_brand)
  const mg = normName(med.drug_name_generic)
  return !!(
    (tb && mb && tb === mb) ||
    (tg && mg && tg === mg) ||
    (tb && mg && tb === mg) ||
    (tg && mb && tg === mb)
  )
}

function buildCards(
  existing: ExistingMedicationReconcile[],
  transitions: NewMedicationReconcile[],
): MergedCard[] {
  const usedTransitionIds = new Set<string>()
  const cards: MergedCard[] = []

  // 1. One card per existing med — find matching transition if any
  for (const med of existing) {
    const matched = transitions.find((t) => {
      if (usedTransitionIds.has(t.transition_id)) return false
      return matchesExisting(t, med)
    })
    if (matched) usedTransitionIds.add(matched.transition_id)

    const displayName = med.drug_name_brand || med.drug_name_generic || 'Unknown'
    const genericName =
      med.drug_name_generic && med.drug_name_generic !== displayName
        ? med.drug_name_generic
        : null

    let contextMsg: string
    let contextBg: string
    let defaultGuardian: GuardianAction = 'still_taking'

    if (!matched) {
      contextMsg = 'This was not found in your new documents. Are you still taking it?'
      contextBg = '#FFF7ED'
    } else if (matched.transition_type === 'removed') {
      contextMsg = 'This was asked to stop in your documents. Are you still taking it?'
      contextBg = '#FEF9C3'
      defaultGuardian = 'stopped'
    } else if (matched.transition_type === 'dose_changed') {
      const from = matched.prior_dose_mg ?? '?'
      const to = matched.new_dose_mg ?? '?'
      contextMsg = `Same medication but dosage changed from ${from} to ${to}.`
      contextBg = '#EFF6FF'
    } else if (matched.transition_type === 'frequency_changed') {
      const from = matched.prior_frequency ?? '?'
      const to = matched.new_frequency ?? '?'
      contextMsg = `Same medication but frequency changed from ${from} to ${to}.`
      contextBg = '#EFF6FF'
    } else if (matched.transition_type === 'restarted') {
      contextMsg = 'This medication appears to have been restarted in your documents.'
      contextBg = '#F0FDF4'
    } else {
      contextMsg = 'This appears to be the same as in your records. Are you still taking it?'
      contextBg = '#F9FAFB'
    }

    cards.push({
      key: `existing-${med.medication_id}`,
      displayName,
      genericName,
      sourceDocument: matched?.source_document ?? null,
      initialDose: matched?.new_dose_mg ?? med.dose_text ?? '',
      initialFrequency: matched?.new_frequency ?? med.frequency ?? '',
      contextMsg,
      contextBg,
      transitionId: matched?.transition_id ?? null,
      defaultGuardianAction: defaultGuardian,
    })
  }

  // 2. Added transitions not matched to any existing med
  for (const t of transitions) {
    if (usedTransitionIds.has(t.transition_id)) continue
    if (t.transition_type !== 'added' && t.transition_type !== 'restarted') continue

    const displayName = t.drug_name_brand || t.drug_name_generic || 'Unknown'
    const genericName =
      t.drug_name_generic && t.drug_name_generic !== displayName
        ? t.drug_name_generic
        : null

    cards.push({
      key: `new-${t.transition_id}`,
      displayName,
      genericName,
      sourceDocument: t.source_document ?? null,
      initialDose: t.new_dose_mg ?? '',
      initialFrequency: t.new_frequency ?? '',
      contextMsg: 'This is a new medication found in your documents.',
      contextBg: '#F0FDF4',
      transitionId: t.transition_id,
      defaultGuardianAction: 'still_taking',
    })
    usedTransitionIds.add(t.transition_id)
  }

  return cards
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ReconcileScreen() {
  const { uploadEventId } = useParams<{ uploadEventId: string }>()
  const navigate = useNavigate()
  const { patient_id } = usePatientStore()
  const toast = useToast()

  const [guardianActions, setGuardianActions] = useState<Record<string, GuardianAction>>({})
  const [doses, setDoses] = useState<Record<string, string>>({})
  const [frequencies, setFrequencies] = useState<Record<string, string>>({})
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

  const cards = data
    ? buildCards(data.existing_medications ?? [], data.newly_extracted_medications ?? [])
    : []

  const getGuardian = (card: MergedCard): GuardianAction =>
    guardianActions[card.key] ?? card.defaultGuardianAction

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      // Only submit cards that have a transition_id
      const confirmations = cards
        .filter((c) => c.transitionId)
        .map((c) => ({
          transition_id: c.transitionId!,
          action: 'confirm' as const,
          guardian_action: getGuardian(c),
          new_dose_mg: doses[c.key] || undefined,
          new_frequency: frequencies[c.key] || undefined,
        }))

      await api.post(
        `/api/longitudinal/confirm_reconciliation/${patient_id}/${uploadEventId}`,
        { confirmations }
      )
      navigate(`/dashboard/upload/processing/${uploadEventId}`)
    } catch {
      toast.error('Could not submit. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PageTransition className="px-4 py-6 max-w-xl mx-auto">
      <h2
        className="text-2xl font-normal text-text-primary mb-1"
        style={{ fontFamily: 'Fraunces, serif' }}
      >
        Your medications
      </h2>
      <p className="text-sm text-text-secondary mb-6">
        Tell us which medications you are still taking and which you have stopped.
      </p>

      {isLoading && <SkeletonList count={3} />}

      {isError && (
        <div className="bg-[#FEF2F2] border border-[#DC262630] rounded-xl p-5 text-center mb-4">
          <p className="text-sm font-semibold text-severity-critical mb-1">
            Couldn't load medications
          </p>
          <p className="text-sm text-severity-critical opacity-80 mb-4">
            Something went wrong. Please try again.
          </p>
          <button
            onClick={() => refetch()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-[#DC262630] text-severity-critical text-sm font-medium"
          >
            Try again
          </button>
        </div>
      )}

      {!isLoading && !isError && data && (
        <div className="flex flex-col gap-4 mb-6">
          {cards.length === 0 ? (
            <div className="bg-bg-card border border-border rounded-xl p-5 text-center">
              <p className="text-base font-semibold text-text-primary mb-1">No medications found</p>
              <p className="text-sm text-text-secondary">
                No medications were recorded or extracted from your documents.
              </p>
            </div>
          ) : (
            cards.map((card) => (
              <MedCard
                key={card.key}
                card={card}
                guardianAction={getGuardian(card)}
                dose={doses[card.key] ?? card.initialDose}
                frequency={frequencies[card.key] ?? card.initialFrequency}
                onGuardianChange={(a) =>
                  setGuardianActions((p) => ({ ...p, [card.key]: a }))
                }
                onDoseChange={(v) => setDoses((p) => ({ ...p, [card.key]: v }))}
                onFrequencyChange={(v) => setFrequencies((p) => ({ ...p, [card.key]: v }))}
              />
            ))
          )}
        </div>
      )}

      <Button fullWidth size="lg" loading={submitting} disabled={isLoading} onClick={handleSubmit}>
        Confirm &amp; continue
      </Button>
    </PageTransition>
  )
}

// ─── Med card ─────────────────────────────────────────────────────────────────

function MedCard({
  card,
  guardianAction,
  dose,
  frequency,
  onGuardianChange,
  onDoseChange,
  onFrequencyChange,
}: {
  card: MergedCard
  guardianAction: GuardianAction
  dose: string
  frequency: string
  onGuardianChange: (a: GuardianAction) => void
  onDoseChange: (v: string) => void
  onFrequencyChange: (v: string) => void
}) {
  const isStopped = guardianAction === 'stopped'

  return (
    <div
      className={`bg-bg-card border border-border rounded-xl p-4 transition-opacity ${
        isStopped ? 'opacity-50' : ''
      }`}
    >
      {/* Context prompt */}
      <p
        className="text-xs text-[#374151] rounded-lg px-3 py-2 mb-3 leading-relaxed"
        style={{ backgroundColor: card.contextBg }}
      >
        {card.contextMsg}
      </p>

      {/* Drug name */}
      <div className="mb-3">
        <p className="text-base font-semibold text-text-primary">
          {card.displayName}
          {card.genericName && (
            <span className="text-sm font-normal text-text-muted ml-1">
              ({card.genericName})
            </span>
          )}
        </p>
        {card.sourceDocument && (
          <p className="text-xs text-text-muted mt-0.5">From: {card.sourceDocument}</p>
        )}
      </div>

      {/* Dose & frequency */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <label className="block text-xs font-medium text-text-muted mb-1">Dose</label>
          <input
            type="text"
            value={dose}
            onChange={(e) => onDoseChange(e.target.value)}
            placeholder="e.g. 500mg"
            className="w-full h-9 rounded-lg border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent-primary transition-colors"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-text-muted mb-1">Frequency</label>
          <input
            type="text"
            value={frequency}
            onChange={(e) => onFrequencyChange(e.target.value)}
            placeholder="e.g. twice daily"
            className="w-full h-9 rounded-lg border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent-primary transition-colors"
          />
        </div>
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
              onClick={() => onGuardianChange(value)}
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
