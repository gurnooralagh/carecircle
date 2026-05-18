import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { PageTransition } from '../../components/ui/PageTransition'
import { Step1Welcome } from './Step1Welcome'
import { Step2PatientInfo } from './Step2PatientInfo'
import { Step3HealthBackground } from './Step3HealthBackground'
import { Step4Upload } from './Step4Upload'
import type { HealthData } from './Step3HealthBackground'

export interface PatientFormData {
  full_name: string
  date_of_birth: string
  gender: 'Male' | 'Female' | 'Other'
  weight_kg?: number
  height_cm?: number
  city?: string
  state?: string
}

const TOTAL_STEPS = 4

export function OnboardingLayout() {
  const [step, setStep] = useState(1)
  const [patientData, setPatientData] = useState<PatientFormData | null>(null)
  const [healthData, setHealthData] = useState<HealthData | null>(null)
  const navigate = useNavigate()

  const goNext = () => {
    if (step < TOTAL_STEPS) setStep((s) => s + 1)
  }

  const handlePatientData = (data: PatientFormData) => {
    setPatientData(data)
    goNext()
  }

  const handleHealthData = (data: HealthData) => {
    setHealthData(data)
    goNext()
  }

  const handleSubmitComplete = () => {
    navigate('/onboarding/processing')
  }

  const stepContent = () => {
    switch (step) {
      case 1:
        return <Step1Welcome onNext={goNext} />
      case 2:
        return <Step2PatientInfo onNext={handlePatientData} />
      case 3:
        return <Step3HealthBackground onNext={handleHealthData} />
      case 4:
        return (
          <Step4Upload
            patientData={patientData!}
            healthData={healthData!}
            onSubmitted={handleSubmitComplete}
          />
        )
      default:
        return null
    }
  }

  return (
    <div className="min-h-screen bg-bg-primary flex flex-col">
      <header className="px-6 py-4 flex items-center justify-between border-b border-border">
        <span
          className="text-lg font-semibold text-accent-primary"
          style={{ fontFamily: 'Fraunces, serif' }}
        >
          CareCircle
        </span>
      </header>

      {/* Progress dots */}
      <div className="flex justify-center gap-2 py-5">
        {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
          <div
            key={i}
            className={`rounded-full transition-all duration-300 ${
              i + 1 === step
                ? 'w-6 h-2.5 bg-accent-primary'
                : i + 1 < step
                ? 'w-2.5 h-2.5 bg-accent-primary opacity-50'
                : 'w-2.5 h-2.5 bg-border'
            }`}
          />
        ))}
      </div>

      <div className="flex-1 max-w-xl mx-auto w-full px-6 pb-12">
        <AnimatePresence mode="wait">
          <PageTransition key={step}>{stepContent()}</PageTransition>
        </AnimatePresence>
      </div>
    </div>
  )
}
