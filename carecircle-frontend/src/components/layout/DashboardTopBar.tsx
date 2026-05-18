import { useNavigate, useLocation, Link } from 'react-router-dom'
import { ShieldAlert, FilePlus, UserCircle } from 'lucide-react'
import { usePatientStore } from '../../store/patient'
import { getHealthStatusColor } from '../../lib/utils'

export function DashboardTopBar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { patient_name, health_status } = usePatientStore()
  const dotColor = getHealthStatusColor(health_status)

  const isHome = location.pathname === '/dashboard'

  return (
    <header className="sticky top-0 z-30 bg-bg-card border-b border-border">
      <div className="px-4 h-14 flex items-center justify-between gap-2">
        {/* Left: logo + optional profile link */}
        <div className="flex flex-col justify-center min-w-0">
          <span
            className="text-lg font-semibold text-accent-primary leading-none"
            style={{ fontFamily: 'Fraunces, serif' }}
          >
            CareCircle
          </span>
          {isHome && (
            <Link
              to="/dashboard/profile"
              className="flex items-center gap-1 mt-0.5 text-xs text-text-muted hover:text-accent-primary transition-colors"
            >
              <UserCircle className="w-3 h-3" />
              <span>Your profile</span>
            </Link>
          )}
        </div>

        {/* Center: patient name + health dot (non-home pages) */}
        {!isHome && (
          <div className="flex items-center gap-2 flex-1 justify-center">
            <div
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: dotColor }}
              aria-hidden="true"
            />
            <span className="text-sm font-medium text-text-primary truncate max-w-[140px]">
              {patient_name ?? 'Patient'}
            </span>
          </div>
        )}

        {/* Right: New doc + Emergency */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => navigate('/dashboard/upload')}
            aria-label="Upload new document"
            className="flex items-center gap-1.5 px-3 h-9 rounded-xl border border-accent-primary text-accent-primary text-sm font-medium hover:bg-[#E6F4F4] transition-colors cursor-pointer"
          >
            <FilePlus className="w-4 h-4" />
            <span className="hidden sm:inline">New doc</span>
          </button>

          <button
            onClick={() => navigate('/emergency')}
            aria-label="Open emergency summary"
            className="flex items-center gap-1.5 px-3 h-9 rounded-xl border border-severity-critical text-severity-critical text-sm font-medium hover:bg-[#FEF2F2] transition-colors cursor-pointer"
          >
            <ShieldAlert className="w-4 h-4" />
            <span className="hidden sm:inline">Emergency</span>
          </button>
        </div>
      </div>
    </header>
  )
}
