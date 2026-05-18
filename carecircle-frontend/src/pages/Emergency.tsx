import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { X, Printer, Pill, AlertTriangle, Activity, UserCheck, Phone } from 'lucide-react'
import api from '../lib/api'
import { usePatientStore } from '../store/patient'
import { calcAge, formatDate } from '../lib/utils'
import type { EmergencySummary } from '../types'

export function Emergency() {
  const navigate = useNavigate()
  const { patient_id, patient_name } = usePatientStore()

  const { data, isLoading } = useQuery({
    queryKey: ['emergency-summary', patient_id],
    queryFn: async () => {
      try {
        const res = await api.get(`/api/patients/${patient_id}/emergency_summary`)
        return res.data as EmergencySummary
      } catch {
        return null
      }
    },
    enabled: !!patient_id,
  })

  return (
    <div className="fixed inset-0 z-50 bg-white overflow-y-auto">
      {/* Header */}
      <div className="sticky top-0 bg-white border-b border-[#E8E4DE] px-6 py-4 flex items-center justify-between no-print">
        <div>
          <h1 className="text-xl font-bold text-[#DC2626]">Emergency Summary</h1>
          <p className="text-sm text-[#6B6B6B]">For emergency medical personnel</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => window.print()}
            aria-label="Print emergency summary"
            className="flex items-center gap-1.5 h-9 px-3 rounded-lg border border-[#E8E4DE] text-sm text-[#1A1A1A] hover:bg-[#F2F0EC] transition-colors"
          >
            <Printer className="w-4 h-4" />
            Print
          </button>
          <button
            onClick={() => navigate(-1)}
            aria-label="Close emergency summary"
            className="w-9 h-9 rounded-lg border border-[#E8E4DE] flex items-center justify-center text-[#6B6B6B] hover:bg-[#F2F0EC] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-6 py-8">
        {isLoading && (
          <div className="flex items-center justify-center py-16">
            <div className="w-8 h-8 rounded-full border-2 border-[#0D6E6E] border-t-transparent animate-spin" />
          </div>
        )}

        {/* If endpoint not built, show what we know */}
        {!isLoading && !data && (
          <div className="bg-[#FFFBEB] border border-[#D97706] rounded-xl p-4 mb-6">
            <p className="text-sm text-[#D97706] font-medium">
              Full emergency summary is loading. Basic information shown below.
            </p>
          </div>
        )}

        {/* Patient header */}
        <section className="mb-8">
          <div className="border-2 border-[#DC2626] rounded-xl p-6">
            <h2 className="text-3xl font-bold text-[#1A1A1A] mb-1">
              {data?.patient.full_name ?? patient_name ?? 'Patient'}
            </h2>
            {data?.patient && (
              <div className="flex flex-wrap gap-4 text-lg text-[#1A1A1A] mt-2">
                <span>Age: {calcAge(data.patient.date_of_birth)}</span>
                <span>·</span>
                <span>{data.patient.gender}</span>
                {data.patient.city && (
                  <>
                    <span>·</span>
                    <span>{data.patient.city}</span>
                  </>
                )}
              </div>
            )}
          </div>
        </section>

        {data && (
          <>
            {/* Active medications */}
            <Section icon={Pill} title="Active Medications" color="#0D6E6E">
              {data.active_medications.length === 0 ? (
                <p className="text-[#6B6B6B]">None on record</p>
              ) : (
                <div className="flex flex-col gap-3">
                  {data.active_medications.map((med) => (
                    <div key={med.medication_id} className="flex justify-between items-start gap-4 py-2 border-b border-[#E8E4DE] last:border-0">
                      <div>
                        <p className="font-semibold text-[#1A1A1A]">{med.drug_name_brand ?? med.drug_name ?? 'Unknown'}</p>
                        {med.drug_name_generic && (
                          <p className="text-sm text-[#6B6B6B]">{med.drug_name_generic}</p>
                        )}
                      </div>
                      <div className="text-right shrink-0">
                        <p className="font-medium text-[#1A1A1A]">{med.dose_text}</p>
                        <p className="text-sm text-[#6B6B6B]">{med.frequency}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Section>

            {/* Allergies */}
            <Section icon={AlertTriangle} title="Known Allergies" color="#DC2626">
              {data.allergies.length === 0 ? (
                <p className="text-[#6B6B6B]">No known allergies on record</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {data.allergies.map((a, i) => (
                    <span
                      key={i}
                      className="px-4 py-2 rounded-full font-semibold text-[#DC2626] bg-[#FEF2F2] border border-[#DC262630] text-base"
                    >
                      {a}
                    </span>
                  ))}
                </div>
              )}
            </Section>

            {/* Active conditions */}
            <Section icon={Activity} title="Active Conditions" color="#EA580C">
              {data.active_conditions.length === 0 ? (
                <p className="text-[#6B6B6B]">None on record</p>
              ) : (
                <ul className="list-disc list-inside space-y-1">
                  {data.active_conditions.map((c, i) => (
                    <li key={i} className="text-[#1A1A1A] text-base">{c}</li>
                  ))}
                </ul>
              )}
            </Section>

            {/* Primary doctor */}
            {data.primary_doctor && (
              <Section icon={UserCheck} title="Primary Doctor" color="#0D9488">
                <div>
                  <p className="font-semibold text-[#1A1A1A] text-lg">{data.primary_doctor.name}</p>
                  <p className="text-[#6B6B6B]">{data.primary_doctor.specialty}</p>
                  {data.primary_doctor.phone && (
                    <p className="font-medium text-[#0D6E6E] text-lg mt-1">{data.primary_doctor.phone}</p>
                  )}
                </div>
              </Section>
            )}

            {/* Guardian contacts */}
            {data.guardian_contacts && data.guardian_contacts.length > 0 && (
              <Section icon={Phone} title="Guardian / Emergency Contacts" color="#6B7280">
                <div className="flex flex-col gap-3">
                  {data.guardian_contacts.map((gc, i) => (
                    <div key={i} className="flex items-center justify-between">
                      <div>
                        <p className="font-semibold text-[#1A1A1A]">{gc.name}</p>
                        {gc.relationship && (
                          <p className="text-sm text-[#6B6B6B]">{gc.relationship}</p>
                        )}
                      </div>
                      {gc.phone && (
                        <a
                          href={`tel:${gc.phone}`}
                          className="font-medium text-[#0D6E6E] text-lg"
                        >
                          {gc.phone}
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Recent documents */}
            {data.recent_documents && data.recent_documents.length > 0 && (
              <Section icon={null} title="Recent Documents" color="#6B7280">
                <div className="flex flex-col gap-2">
                  {data.recent_documents.map((doc) => (
                    <div key={doc.document_id} className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-[#1A1A1A] text-sm">{doc.filename}</p>
                        <p className="text-xs text-[#9E9E9E]">
                          {doc.document_type} · {formatDate(doc.upload_date)}
                        </p>
                      </div>
                      <a
                        href={doc.file_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-[#0D6E6E] hover:underline"
                      >
                        View
                      </a>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function Section({
  icon: Icon,
  title,
  color,
  children,
}: {
  icon: React.ElementType | null
  title: string
  color: string
  children: React.ReactNode
}) {
  return (
    <section className="mb-6">
      <div className="flex items-center gap-2 mb-3 pb-2 border-b-2 border-[#E8E4DE]">
        {Icon && <Icon className="w-5 h-5" style={{ color }} />}
        <h3 className="text-lg font-bold" style={{ color }}>
          {title}
        </h3>
      </div>
      {children}
    </section>
  )
}
