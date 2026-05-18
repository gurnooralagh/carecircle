import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Pill, Plus, X } from 'lucide-react'
import { MedicationCard } from '../../components/MedicationCard'
import { SkeletonList } from '../../components/ui/SkeletonCard'
import { EmptyState } from '../../components/ui/EmptyState'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { PageTransition } from '../../components/ui/PageTransition'
import { AnimatePresence, motion } from 'framer-motion'
import api from '../../lib/api'
import { usePatientStore } from '../../store/patient'
import { useToast } from '../../store/toast'
import { isNotBuiltError } from '../../lib/utils'
import type { Medication } from '../../types'

const STATUS_GROUPS = [
  { key: 'active', label: 'Active' },
  { key: 'held', label: 'On Hold' },
  { key: 'stopped', label: 'Stopped' },
]

export function MedicationsTab() {
  const { patient_id } = usePatientStore()
  const toast = useToast()
  const queryClient = useQueryClient()
  const [addOpen, setAddOpen] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-medications', patient_id],
    queryFn: async () => {
      try {
        const res = await api.get(`/api/onboarding/extracted_medications/${patient_id}`)
        return res.data as { medications: Medication[] }
      } catch {
        return { medications: [] }
      }
    },
    enabled: !!patient_id,
  })

  const medications = data?.medications ?? []

  const handleEdit = async (id: string, dose: string, freq: string) => {
    try {
      await api.patch(`/api/medications/${id}`, {
        dose_text: dose,
        frequency: freq,
        guardian_confirmed: true,
      })
      queryClient.invalidateQueries({ queryKey: ['dashboard-medications', patient_id] })
      toast.success('Medication updated')
    } catch (err) {
      if (isNotBuiltError(err)) {
        toast.info('Editing medications is coming soon')
      } else {
        toast.error('Could not update medication')
      }
    }
  }

  return (
    <PageTransition className="px-4 py-6 max-w-xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2
          className="text-2xl font-normal text-text-primary"
          style={{ fontFamily: 'Fraunces, serif' }}
        >
          Medications
        </h2>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setAddOpen(true)}
          aria-label="Add medication"
        >
          <Plus className="w-4 h-4" />
          Add
        </Button>
      </div>

      {isLoading && <SkeletonList count={4} />}

      {!isLoading && medications.length === 0 && (
        <EmptyState
          icon={Pill}
          title="No medications yet"
          description="Medications found in your documents will appear here."
        />
      )}

      {!isLoading &&
        STATUS_GROUPS.map(({ key, label }) => {
          const group = medications.filter((m) => {
            // Map guardian_taking_status → status group when status field is absent
            let status = m.status
            if (!status) {
              const gts = (m as unknown as Record<string, string>).guardian_taking_status
              if (gts === 'no_stopped') status = 'stopped'
              else status = 'active'
            }
            return status === key
          })
          if (group.length === 0) return null
          return (
            <div key={key} className="mb-6">
              <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-3">
                {label} ({group.length})
              </h3>
              <div className="flex flex-col gap-3">
                {group.map((med) => (
                  <MedicationCard
                    key={med.medication_id}
                    medication={med}
                    onEdit={handleEdit}
                  />
                ))}
              </div>
            </div>
          )
        })}

      {/* Add medication bottom sheet */}
      <AnimatePresence>
        {addOpen && (
          <AddMedicationSheet
            patientId={patient_id ?? ''}
            onClose={() => setAddOpen(false)}
            onAdded={() => {
              setAddOpen(false)
              queryClient.invalidateQueries({ queryKey: ['dashboard-medications', patient_id] })
            }}
          />
        )}
      </AnimatePresence>
    </PageTransition>
  )
}

interface AddMedicationSheetProps {
  patientId: string
  onClose: () => void
  onAdded: () => void
}

function AddMedicationSheet({ patientId, onClose, onAdded }: AddMedicationSheetProps) {
  const toast = useToast()
  const [brandName, setBrandName] = useState('')
  const [genericName, setGenericName] = useState('')
  const [dose, setDose] = useState('')
  const [frequency, setFrequency] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    if (!brandName || !dose || !frequency) {
      toast.error('Please fill in brand name, dose, and frequency')
      return
    }
    setSaving(true)
    try {
      await api.post('/api/medications/add', {
        patient_id: patientId,
        brand_name: brandName,
        generic_name: genericName,
        dose_text: dose,
        frequency,
        status: 'active',
        guardian_confirmed: true,
      })
      onAdded()
      toast.success('Medication added')
    } catch (err) {
      if (isNotBuiltError(err)) {
        toast.info('Adding medications is coming soon')
        onClose()
      } else {
        toast.error('Could not add medication')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-end"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <motion.div
        className="relative bg-bg-card rounded-t-2xl w-full p-6 z-10 max-h-[90vh] overflow-y-auto"
        initial={{ y: '100%' }}
        animate={{ y: 0 }}
        exit={{ y: '100%' }}
        transition={{ type: 'spring', damping: 25, stiffness: 200 }}
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-semibold text-text-primary">Add medication</h3>
          <button onClick={onClose} aria-label="Close" className="text-text-muted hover:text-text-primary">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="flex flex-col gap-4">
          <Input
            label="Brand name"
            value={brandName}
            onChange={(e) => setBrandName(e.target.value)}
            placeholder="e.g. Metformin"
          />
          <Input
            label="Generic name (optional)"
            value={genericName}
            onChange={(e) => setGenericName(e.target.value)}
            placeholder="e.g. Metformin hydrochloride"
          />
          <Input
            label="Dose"
            value={dose}
            onChange={(e) => setDose(e.target.value)}
            placeholder="e.g. 500mg"
          />
          <Input
            label="Frequency"
            value={frequency}
            onChange={(e) => setFrequency(e.target.value)}
            placeholder="e.g. Twice daily"
          />
          <Button onClick={handleSave} fullWidth loading={saving} className="mt-2">
            Add medication
          </Button>
        </div>
      </motion.div>
    </motion.div>
  )
}
