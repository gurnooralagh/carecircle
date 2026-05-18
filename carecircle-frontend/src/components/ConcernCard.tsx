import { useState } from 'react'
import { ChevronDown, ChevronUp, FileText } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Concern } from '../types'
import { getSeverityColor, getSeverityBg, getSeverityLabel } from '../lib/utils'
import { StatusBadge } from './ui/Badge'

interface ConcernCardProps {
  concern: Concern
}

export function ConcernCard({ concern }: ConcernCardProps) {
  const [expanded, setExpanded] = useState(false)
  const color = getSeverityColor(concern.priority)
  const bg = getSeverityBg(concern.priority)
  const label = getSeverityLabel(concern.priority)

  return (
    <div
      className="bg-bg-card rounded-xl border border-border shadow-sm overflow-hidden"
      style={{ borderLeft: `4px solid ${color}` }}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="w-full text-left p-4 flex items-start gap-3 focus:outline-none"
        style={{ minHeight: '44px' }}
      >
        <div className="flex-1 min-w-0">
          {/* Severity badge + status badge */}
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span
              className="text-xs font-semibold tracking-wide"
              style={{ color }}
            >
              {label}
            </span>
            {concern.status && concern.status !== 'existing' && (
              <StatusBadge status={concern.status} />
            )}
          </div>
          <h3 className="text-base font-semibold text-text-primary leading-tight">
            {concern.title}
          </h3>
          <p className="text-sm text-text-secondary mt-1 line-clamp-2">
            {concern.summary}
          </p>
        </div>
        <div className="shrink-0 mt-1 text-text-muted">
          {expanded ? (
            <ChevronUp className="w-5 h-5" />
          ) : (
            <ChevronDown className="w-5 h-5" />
          )}
        </div>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div
              className="px-4 pb-4 border-t border-border pt-3 space-y-3"
              style={{ backgroundColor: bg }}
            >
              {concern.what_was_found && (
                <Section title="What was found" text={concern.what_was_found} color={color} />
              )}
              {concern.why_it_matters && (
                <Section title="Why it matters" text={concern.why_it_matters} color={color} />
              )}
              {concern.what_to_do && (
                <Section title="What to do" text={concern.what_to_do} color={color} />
              )}
              {concern.source_documents && concern.source_documents.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-1">
                    Sources
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {concern.source_documents.map((doc, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1 text-xs text-text-muted"
                      >
                        <FileText className="w-3 h-3" />
                        {doc}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Section({
  title,
  text,
  color,
}: {
  title: string
  text: string
  color: string
}) {
  return (
    <div>
      <p
        className="text-xs font-semibold uppercase tracking-wide mb-0.5"
        style={{ color }}
      >
        {title}
      </p>
      <p className="text-sm text-text-primary leading-relaxed">{text}</p>
    </div>
  )
}
