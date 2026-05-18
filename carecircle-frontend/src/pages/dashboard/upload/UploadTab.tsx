import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileUploadZone } from '../../../components/FileUploadZone'
import { Button } from '../../../components/ui/Button'
import { PageTransition } from '../../../components/ui/PageTransition'
import api from '../../../lib/api'
import { usePatientStore } from '../../../store/patient'
import { useUploadStore } from '../../../store/upload'
import { useToast } from '../../../store/toast'
import type { UploadFile } from '../../../types'

export function UploadTab() {
  const navigate = useNavigate()
  const [files, setFiles] = useState<UploadFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const { patient_id } = usePatientStore()
  const { setUploadEvent } = useUploadStore()
  const toast = useToast()

  const handleUpload = async () => {
    if (files.length === 0) {
      setError('Please add at least one document.')
      return
    }
    setError('')
    setUploading(true)

    try {
      const formData = new FormData()
      for (const uf of files) {
        formData.append('files', uf.file)
      }
      formData.append('file_types', JSON.stringify(files.map((uf) => uf.document_type)))

      // Do NOT set Content-Type manually — axios must auto-set multipart/form-data with boundary
      const res = await api.post(`/api/longitudinal/upload/${patient_id}`, formData)

      const uploadEventId = res.data?.upload_event_id ?? res.data?.id
      if (!uploadEventId) throw new Error('No upload event ID returned from server.')
      setUploadEvent(uploadEventId, 'pending')

      // Poll until reconciling — throws if failed or timeout
      const reached = await pollUntilReconciling(patient_id!, uploadEventId)
      if (!reached) {
        toast.error('Processing is taking longer than expected. Please try again in a minute.')
        return
      }
      navigate(`/dashboard/upload/reconcile/${uploadEventId}`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Upload failed. Please try again.'
      toast.error(msg)
    } finally {
      setUploading(false)
    }
  }

  return (
    <PageTransition className="px-4 py-6 max-w-xl mx-auto">
      <h2
        className="text-2xl font-normal text-text-primary mb-1"
        style={{ fontFamily: 'Fraunces, serif' }}
      >
        Upload new documents
      </h2>
      <p className="text-sm text-text-secondary mb-8">
        Add new prescriptions or reports to update your loved one's health analysis.
      </p>

      <FileUploadZone files={files} onFilesChange={setFiles} />

      {error && (
        <p className="text-sm text-severity-critical mt-3" role="alert">
          {error}
        </p>
      )}

      <Button
        onClick={handleUpload}
        fullWidth
        size="lg"
        loading={uploading}
        className="mt-6"
      >
        {uploading ? 'Uploading & processing…' : 'Upload & analyse'}
      </Button>
    </PageTransition>
  )
}

// Returns true when ready, false on timeout. Throws on explicit failure.
async function pollUntilReconciling(patientId: string, uploadEventId: string): Promise<boolean> {
  const MAX_POLLS = 160  // ~8 minutes — Railway + LLM extraction can be slow
  for (let i = 0; i < MAX_POLLS; i++) {
    await new Promise((r) => setTimeout(r, 3000))
    try {
      const res = await api.get(
        `/api/longitudinal/status/${patientId}/${uploadEventId}`
      )
      const status = res.data?.processing_status
      if (status === 'reconciling' || status === 'ready') return true
      if (status === 'failed') throw new Error('Document processing failed. Please try uploading again.')
    } catch (err) {
      // Only re-throw explicit failures, ignore transient network errors
      if (err instanceof Error && err.message.includes('processing failed')) throw err
    }
  }
  return false
}
