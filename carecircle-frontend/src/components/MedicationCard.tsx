import { useState } from 'react'
import { Pencil, Check, X, AlertTriangle } from 'lucide-react'
import type { Medication } from '../types'
import { Button } from './ui/Button'

interface MedicationCardProps {
  medication: Medication
  onEdit?: (id: string, dose: string, frequency: string) => Promise<void>
  onConfirm?: (id: string) => void
  onRemove?: (id: string) => void
  showActions?: boolean
  editDisabled?: boolean
}

const STATUS_STYLES: Record<string, { label: string; color: string; bg: string }> = {
  active: { label: 'Active', color: '#16A34A', bg: '#F0FDF4' },
  held: { label: 'On Hold', color: '#D97706', bg: '#FFFBEB' },
  stopped: { label: 'Stopped', color: '#6B7280', bg: '#F9FAFB' },
}

export function MedicationCard({
  medication,
  onEdit,
  onConfirm,
  onRemove,
  showActions = false,
  editDisabled = false,
}: MedicationCardProps) {
  const [editing, setEditing] = useState(false)
  const [dose, setDose] = useState(medication.dose_text ?? medication.dosage ?? '')
  const [frequency, setFrequency] = useState(medication.frequency ?? '')
  const [saving, setSaving] = useState(false)

  const statusStyle = STATUS_STYLES[medication.status ?? 'active'] ?? STATUS_STYLES.active
  const displayName = medication.drug_name_brand ?? medication.drug_name ?? 'Unknown'
  const genericName = medication.drug_name_generic
  const needsVerify = (medication.confidence ?? 1) < 0.8

  const handleSave = async () => {
    if (!onEdit) return
    setSaving(true)
    try {
      await onEdit(medication.medication_id, dose, frequency)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-bg-card rounded-xl border border-border shadow-sm p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-0.5">
            <h3 className="text-base font-semibold text-text-primary leading-tight">
              {displayName}
            </h3>
            <span
              className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium"
              style={{ color: statusStyle.color, backgroundColor: statusStyle.bg }}
            >
              {statusStyle.label}
            </span>
            {needsVerify && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-[#FFFBEB] text-[#D97706]">
                <AlertTriangle className="w-3 h-3" />
                Please verify
              </span>
            )}
          </div>
          {genericName && (
            <p className="text-sm text-text-muted mb-1">{genericName}</p>
          )}

          {editing ? (
            <div className="flex flex-col gap-2 mt-2">
              <input
                value={dose}
                onChange={(e) => setDose(e.target.value)}
                className="h-9 px-3 rounded-lg border border-border text-sm focus:outline-none focus:ring-2 focus:ring-accent-primary"
                placeholder="Dose (e.g. 10mg)"
                aria-label="Dose"
              />
              <input
                value={frequency}
                onChange={(e) => setFrequency(e.target.value)}
                className="h-9 px-3 rounded-lg border border-border text-sm focus:outline-none focus:ring-2 focus:ring-accent-primary"
                placeholder="Frequency (e.g. Once daily)"
                aria-label="Frequency"
              />
            </div>
          ) : (
            <div className="flex gap-3 text-sm text-text-secondary mt-1 flex-wrap">
              <span>{medication.dose_text}</span>
              <span className="text-border">·</span>
              <span>{medication.frequency}</span>
            </div>
          )}

          {medication.source && !editing && (
            <p className="text-xs text-text-muted mt-1">From: {medication.source}</p>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex flex-col gap-1 shrink-0">
          {editing ? (
            <>
              <button
                onClick={handleSave}
                disabled={saving}
                aria-label="Save changes"
                className="w-9 h-9 rounded-lg bg-accent-primary text-white flex items-center justify-center hover:bg-[#0A5858] transition-colors disabled:opacity-50"
              >
                <Check className="w-4 h-4" />
              </button>
              <button
                onClick={() => {
                  setEditing(false)
                  setDose(medication.dose_text ?? medication.dosage ?? '')
                  setFrequency(medication.frequency ?? '')
                }}
                aria-label="Cancel edit"
                className="w-9 h-9 rounded-lg border border-border text-text-muted flex items-center justify-center hover:bg-bg-secondary transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </>
          ) : (
            <>
              {onEdit && !editDisabled && (
                <button
                  onClick={() => setEditing(true)}
                  aria-label="Edit medication"
                  className="w-9 h-9 rounded-lg border border-border text-text-muted flex items-center justify-center hover:bg-bg-secondary transition-colors"
                >
                  <Pencil className="w-4 h-4" />
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {showActions && !editing && (
        <div className="flex gap-2 mt-3 pt-3 border-t border-border">
          {onConfirm && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onConfirm(medication.medication_id)}
              className="flex-1"
            >
              <Check className="w-3.5 h-3.5" />
              Confirm
            </Button>
          )}
          {onRemove && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onRemove(medication.medication_id)}
              className="text-severity-critical hover:bg-[#FEF2F2]"
            >
              <X className="w-3.5 h-3.5" />
              Remove
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
