import { useLocation, Link } from 'react-router-dom'
import { Mail } from 'lucide-react'
import { AuthLayout } from '../components/layout/AuthLayout'

export function CheckEmail() {
  const location = useLocation()
  const email = (location.state as { email?: string })?.email ?? 'your email'

  return (
    <AuthLayout title="Check your email" subtitle="">
      <div className="flex flex-col items-center text-center gap-4 py-4">
        <div className="w-16 h-16 rounded-full bg-[#E6F4F4] flex items-center justify-center">
          <Mail className="w-8 h-8 text-accent-primary" />
        </div>
        <p className="text-base text-text-secondary max-w-xs">
          We sent a confirmation link to <span className="font-semibold text-text-primary">{email}</span>.
          Click the link to confirm your account, then come back and log in.
        </p>
        <Link
          to="/login"
          className="mt-2 inline-flex items-center justify-center h-12 px-6 rounded-xl bg-accent-primary text-white text-sm font-medium hover:bg-[#0A5858] transition-colors w-full"
        >
          Go to login
        </Link>
      </div>
    </AuthLayout>
  )
}
