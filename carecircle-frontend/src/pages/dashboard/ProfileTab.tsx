import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { ChevronDown, User } from 'lucide-react'
import { SkeletonCard } from '../../components/ui/SkeletonCard'
import { PageTransition } from '../../components/ui/PageTransition'
import api from '../../lib/api'
import { usePatientStore } from '../../store/patient'
import { useAuthStore } from '../../store/auth'
import { calcAge, formatDate } from '../../lib/utils'
import type { Patient } from '../../types'
import { supabase } from '../../lib/supabase'

export function ProfileTab() {
  const { patient_id } = usePatientStore()
  const { user_id } = useAuthStore()
  const [aiSummaryOpen, setAiSummaryOpen] = useState(false)
  const [signingOut, setSigningOut] = useState(false)

  const { data: patient, isLoading } = useQuery({
    queryKey: ['patient-profile', patient_id],
    queryFn: async () => {
      try {
        const res = await api.get(`/api/patients/${patient_id}/profile`)
        return res.data as Patient
      } catch {
        return null
      }
    },
    enabled: !!patient_id,
  })

  const handleSignOut = async () => {
    setSigningOut(true)
    await supabase.auth.signOut()
    window.location.href = '/login'
  }

  if (isLoading) {
    return (
      <PageTransition className="px-4 py-6 max-w-xl mx-auto space-y-4">
        <SkeletonCard lines={5} />
        <SkeletonCard lines={3} />
      </PageTransition>
    )
  }

  if (!patient) {
    return (
      <PageTransition className="px-4 py-6 max-w-xl mx-auto space-y-4">
        <div className="bg-bg-card border border-border rounded-2xl p-6 text-center">
          <User className="w-8 h-8 text-text-muted mx-auto mb-3" />
          <p className="text-base font-semibold text-text-primary mb-1">Profile coming soon</p>
          <p className="text-sm text-text-secondary">Patient profile details will be available here.</p>
        </div>
        <button
          onClick={handleSignOut}
          disabled={signingOut}
          className="w-full py-3 rounded-xl border border-border text-sm font-medium text-severity-critical hover:bg-[#FEF2F2] transition-colors"
        >
          {signingOut ? 'Signing out…' : 'Sign out'}
        </button>
      </PageTransition>
    )
  }

  return (
    <PageTransition className="px-4 py-6 max-w-xl mx-auto">
      <h2
        className="text-2xl font-normal text-text-primary mb-6"
        style={{ fontFamily: 'Fraunces, serif' }}
      >
        Profile
      </h2>

      {patient && (
        <>
          {/* Patient info */}
          <section className="bg-bg-card rounded-xl border border-border shadow-sm p-6 mb-4">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-full bg-[#E6F4F4] flex items-center justify-center">
                <User className="w-6 h-6 text-accent-primary" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-text-primary">{patient.full_name}</h3>
                <p className="text-sm text-text-secondary">
                  {calcAge(patient.date_of_birth)} years · {patient.gender}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <ProfileField label="Date of birth" value={formatDate(patient.date_of_birth)} />
              {patient.city && <ProfileField label="City" value={patient.city} />}
              {patient.weight_kg && <ProfileField label="Weight" value={`${patient.weight_kg} kg`} />}
              {patient.height_cm && <ProfileField label="Height" value={`${patient.height_cm} cm`} />}
            </div>
          </section>

          {/* Active diagnoses */}
          {patient.active_diagnoses && patient.active_diagnoses.length > 0 && (
            <section className="bg-bg-card rounded-xl border border-border shadow-sm p-6 mb-4">
              <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-3">
                Active diagnoses
              </h3>
              <div className="flex flex-wrap gap-2">
                {patient.active_diagnoses.map((d, i) => (
                  <span
                    key={i}
                    className="inline-flex px-3 py-1 rounded-full text-sm bg-bg-secondary text-text-primary border border-border"
                  >
                    {d}
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Known allergies */}
          {patient.known_allergies && patient.known_allergies.length > 0 && (
            <section className="bg-bg-card rounded-xl border border-border shadow-sm p-6 mb-4">
              <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-3">
                Known allergies
              </h3>
              <div className="flex flex-wrap gap-2">
                {patient.known_allergies.map((a, i) => (
                  <span
                    key={i}
                    className="inline-flex px-3 py-1 rounded-full text-sm bg-[#FEF2F2] text-severity-critical border border-[#DC262630]"
                  >
                    {a}
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Primary doctor — coming soon */}
          <section className="bg-bg-card rounded-xl border border-border shadow-sm p-6 mb-4">
            <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-2">
              Primary doctor
            </h3>
            <p className="text-sm text-text-muted italic">Coming soon</p>
          </section>

          {/* AI summary */}
          {patient.ai_summary && (
            <section className="bg-bg-card rounded-xl border border-border shadow-sm mb-4 overflow-hidden">
              <button
                onClick={() => setAiSummaryOpen((v) => !v)}
                className="flex items-center justify-between w-full px-6 py-4"
              >
                <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide">
                  AI health summary
                </h3>
                <ChevronDown
                  className={`w-4 h-4 text-text-muted transition-transform ${aiSummaryOpen ? 'rotate-180' : ''}`}
                />
              </button>
              {aiSummaryOpen && (
                <div className="px-6 pb-5 border-t border-border pt-3">
                  <p className="text-sm text-text-secondary leading-relaxed">
                    {patient.ai_summary}
                  </p>
                </div>
              )}
            </section>
          )}
        </>
      )}

      {/* Account section */}
      <section className="bg-bg-card rounded-xl border border-border shadow-sm p-6">
        <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-4">
          Account
        </h3>
        <div className="flex flex-col gap-3">
          <p className="text-sm text-text-muted">User ID: {user_id}</p>
          <button
            onClick={handleSignOut}
            disabled={signingOut}
            className="h-11 rounded-xl border border-severity-critical text-severity-critical text-sm font-medium hover:bg-[#FEF2F2] transition-colors disabled:opacity-50"
          >
            {signingOut ? 'Signing out…' : 'Sign out'}
          </button>
        </div>
      </section>
    </PageTransition>
  )
}

function ProfileField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-text-muted mb-0.5">{label}</p>
      <p className="text-sm font-medium text-text-primary">{value}</p>
    </div>
  )
}
