import { useNavigate } from 'react-router-dom'
import { ProcessingScreen } from '../../components/ProcessingScreen'
import { usePatientStore } from '../../store/patient'
import api from '../../lib/api'

const TEXT_VARIANTS = [
  'Reading documents…',
  'Checking medications…',
  'Looking for concerns…',
  'Cross-referencing lab values…',
  'Almost ready…',
]

export function OnboardingProcessing() {
  const navigate = useNavigate()
  const { patient_id } = usePatientStore()

  const pollFn = async () => {
    const res = await api.get(`/api/onboarding/status/${patient_id}`)
    const status: string = res.data?.status ?? ''
    // Phase 1 complete when extraction is done — medications ready to review
    const ready = status === 'medication_verification_needed'
    return { status: ready ? 'ready' : status }
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
            Reading your documents
          </h2>
          <p className="text-sm text-text-secondary mt-1">
            This usually takes 30–60 seconds.
          </p>
        </div>
        <ProcessingScreen
          textVariants={TEXT_VARIANTS}
          onStatusReady={() => navigate('/onboarding/medications')}
          pollFn={pollFn}
        />
      </div>
    </div>
  )
}
