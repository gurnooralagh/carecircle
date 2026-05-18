import { NavLink, Outlet } from 'react-router-dom'
import { House, ShieldCheck, Pill, FolderOpen, FilePlus } from 'lucide-react'
import { DashboardTopBar } from '../../components/layout/DashboardTopBar'

const TABS = [
  { to: '/dashboard', icon: House, label: 'Home', end: true },
  { to: '/dashboard/findings', icon: ShieldCheck, label: 'Findings', end: false },
  { to: '/dashboard/medications', icon: Pill, label: 'Medications', end: false },
  { to: '/dashboard/documents', icon: FolderOpen, label: 'Documents', end: false },
  { to: '/dashboard/upload', icon: FilePlus, label: 'New doc', end: false },
]

export function DashboardLayout() {
  return (
    <div className="flex flex-col min-h-screen bg-bg-primary">
      <DashboardTopBar />

      {/* Main content — padded to avoid bottom nav overlap */}
      <main className="flex-1 overflow-y-auto pb-20">
        <Outlet />
      </main>

      {/* Bottom tab bar */}
      <nav
        className="fixed bottom-0 left-0 right-0 z-20 bg-bg-card border-t border-border"
        aria-label="Main navigation"
      >
        <div className="flex max-w-lg mx-auto">
          {TABS.map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex-1 flex flex-col items-center justify-center gap-0.5 h-16 transition-colors ${
                  isActive ? 'text-accent-primary' : 'text-text-muted hover:text-text-secondary'
                }`
              }
              aria-label={label}
            >
              {({ isActive }) => (
                <>
                  <Icon className="w-5 h-5" strokeWidth={isActive ? 2.5 : 1.75} />
                  <span className="text-xs font-medium">{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
