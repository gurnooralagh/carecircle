import { useEffect, useRef } from 'react'

interface UsePollingOptions {
  pollFn: () => Promise<{ status: string }>
  onReady: () => void
  onFailed?: () => void
  readyStatus?: string
  failedStatus?: string
  interval?: number
  enabled?: boolean
  timeoutMs?: number
}

export function usePolling({
  pollFn,
  onReady,
  onFailed,
  readyStatus = 'ready',
  failedStatus = 'failed',
  interval = 3000,
  enabled = true,
  timeoutMs = 10 * 60 * 1000, // 10 minutes default
}: UsePollingOptions) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const activeRef = useRef(true)

  useEffect(() => {
    if (!enabled) return

    activeRef.current = true

    // Hard timeout — give up after timeoutMs
    timeoutRef.current = setTimeout(() => {
      if (activeRef.current) onFailed?.()
    }, timeoutMs)

    const poll = async () => {
      if (!activeRef.current) return
      try {
        const result = await pollFn()
        if (!activeRef.current) return

        if (result.status === readyStatus) {
          if (timeoutRef.current) clearTimeout(timeoutRef.current)
          onReady()
          return
        }
        if (result.status === failedStatus) {
          if (timeoutRef.current) clearTimeout(timeoutRef.current)
          onFailed?.()
          return
        }
        // Keep polling
        timerRef.current = setTimeout(poll, interval)
      } catch {
        if (!activeRef.current) return
        timerRef.current = setTimeout(poll, interval)
      }
    }

    poll()

    return () => {
      activeRef.current = false
      if (timerRef.current) clearTimeout(timerRef.current)
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [enabled]) // eslint-disable-line react-hooks/exhaustive-deps
}
