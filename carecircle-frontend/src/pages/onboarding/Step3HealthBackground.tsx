import { useState } from 'react'
import type { KeyboardEvent } from 'react'
import { X, Plus } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'

export interface HealthData {
  conditions: string[]
  medications: Array<{ drug_name: string; dosage: string; frequency: string }>
  allergies: string[]
  doctors: Array<{ name: string; specialty: string; hospital: string }>
}

interface Props {
  onNext: (data: HealthData) => void
}

function TagInput({
  label,
  placeholder,
  tags,
  onChange,
}: {
  label: string
  placeholder: string
  tags: string[]
  onChange: (tags: string[]) => void
}) {
  const [input, setInput] = useState('')

  const add = () => {
    const val = input.trim()
    if (val && !tags.includes(val)) onChange([...tags, val])
    setInput('')
  }

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add() }
    if (e.key === 'Backspace' && input === '' && tags.length > 0) {
      onChange(tags.slice(0, -1))
    }
  }

  return (
    <div className="mb-5">
      <label className="block text-sm font-medium text-text-primary mb-1.5">{label}</label>
      <div className="min-h-[44px] rounded-xl border border-border bg-bg-secondary px-3 py-2 flex flex-wrap gap-2 focus-within:border-accent-primary transition-colors">
        {tags.map((t) => (
          <span
            key={t}
            className="flex items-center gap-1 bg-accent-primary/10 text-accent-primary text-xs font-medium px-2 py-1 rounded-full"
          >
            {t}
            <button
              type="button"
              onClick={() => onChange(tags.filter((x) => x !== t))}
              className="hover:text-accent-primary/70"
              aria-label={`Remove ${t}`}
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          onBlur={add}
          placeholder={tags.length === 0 ? placeholder : ''}
          className="flex-1 min-w-[120px] bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none"
        />
      </div>
      <p className="text-xs text-text-muted mt-1">Press Enter or comma to add each item</p>
    </div>
  )
}

interface MedRow {
  drug_name: string
  dosage: string
  frequency: string
}

export function Step3HealthBackground({ onNext }: Props) {
  const [conditions, setConditions] = useState<string[]>([])
  const [allergies, setAllergies] = useState<string[]>([])
  const [medications, setMedications] = useState<MedRow[]>([])
  const [doctorName, setDoctorName] = useState('')
  const [doctorSpecialty, setDoctorSpecialty] = useState('')
  const [doctorHospital, setDoctorHospital] = useState('')

  const addMedication = () => {
    setMedications((prev) => [...prev, { drug_name: '', dosage: '', frequency: '' }])
  }

  const updateMedication = (index: number, field: keyof MedRow, value: string) => {
    setMedications((prev) =>
      prev.map((med, i) => (i === index ? { ...med, [field]: value } : med))
    )
  }

  const removeMedication = (index: number) => {
    setMedications((prev) => prev.filter((_, i) => i !== index))
  }

  const handleContinue = () => {
    const doctors: Array<{ name: string; specialty: string; hospital: string }> = []
    if (doctorName.trim() || doctorSpecialty.trim() || doctorHospital.trim()) {
      doctors.push({
        name: doctorName.trim(),
        specialty: doctorSpecialty.trim(),
        hospital: doctorHospital.trim(),
      })
    }

    onNext({
      conditions,
      medications: medications.filter((m) => m.drug_name.trim()),
      allergies,
      doctors,
    })
  }

  return (
    <div className="pt-4">
      <h2
        className="text-2xl font-normal text-text-primary mb-1"
        style={{ fontFamily: 'Fraunces, serif' }}
      >
        Health background
      </h2>
      <p className="text-sm text-text-secondary mb-8">
        Add what you already know — our AI will also extract more from your documents.
        Everything here is optional.
      </p>

      <TagInput
        label="Known diagnoses / conditions"
        placeholder="e.g. Type 2 diabetes, hypertension…"
        tags={conditions}
        onChange={setConditions}
      />

      {/* Medications structured list */}
      <div className="mb-5">
        <label className="block text-sm font-medium text-text-primary mb-1.5">
          Current medications
        </label>
        {medications.length > 0 && (
          <div className="flex flex-col gap-3 mb-2">
            {medications.map((med, i) => (
              <div key={i} className="flex gap-2 items-start">
                <div className="flex-1 grid grid-cols-3 gap-2">
                  <input
                    type="text"
                    value={med.drug_name}
                    onChange={(e) => updateMedication(i, 'drug_name', e.target.value)}
                    placeholder="e.g. Metformin"
                    className="h-10 rounded-xl border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent-primary transition-colors"
                  />
                  <input
                    type="text"
                    value={med.dosage}
                    onChange={(e) => updateMedication(i, 'dosage', e.target.value)}
                    placeholder="e.g. 500mg"
                    className="h-10 rounded-xl border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent-primary transition-colors"
                  />
                  <input
                    type="text"
                    value={med.frequency}
                    onChange={(e) => updateMedication(i, 'frequency', e.target.value)}
                    placeholder="e.g. twice daily"
                    className="h-10 rounded-xl border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent-primary transition-colors"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => removeMedication(i)}
                  className="mt-2.5 text-text-muted hover:text-severity-critical transition-colors"
                  aria-label="Remove medication"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
        <button
          type="button"
          onClick={addMedication}
          className="flex items-center gap-1.5 text-sm text-accent-primary font-medium hover:opacity-80 transition-opacity"
        >
          <Plus className="w-4 h-4" />
          Add medication
        </button>
      </div>

      <TagInput
        label="Allergies"
        placeholder="e.g. Penicillin, Aspirin, nuts…"
        tags={allergies}
        onChange={setAllergies}
      />

      {/* Primary doctor (optional) */}
      <div className="mb-5">
        <label className="block text-sm font-medium text-text-primary mb-1.5">
          Primary doctor (optional)
        </label>
        <div className="flex flex-col gap-2">
          <Input
            label="Doctor name"
            type="text"
            placeholder="e.g. Dr. Sharma"
            value={doctorName}
            onChange={(e) => setDoctorName(e.target.value)}
          />
          <Input
            label="Specialty"
            type="text"
            placeholder="e.g. Cardiologist"
            value={doctorSpecialty}
            onChange={(e) => setDoctorSpecialty(e.target.value)}
          />
          <Input
            label="Hospital"
            type="text"
            placeholder="e.g. Apollo Hospital"
            value={doctorHospital}
            onChange={(e) => setDoctorHospital(e.target.value)}
          />
        </div>
      </div>

      <Button onClick={handleContinue} fullWidth size="lg">
        Continue
      </Button>
    </div>
  )
}
