import { useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { Upload, X, FileText } from 'lucide-react'
import type { UploadFile } from '../types'

interface FileUploadZoneProps {
  files: UploadFile[]
  onFilesChange: (files: UploadFile[]) => void
}

const DOCUMENT_TYPES = ['Prescription', 'Lab Report', 'Discharge Summary', 'Other'] as const

function generateId() {
  return Math.random().toString(36).slice(2)
}

function toUploadFile(file: File): UploadFile {
  return {
    id: generateId(),
    file,
    document_type: 'Prescription',
    document_date: new Date().toISOString().slice(0, 10),
  }
}

export function FileUploadZone({ files, onFilesChange }: FileUploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return
    const valid = Array.from(incoming).filter((f) =>
      ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg'].includes(f.type)
    )
    onFilesChange([...files, ...valid.map(toUploadFile)])
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragging(false)
    addFiles(e.dataTransfer.files)
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragging(true)
  }

  const handleDragLeave = () => setDragging(false)

  const removeFile = (id: string) => {
    onFilesChange(files.filter((f) => f.id !== id))
  }

  const updateFile = (id: string, patch: Partial<UploadFile>) => {
    onFilesChange(files.map((f) => (f.id === id ? { ...f, ...patch } : f)))
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Upload files — click or drag and drop"
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center gap-3 cursor-pointer transition-colors select-none ${
          dragging
            ? 'border-accent-primary bg-[#F0FDFA]'
            : 'border-border bg-bg-secondary hover:border-accent-primary hover:bg-[#F0FDFA]'
        }`}
      >
        <div className="w-12 h-12 rounded-full bg-bg-card border border-border flex items-center justify-center">
          <Upload className={`w-6 h-6 ${dragging ? 'text-accent-primary' : 'text-text-muted'}`} />
        </div>
        <div className="text-center">
          <p className="text-sm font-medium text-text-primary">
            {dragging ? 'Drop files here' : 'Click to upload or drag and drop'}
          </p>
          <p className="text-xs text-text-muted mt-0.5">PDF, JPG, PNG accepted</p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
          multiple
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
          aria-label="File input"
        />
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="flex flex-col gap-3">
          {files.map((uf) => (
            <div
              key={uf.id}
              className="bg-bg-card border border-border rounded-xl p-4 flex items-start gap-3"
            >
              <FileText className="w-5 h-5 text-accent-primary shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0 flex flex-col gap-2">
                <p className="text-sm font-medium text-text-primary truncate">{uf.file.name}</p>
                <div className="flex flex-col sm:flex-row gap-2">
                  <select
                    value={uf.document_type}
                    onChange={(e) =>
                      updateFile(uf.id, {
                        document_type: e.target.value as UploadFile['document_type'],
                      })
                    }
                    aria-label="Document type"
                    className="flex-1 h-9 px-3 rounded-lg border border-border text-sm text-text-primary bg-bg-card focus:outline-none focus:ring-2 focus:ring-accent-primary"
                  >
                    {DOCUMENT_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <button
                onClick={() => removeFile(uf.id)}
                aria-label={`Remove ${uf.file.name}`}
                className="shrink-0 w-8 h-8 rounded-lg border border-border flex items-center justify-center text-text-muted hover:text-severity-critical hover:border-severity-critical transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
