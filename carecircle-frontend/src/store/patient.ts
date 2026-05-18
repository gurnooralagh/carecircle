import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface PatientState {
  patient_id: string | null
  patient_name: string | null
  onboarding_complete: boolean
  health_status: 'stable' | 'needs_attention' | 'urgent' | null
  setPatient: (data: Partial<PatientState>) => void
  clearPatient: () => void
}

export const usePatientStore = create<PatientState>()(
  persist(
    (set) => ({
      patient_id: null,
      patient_name: null,
      onboarding_complete: false,
      health_status: null,
      setPatient: (data) => set((state) => ({ ...state, ...data })),
      clearPatient: () =>
        set({
          patient_id: null,
          patient_name: null,
          onboarding_complete: false,
          health_status: null,
        }),
    }),
    {
      name: 'carecircle-patient',
    }
  )
)
