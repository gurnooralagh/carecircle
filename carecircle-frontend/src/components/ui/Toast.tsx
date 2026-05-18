import { AnimatePresence, motion } from 'framer-motion'
import { X, CheckCircle, AlertCircle, Info } from 'lucide-react'
import { useToastStore } from '../../store/toast'

export function ToastContainer() {
  const { toasts, removeToast } = useToastStore()

  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex flex-col gap-2 w-full max-w-sm px-4 pointer-events-none"
    >
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className="pointer-events-auto"
          >
            <ToastItem toast={toast} onRemove={removeToast} />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}

interface ToastItemProps {
  toast: { id: string; message: string; type: 'success' | 'error' | 'info' }
  onRemove: (id: string) => void
}

const TOAST_STYLES = {
  success: {
    bg: 'bg-[#F0FDF4]',
    border: 'border-[#16A34A]',
    icon: CheckCircle,
    iconColor: 'text-[#16A34A]',
  },
  error: {
    bg: 'bg-[#FEF2F2]',
    border: 'border-[#DC2626]',
    icon: AlertCircle,
    iconColor: 'text-[#DC2626]',
  },
  info: {
    bg: 'bg-[#F0F9FF]',
    border: 'border-[#0891B2]',
    icon: Info,
    iconColor: 'text-[#0891B2]',
  },
}

function ToastItem({ toast, onRemove }: ToastItemProps) {
  const style = TOAST_STYLES[toast.type]
  const Icon = style.icon

  return (
    <div
      className={`flex items-start gap-3 p-4 rounded-xl border shadow-md ${style.bg} ${style.border}`}
    >
      <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${style.iconColor}`} />
      <p className="text-sm text-text-primary flex-1">{toast.message}</p>
      <button
        onClick={() => onRemove(toast.id)}
        aria-label="Dismiss notification"
        className="shrink-0 text-text-muted hover:text-text-primary transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}
