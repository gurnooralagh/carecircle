import { useNavigate, useParams } from 'react-router-dom'
import { ProcessingScreen } from '../../../components/ProcessingScreen'
import api from '../../../lib/api'
import { usePatientStore } from '../../../store/patient'

const TEXT_VARIANTS = [
  'Comparing with previous findings…',
  'Checking for new concerns…',
  'Reviewing medication changes…',
  'Looking for improvements…',
  'Almost done…',
]

export function UploadProcessing() {
  const navigate = useNavigate()
  const { uploadEventId } = useParams<{ uploadEventId: string }>()
  const { patient_id } = usePatientStore()

  const pollFn = async () => {
    const res = await api.get(
      `/api/longitudinal/status/${patient_id}/${uploadEventId}`
    )
    return { status: res.data.processing_status as string }
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
      <div className="flex-1 flex flex-col">
        <div className="text-center pt-10 pb-4 px-6">
          <h2
            className="text-2xl font-normal text-text-primary"
            style={{ fontFamily: 'Fraunces, serif' }}
          >
            Updating the analysis
          </h2>
          <p className="text-sm text-text-secondary mt-1">
            Comparing with previous findings…
          </p>
        </div>
        <ProcessingScreen
          textVariants={TEXT_VARIANTS}
          onStatusReady={() => navigate(`/dashboard/upload/findings/${uploadEventId}`)}
          pollFn={pollFn}
        />
      </div>
    </div>
  )
}
