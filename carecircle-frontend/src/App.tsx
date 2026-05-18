import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AnimatePresence } from 'framer-motion'

// Pages
import { Landing } from './pages/Landing'
import { Login } from './pages/Login'
import { Signup } from './pages/Signup'
import { ForgotPassword } from './pages/ForgotPassword'
import { ResetPassword } from './pages/ResetPassword'
import { Emergency } from './pages/Emergency'

// Onboarding
import { OnboardingLayout } from './pages/onboarding/OnboardingLayout'
import { OnboardingProcessing } from './pages/onboarding/OnboardingProcessing'
import { OnboardingAnalysis } from './pages/onboarding/OnboardingAnalysis'
import { Step4Medications } from './pages/onboarding/Step4Medications'
import { OnboardingFindings } from './pages/onboarding/OnboardingFindings'
import { OnboardingChecklist } from './pages/onboarding/OnboardingChecklist'
import { CheckEmail } from './pages/CheckEmail'

// Dashboard
import { DashboardLayout } from './pages/dashboard/DashboardLayout'
import { DashboardHome } from './pages/dashboard/DashboardHome'
import { FindingsTab } from './pages/dashboard/FindingsTab'
import { MedicationsTab } from './pages/dashboard/MedicationsTab'
import { DocumentsTab } from './pages/dashboard/DocumentsTab'
import { ProfileTab } from './pages/dashboard/ProfileTab'
import { UploadTab } from './pages/dashboard/upload/UploadTab'
import { ReconcileScreen } from './pages/dashboard/upload/ReconcileScreen'
import { UploadProcessing } from './pages/dashboard/upload/UploadProcessing'
import { LongitudinalFindings } from './pages/dashboard/upload/LongitudinalFindings'

// Toast
import { ToastContainer } from './components/ui/Toast'
import { PreviewNav } from './components/ui/PreviewNav'

// Auth
import { supabase } from './lib/supabase'
import { useAuthStore } from './store/auth'
import { usePatientStore } from './store/patient'

const PREVIEW_MODE = import.meta.env.VITE_PREVIEW_MODE === 'true'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

// ─── Auth Guards ─────────────────────────────────────────────────────────────

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { is_authenticated } = useAuthStore()
  if (PREVIEW_MODE) return <>{children}</>
  if (!is_authenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

function RequireOnboarded({ children }: { children: React.ReactNode }) {
  const { is_authenticated } = useAuthStore()
  const { onboarding_complete } = usePatientStore()

  if (PREVIEW_MODE) return <>{children}</>
  if (!is_authenticated) return <Navigate to="/login" replace />
  if (!onboarding_complete) return <Navigate to="/onboarding" replace />
  return <>{children}</>
}

function RedirectIfAuth({ children }: { children: React.ReactNode }) {
  const { is_authenticated } = useAuthStore()
  const { onboarding_complete } = usePatientStore()

  if (PREVIEW_MODE) return <>{children}</>
  if (is_authenticated) {
    return <Navigate to={onboarding_complete ? '/dashboard' : '/onboarding'} replace />
  }
  return <>{children}</>
}

// ─── Animated Routes ─────────────────────────────────────────────────────────

function AnimatedRoutes() {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        {/* Public */}
        <Route path="/" element={<RedirectIfAuth><Landing /></RedirectIfAuth>} />
        <Route path="/login" element={<RedirectIfAuth><Login /></RedirectIfAuth>} />
        <Route path="/signup" element={<RedirectIfAuth><Signup /></RedirectIfAuth>} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />

        {/* Emergency — accessible while authenticated */}
        <Route path="/emergency" element={<RequireAuth><Emergency /></RequireAuth>} />

        {/* Check email after signup */}
        <Route path="/check-email" element={<CheckEmail />} />

        {/* Onboarding */}
        <Route path="/onboarding" element={<RequireAuth><OnboardingLayout /></RequireAuth>} />
        <Route path="/onboarding/processing" element={<RequireAuth><OnboardingProcessing /></RequireAuth>} />
        <Route path="/onboarding/medications" element={<RequireAuth><Step4Medications /></RequireAuth>} />
        <Route path="/onboarding/analysis" element={<RequireAuth><OnboardingAnalysis /></RequireAuth>} />
        <Route path="/onboarding/findings" element={<RequireAuth><OnboardingFindings /></RequireAuth>} />
        <Route path="/onboarding/checklist" element={<RequireAuth><OnboardingChecklist /></RequireAuth>} />

        {/* Dashboard */}
        <Route
          path="/dashboard"
          element={<RequireOnboarded><DashboardLayout /></RequireOnboarded>}
        >
          <Route index element={<DashboardHome />} />
          <Route path="findings" element={<FindingsTab />} />
          <Route path="medications" element={<MedicationsTab />} />
          <Route path="documents" element={<DocumentsTab />} />
          <Route path="profile" element={<ProfileTab />} />
          <Route path="upload" element={<UploadTab />} />
          <Route path="upload/reconcile/:uploadEventId" element={<ReconcileScreen />} />
          <Route path="upload/processing/:uploadEventId" element={<UploadProcessing />} />
          <Route path="upload/findings/:uploadEventId" element={<LongitudinalFindings />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  )
}

// ─── App Shell ────────────────────────────────────────────────────────────────

function AppShell() {
  const { login, logout } = useAuthStore()
  const [initialised, setInitialised] = useState(false)

  useEffect(() => {
    // Sync Supabase session on mount
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.access_token && session.user?.id) {
        login(session.access_token, session.user.id)
      }
      setInitialised(true)
    })

    // Watch for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        if (session?.access_token && session.user?.id) {
          login(session.access_token, session.user.id)
        } else {
          logout()
        }
      }
    )

    return () => subscription.unsubscribe()
  }, [login, logout])

  if (!initialised) {
    return (
      <div className="min-h-screen bg-bg-primary flex items-center justify-center">
        <div className="w-8 h-8 rounded-full border-2 border-accent-primary border-t-transparent animate-spin" />
      </div>
    )
  }

  return (
    <>
      <AnimatedRoutes />
      <ToastContainer />
      {PREVIEW_MODE && <PreviewNav />}
    </>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </QueryClientProvider>
  )
}
