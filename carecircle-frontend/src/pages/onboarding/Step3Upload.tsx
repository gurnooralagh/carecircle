import { useState } from 'react'
import { FileUploadZone } from '../../components/FileUploadZone'
import { Button } from '../../components/ui/Button'
import api from '../../lib/api'
import { usePatientStore } from '../../store/patient'
import { useToast } from '../../store/toast'
import type { UploadFile } from '../../types'
import type { PatientFormData } from './OnboardingLayout'

interface Step3UploadProps {
  patientData: PatientFormData
  onSubmitted: () => void
}

export function Step3Upload({ patientData, onSubmitted }: Step3UploadProps) {
  const [files, setFiles] = useState<UploadFile[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const { setPatient } = usePatientStore()
  const toast = useToast()

  const handleContinue = async () => {
    if (files.length === 0) {
      setError('Please add at least one document before continuing.')
      return
    }
    setError('')
    setSubmitting(true)

    try {
      const formData = new FormData()

      // Patient info fields
      formData.append('full_name', patientData.full_name)
      formData.append('date_of_birth', patientData.date_of_birth)
      formData.append('gender', patientData.gender)
      if (patientData.weight_kg != null) formData.append('weight_kg', String(patientData.weight_kg))
      if (patientData.height_cm != null) formData.append('height_cm', String(patientData.height_cm))
      if (patientData.city) formData.append('city', patientData.city)

      // Empty JSON arrays for optional fields
      formData.append('conditions', '[]')
      formData.append('medications', '[]')
      formData.append('allergies', '[]')
      formData.append('doctors', '[]')

      // Files + types
      const fileTypes: string[] = []
      for (const uf of files) {
        formData.append('files', uf.file)
        fileTypes.push(uf.document_type)
      }
      formData.append('file_types', JSON.stringify(fileTypes))

      const res = await api.post('/api/onboarding/submit', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      const patientId = res.data?.patient_id
      if (!patientId) throw new Error('No patient ID returned')

      setPatient({
        patient_id: patientId,
        patient_name: patientData.full_name,
        onboarding_complete: false,
      })

      onSubmitted()
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Submission failed. Please try again.'
      toast.error(msg)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="pt-4">
      <h2
        className="text-2xl font-normal text-text-primary mb-1"
        style={{ fontFamily: 'Fraunces, serif' }}
      >
        Upload medical documents
      </h2>
      <p className="text-sm text-text-secondary mb-8">
        Add prescriptions, lab reports, or discharge summaries. You can always add more later.
      </p>

      <FileUploadZone files={files} onFilesChange={setFiles} />

      {error && (
        <p className="text-sm text-severity-critical mt-3" role="alert">
          {error}
        </p>
      )}

      <Button
        onClick={handleContinue}
        fullWidth
        size="lg"
        loading={submitting}
        className="mt-6"
      >
        {submitting ? 'Submitting…' : 'Continue'}
      </Button>
    </div>
  )
}
