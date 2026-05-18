import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, ExternalLink, ChevronDown, FolderOpen } from 'lucide-react'
import { SkeletonList } from '../../components/ui/SkeletonCard'
import { EmptyState } from '../../components/ui/EmptyState'
import { PageTransition } from '../../components/ui/PageTransition'
import api from '../../lib/api'
import { supabase } from '../../lib/supabase'
import { usePatientStore } from '../../store/patient'
import { formatDate } from '../../lib/utils'

const STATUS_STYLES: Record<string, { label: string; color: string; bg: string }> = {
  pending: { label: 'Pending', color: '#D97706', bg: '#FFFBEB' },
  processing: { label: 'Processing', color: '#0891B2', bg: '#F0F9FF' },
  completed: { label: 'Analysed', color: '#16A34A', bg: '#F0FDF4' },
  failed: { label: 'Failed', color: '#DC2626', bg: '#FEF2F2' },
}

interface RawDoc {
  id: string
  document_type: string
  original_filename: string
  extraction_status: string
  uploaded_at: string
}

interface DocWithUrl extends RawDoc {
  signed_url: string | null
}

export function DocumentsTab() {
  const { patient_id } = usePatientStore()

  const { data: documents = [], isLoading, error: queryError } = useQuery({
    queryKey: ['documents', patient_id],
    queryFn: async (): Promise<DocWithUrl[]> => {
      const { data, error } = await supabase
        .from('documents')
        .select('id, document_type, original_filename, extraction_status, uploaded_at')
        .eq('patient_id', patient_id)
        .eq('is_deleted', false)
        .order('uploaded_at', { ascending: false })

      if (error) throw new Error(error.message)
      if (!data || data.length === 0) return []

      // Fetch signed URLs in parallel (best-effort)
      const withUrls = await Promise.all(
        (data as RawDoc[]).map(async (doc) => {
          try {
            const res = await api.get(`/api/documents/${doc.id}/url`)
            return { ...doc, signed_url: res.data.signed_url as string }
          } catch {
            return { ...doc, signed_url: null }
          }
        })
      )
      return withUrls
    },
    enabled: !!patient_id,
    retry: false,
  })

  // Group by document_type
  const grouped: Record<string, DocWithUrl[]> = {}
  for (const doc of documents) {
    const type = doc.document_type ?? 'Other'
    if (!grouped[type]) grouped[type] = []
    grouped[type].push(doc)
  }

  return (
    <PageTransition className="px-4 py-6 max-w-xl mx-auto">
      <h2
        className="text-2xl font-normal text-text-primary mb-6"
        style={{ fontFamily: 'Fraunces, serif' }}
      >
        Documents
      </h2>

      {isLoading && <SkeletonList count={4} />}

      {queryError && (
        <div className="bg-[#FEF2F2] border border-[#DC262630] rounded-xl p-4 mb-4">
          <p className="text-sm font-semibold text-severity-critical mb-1">Could not load documents</p>
          <p className="text-xs text-severity-critical opacity-80">{(queryError as Error).message}</p>
        </div>
      )}

      {!isLoading && !queryError && documents.length === 0 && (
        <EmptyState
          icon={FolderOpen}
          title="No documents yet"
          description="Upload prescriptions and medical reports to see them here."
        />
      )}

      {!isLoading &&
        Object.entries(grouped).map(([type, docs]) => (
          <DocumentGroup key={type} type={type} docs={docs} />
        ))}
    </PageTransition>
  )
}

function DocumentGroup({ type, docs }: { type: string; docs: DocWithUrl[] }) {
  const [open, setOpen] = useState(true)

  return (
    <div className="mb-4">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 text-sm font-semibold text-text-muted uppercase tracking-wide mb-3 hover:text-text-secondary transition-colors"
      >
        <ChevronDown className={`w-4 h-4 transition-transform ${open ? '' : '-rotate-90'}`} />
        {type} ({docs.length})
      </button>

      {open && (
        <div className="flex flex-col gap-3">
          {docs.map((doc) => (
            <DocumentCard key={doc.id} doc={doc} />
          ))}
        </div>
      )}
    </div>
  )
}

function DocumentCard({ doc }: { doc: DocWithUrl }) {
  const statusStyle = STATUS_STYLES[doc.extraction_status] ?? STATUS_STYLES.pending

  return (
    <div className="bg-bg-card border border-border rounded-xl p-4 flex items-start gap-3">
      <div className="w-10 h-10 rounded-lg bg-bg-secondary flex items-center justify-center shrink-0">
        <FileText className="w-5 h-5 text-text-muted" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text-primary truncate">{doc.original_filename}</p>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <span className="text-xs text-text-muted">
            Uploaded {formatDate(doc.uploaded_at)}
          </span>
        </div>
        <span
          className="inline-flex mt-1.5 px-2 py-0.5 rounded-full text-xs font-medium"
          style={{ color: statusStyle.color, backgroundColor: statusStyle.bg }}
        >
          {statusStyle.label}
        </span>
      </div>
      {doc.signed_url && (
        <a
          href={doc.signed_url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Open ${doc.original_filename}`}
          className="w-9 h-9 rounded-lg border border-border flex items-center justify-center text-text-muted hover:text-accent-primary hover:border-accent-primary transition-colors shrink-0"
        >
          <ExternalLink className="w-4 h-4" />
        </a>
      )}
    </div>
  )
}
