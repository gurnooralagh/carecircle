import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ShieldCheck, ChevronDown, RefreshCw } from 'lucide-react'
import { ConcernCard } from '../../components/ConcernCard'
import { SkeletonList } from '../../components/ui/SkeletonCard'
import { EmptyState } from '../../components/ui/EmptyState'
import { PageTransition } from '../../components/ui/PageTransition'
import api from '../../lib/api'
import { usePatientStore } from '../../store/patient'
import { formatDate } from '../../lib/utils'
import type { Concern, AnalysisRun } from '../../types'

const PRIORITY_ORDER = ['critical_concern', 'high_priority', 'moderate', 'for_your_awareness']

export function FindingsTab() {
  const { patient_id } = usePatientStore()
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Fetch runs list
  const { data: runsData } = useQuery({
    queryKey: ['dashboard-runs', patient_id],
    queryFn: async () => {
      const res = await api.get(`/api/dashboard/runs/${patient_id}`)
      return res.data as { runs: AnalysisRun[] }
    },
    enabled: !!patient_id,
  })

  const runs = runsData?.runs ?? []
  const latestRun = runs[runs.length - 1] ?? null

  // Default to latest run once loaded
  const effectiveRunId = selectedRunId ?? latestRun?.run_id ?? 'onboarding'
  const selectedRun = runs.find((r) => r.run_id === effectiveRunId) ?? latestRun

  // Fetch concerns for the selected run
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['dashboard-findings', patient_id, effectiveRunId],
    queryFn: async () => {
      const res = await api.get(
        `/api/dashboard/findings/${patient_id}?run_id=${effectiveRunId}`
      )
      return res.data as { concerns: Concern[]; run_id: string }
    },
    enabled: !!patient_id,
    retry: 2,
  })

  const allConcerns = data?.concerns ?? []
  const active = allConcerns
    .filter((c) => c.status !== 'resolved')
    .sort((a, b) => PRIORITY_ORDER.indexOf(a.priority) - PRIORITY_ORDER.indexOf(b.priority))
  const resolved = allConcerns.filter((c) => c.status === 'resolved')
  const [showResolved, setShowResolved] = useState(false)

  return (
    <PageTransition className="px-4 py-6 max-w-xl mx-auto">
      <h2
        className="text-2xl font-normal text-text-primary mb-4"
        style={{ fontFamily: 'Fraunces, serif' }}
      >
        Findings
      </h2>

      {/* Run selector */}
      {runs.length > 0 && (
        <div className="relative mb-5" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen((v) => !v)}
            className="w-full flex items-center justify-between px-4 h-11 rounded-xl bg-bg-card border border-border shadow-sm text-sm font-medium text-text-primary hover:bg-bg-secondary transition-colors"
          >
            <span className="flex items-center gap-2">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: selectedRun?.run_type === 'onboarding' ? '#0891B2' : '#8B5CF6' }}
              />
              <span>
                {selectedRun?.label ?? 'Select run'}
                {selectedRun?.run_date ? ` · ${formatDate(selectedRun.run_date)}` : ''}
              </span>
              {selectedRun?.run_id === latestRun?.run_id && (
                <span className="text-xs font-medium px-1.5 py-0.5 rounded-full bg-[#F0FDF4] text-[#16A34A]">
                  Latest
                </span>
              )}
            </span>
            <ChevronDown className={`w-4 h-4 text-text-muted transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
          </button>

          {dropdownOpen && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-bg-card border border-border rounded-xl shadow-lg z-20 overflow-hidden">
              {[...runs].reverse().map((run) => {
                const isLatest = run.run_id === latestRun?.run_id
                const isSelected = run.run_id === effectiveRunId
                return (
                  <button
                    key={run.run_id}
                    onClick={() => {
                      setSelectedRunId(run.run_id)
                      setDropdownOpen(false)
                    }}
                    className={`w-full flex items-center justify-between px-4 py-3 text-left hover:bg-bg-secondary transition-colors ${
                      isSelected ? 'bg-bg-secondary' : ''
                    }`}
                    style={{ minHeight: '44px' }}
                  >
                    <span className="flex items-center gap-2">
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: run.run_type === 'onboarding' ? '#0891B2' : '#8B5CF6' }}
                      />
                      <div className="text-left">
                        <p className="text-sm font-medium text-text-primary">{run.label}</p>
                        <p className="text-xs text-text-muted">{formatDate(run.run_date)}</p>
                      </div>
                    </span>
                    <span className="flex items-center gap-1.5">
                      {isLatest && (
                        <span className="text-xs font-medium px-1.5 py-0.5 rounded-full bg-[#F0FDF4] text-[#16A34A]">
                          Latest
                        </span>
                      )}
                      {isSelected && (
                        <span className="text-accent-primary text-xs">✓</span>
                      )}
                    </span>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}

      {isLoading && <SkeletonList count={4} />}

      {isError && (
        <div className="bg-[#FEF2F2] border border-[#DC262630] rounded-xl p-5 text-center mb-4">
          <p className="text-sm font-semibold text-severity-critical mb-1">Couldn't load findings</p>
          <p className="text-sm text-severity-critical opacity-80 mb-4">
            Something went wrong fetching your findings. Try again or refresh the page.
          </p>
          <button
            onClick={() => refetch()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-[#DC262630] text-severity-critical text-sm font-medium hover:bg-[#FEF2F2] transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Try again
          </button>
        </div>
      )}

      {!isLoading && !isError && active.length === 0 && (
        <EmptyState
          icon={ShieldCheck}
          title="No active findings"
          description="No concerns found for this analysis run."
        />
      )}

      {!isLoading && !isError && (
        <div className="flex flex-col gap-3">
          {active.map((c) => (
            <ConcernCard key={c.id ?? c.title} concern={c} />
          ))}
        </div>
      )}

      {/* Resolved section */}
      {!isLoading && resolved.length > 0 && (
        <div className="mt-6">
          <button
            onClick={() => setShowResolved((v) => !v)}
            className="flex items-center gap-2 text-sm font-medium text-text-muted hover:text-text-secondary transition-colors mb-3"
          >
            <ChevronDown
              className={`w-4 h-4 transition-transform ${showResolved ? 'rotate-180' : ''}`}
            />
            {resolved.length} resolved
          </button>
          {showResolved && (
            <div className="flex flex-col gap-3">
              {resolved.map((c) => (
                <ConcernCard key={c.id ?? c.title} concern={c} />
              ))}
            </div>
          )}
        </div>
      )}
    </PageTransition>
  )
}
