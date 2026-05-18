import { useEffect } from 'react'
import { Heart, Shield, FileSearch } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { supabase } from '../../lib/supabase'
import api from '../../lib/api'

interface Step1WelcomeProps {
  onNext: () => void
}

export function Step1Welcome({ onNext }: Step1WelcomeProps) {
  // Ensure user profile exists before onboarding proceeds
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      const user = data.session?.user
      if (!user) return
      api.post('/api/auth/set-role', {
        role: 'guardian',
        full_name: user.user_metadata?.full_name ?? user.email?.split('@')[0] ?? '',
        email: user.email ?? '',
      }).catch(() => { /* already exists — safe to ignore */ })
    })
  }, [])

  return (
    <div className="flex flex-col items-center text-center pt-8">
      <h1
        className="text-3xl font-normal text-text-primary mb-3"
        style={{ fontFamily: 'Fraunces, serif' }}
      >
        Let's get started.
      </h1>
      <p className="text-base text-text-secondary max-w-sm mb-10">
        We'll walk you through setting up your loved one's medical profile in just a few steps.
        It takes about 5 minutes.
      </p>

      <div className="flex flex-col gap-4 w-full max-w-sm mb-10">
        <FeatureRow
          icon={FileSearch}
          title="Upload documents"
          description="Prescriptions, lab results, discharge summaries — anything you have."
        />
        <FeatureRow
          icon={Shield}
          title="We check for risks"
          description="Drug interactions, concerning lab values, follow-up needs."
        />
        <FeatureRow
          icon={Heart}
          title="You get clear guidance"
          description="Explained in plain language, with a to-do list for what to do next."
        />
      </div>

      <Button onClick={onNext} size="lg" fullWidth>
        Let's begin
      </Button>
    </div>
  )
}

function FeatureRow({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ElementType
  title: string
  description: string
}) {
  return (
    <div className="flex items-start gap-3 text-left bg-bg-card border border-border rounded-xl p-4">
      <div className="w-9 h-9 rounded-lg bg-[#E6F4F4] flex items-center justify-center shrink-0 mt-0.5">
        <Icon className="w-4 h-4 text-accent-primary" />
      </div>
      <div>
        <p className="text-sm font-semibold text-text-primary">{title}</p>
        <p className="text-sm text-text-secondary">{description}</p>
      </div>
    </div>
  )
}
