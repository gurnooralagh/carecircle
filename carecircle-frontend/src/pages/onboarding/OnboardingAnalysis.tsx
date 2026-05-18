import { useNavigate } from 'react-router-dom'
import { ProcessingScreen } from '../../components/ProcessingScreen'
import { usePatientStore } from '../../store/patient'
import api from '../../lib/api'

const TEXT_VARIANTS = [
  'Analysing medications…',
  'Checking for drug interactions…',
  'Reviewing lab values…',
  'Building your findings report…',
  'Almost ready…',
]

export function OnboardingAnalysis() {
  const navigate = useNavigate()
  const { patient_id } = usePatientStore()

  const pollFn = async () => {
    const res = await api.get(`/api/onboarding/status/${patient_id}`)
    const status: string = res.data?.status ?? ''
    const DONE = ['complete', 'findings_ready', 'ready_for_review']
    return { status: DONE.includes(status) ? 'ready' : status }
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
            Analysing everything
          </h2>
          <p className="text-sm text-text-secondary mt-1">
            Checking for interactions, lab concerns, and what needs attention.
          </p>
        </div>
        <ProcessingScreen
          textVariants={TEXT_VARIANTS}
          onStatusReady={() => navigate('/onboarding/findings')}
          pollFn={pollFn}
        />
      </div>
    </div>
  )
}
