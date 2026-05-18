import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/auth'
import { usePatientStore } from '../../store/patient'

const ROUTES = [
  { label: 'Landing', path: '/', group: 'Public' },
  { label: 'Login', path: '/login', group: 'Public' },
  { label: 'Signup', path: '/signup', group: 'Public' },
  { label: 'Forgot Password', path: '/forgot-password', group: 'Public' },
  { label: 'Reset Password', path: '/reset-password', group: 'Public' },
  { label: 'Step 1 — Welcome', path: '/onboarding', group: 'Onboarding' },
  { label: 'Processing', path: '/onboarding/processing', group: 'Onboarding' },
  { label: 'Findings', path: '/onboarding/findings', group: 'Onboarding' },
  { label: 'Checklist', path: '/onboarding/checklist', group: 'Onboarding' },
  { label: 'Home', path: '/dashboard', group: 'Dashboard' },
  { label: 'Findings tab', path: '/dashboard/findings', group: 'Dashboard' },
  { label: 'Medications tab', path: '/dashboard/medications', group: 'Dashboard' },
  { label: 'Documents tab', path: '/dashboard/documents', group: 'Dashboard' },
  { label: 'Profile tab', path: '/dashboard/profile', group: 'Dashboard' },
  { label: 'Upload new docs', path: '/dashboard/upload', group: 'Dashboard' },
  { label: 'Reconcile', path: '/dashboard/upload/reconcile/preview-event-id', group: 'Dashboard' },
  { label: 'Upload Processing', path: '/dashboard/upload/processing/preview-event-id', group: 'Dashboard' },
  { label: 'Longitudinal Findings', path: '/dashboard/upload/findings/preview-event-id', group: 'Dashboard' },
  { label: 'Emergency', path: '/emergency', group: 'Other' },
]

const GROUPS = ['Public', 'Onboarding', 'Dashboard', 'Other']

const MOCK_TOKEN = 'preview-token'
const MOCK_USER_ID = 'preview-user-id'
const MOCK_PATIENT_ID = 'preview-patient-id'

export function PreviewNav() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const { login } = useAuthStore()
  const { setPatient } = usePatientStore()

  function seedAndNavigate(path: string) {
    // Seed stores so auth guards pass
    login(MOCK_TOKEN, MOCK_USER_ID)
    setPatient({
      patient_id: MOCK_PATIENT_ID,
      patient_name: 'Rajesh Singh',
      onboarding_complete: true,
      health_status: 'needs_attention',
    })
    setOpen(false)
    navigate(path)
  }

  return (
    <div className="fixed bottom-20 right-4 z-[9999]">
      {open && (
        <div className="mb-2 w-64 bg-white rounded-xl shadow-xl border border-gray-200 overflow-hidden">
          <div className="bg-gray-800 text-white px-3 py-2 text-xs font-semibold tracking-wide">
            PREVIEW — All Pages
          </div>
          <div className="overflow-y-auto max-h-96">
            {GROUPS.map(group => (
              <div key={group}>
                <div className="px-3 pt-3 pb-1 text-[10px] font-bold tracking-widest text-gray-400 uppercase">
                  {group}
                </div>
                {ROUTES.filter(r => r.group === group).map(route => (
                  <button
                    key={route.path}
                    onClick={() => seedAndNavigate(route.path)}
                    className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-teal-50 hover:text-teal-700 transition-colors cursor-pointer"
                  >
                    {route.label}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
      <button
        onClick={() => setOpen(o => !o)}
        className="bg-gray-800 text-white text-xs font-semibold px-3 py-2 rounded-full shadow-lg hover:bg-gray-700 transition-colors cursor-pointer"
      >
        {open ? '✕ Close' : '👁 Preview pages'}
      </button>
    </div>
  )
}
